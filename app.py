import os
import re
import sqlite3
import threading
import asyncio
import httpx
import functools
import logging
import schedule
import time
from datetime import datetime
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

# ====== Logging Configuration ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_errors.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ====== Configuration ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

ADMIN_IDS = [1119128553]  # @Thawkhyan999
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mysecret123")

# ====== NEW: Multi-Admin Users (Username + Password) ======
ADMIN_USERS = {
    "admin": "mysecret123",       # ခင်ဗျား
    "thawkhyan": "yourpass123",   # ခင်ဗျားရဲ့ အမည်
    # နောက်ထပ် Admin တွေ ထပ်ထည့်နိုင်ပါတယ်
}

EXCHANGE_RATE = 4545

PAYMENT_INFO = (
    "💳 **ငွေလွှဲရန်**\n"
    "KBZPay: 09426419462\n"
    "WavePay: 09426419462"
)

PLAN_LIMITS = {
    "free": {"limit": 50, "price": 0},
    "basic": {"limit": 500, "price": 10000},
    "premium": {"limit": 1500, "price": 30000},
    "premium_plus": {"limit": 5000, "price": 50000},
}


def get_price_usd(price_mmk):
    return round(price_mmk / EXCHANGE_RATE, 2)


BOT_NAMES = ["မစ္စတာသန်း", "ကိုသန်း", "သန်း"]

# ====== Flask App ======
flask_app = Flask(__name__)

# ====== Flask Routes (ဒီနေရာမှာ စတင်ထည့်ပါ) ======

@flask_app.route("/")
def home():
    return "🤖 Bot is running! Visit /admin/proofs for dashboard."

@flask_app.route("/health")
def health():
    return "OK", 200

# 👇 ဒီနေရာမှာ /admin/proofs ကို ထည့်ပါ
@flask_app.route("/admin/proofs")
@requires_auth
def admin_proofs():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, plan, usage_count, proof_status, proof_file_id FROM users")
    results = c.fetchall()
    conn.close()

    html = "<h2>📋 Proofs Dashboard</h2>"
    html += "<table border='1' cellpadding='5' style='border-collapse:collapse;'>"
    html += "<tr><th>User ID</th><th>Plan</th><th>Usage</th><th>Proof Status</th><th>File ID</th><th>Actions</th></tr>"
    for uid, plan, usage, status, file_id in results:
        html += (
            f"<tr><td>{uid}</td><td>{plan}</td><td>{usage}</td><td>{status}</td>"
            f"<td>{file_id[:30] if file_id else '-'}...</td>"
        )
        if status == "pending":
            html += (
                f"<td><a href='/admin/approve/{uid}'>✅ Approve</a> | "
                f"<a href='/admin/reject/{uid}'>❌ Reject</a></td>"
            )
        else:
            html += "<td>-</td>"
        html += "</tr>"
    html += "</table>"
    return html

# 👇 နောက်ထပ် Route တွေကို ဆက်ထည့်ပါ
@flask_app.route("/admin/users")
@requires_auth
def admin_users():
    # ...

@flask_app.route("/admin/stats")
@requires_auth
def admin_stats():
    # ...

# ====== ဒီမှာ Flask Routes ပြီးဆုံးပါပြီ ======

# ====== NEW: User List Dashboard ======
@flask_app.route("/admin/users")
@requires_auth
def admin_users():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, plan, usage_count, proof_status FROM users ORDER BY user_id")
    results = c.fetchall()
    conn.close()

    html = "<h2>👥 User List</h2>"
    html += "<table border='1' cellpadding='5' style='border-collapse:collapse;'>"
    html += "<tr><th>User ID</th><th>Plan</th><th>Usage</th><th>Proof Status</th></tr>"
    for uid, plan, usage, status in results:
        html += f"<tr><td>{uid}</td><td>{plan}</td><td>{usage}</td><td>{status}</td></tr>"
    html += "</table>"
    html += f"<br><p><b>Total Users: {len(results)}</b></p>"
    return html


@flask_app.route("/admin/stats")
@requires_auth
def admin_stats():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT plan, COUNT(*) FROM users GROUP BY plan")
    plan_stats = c.fetchall()

    c.execute("SELECT COUNT(*) FROM users WHERE proof_status='pending'")
    pending = c.fetchone()[0]

    c.execute("SELECT SUM(usage_count) FROM users")
    total_usage = c.fetchone()[0] or 0

    conn.close()

    html = "<h2>📊 Bot Statistics</h2>"
    html += f"<p><b>Total Users:</b> {total_users}</p>"
    html += f"<p><b>Pending Proofs:</b> {pending}</p>"
    html += f"<p><b>Total API Calls:</b> {total_usage}</p>"
    html += "<h3>Plan Distribution</h3><ul>"
    for plan, count in plan_stats:
        html += f"<li>{plan}: {count}</li>"
    html += "</ul>"
    return html


@flask_app.route("/admin/approve/<user_id>")
@requires_auth
def approve_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "SELECT plan FROM users WHERE user_id=? AND proof_status='pending'",
        (user_id,),
    )
    result = c.fetchone()
    if not result:
        conn.close()
        return f"❌ User {user_id} not found or not pending."
    plan = result[0]
    price = PLAN_LIMITS[plan]["price"]

    c.execute(
        """
        UPDATE users 
        SET proof_status='approved', usage_count=0, price=? 
        WHERE user_id=? AND proof_status='pending'
        """,
        (price, user_id),
    )
    conn.commit()
    conn.close()
    return f"✅ User {user_id} upgraded to {plan} Plan!"


@flask_app.route("/admin/reject/<user_id>")
@requires_auth
def reject_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET proof_status='rejected' WHERE user_id=? AND proof_status='pending'",
        (user_id,),
    )
    if c.rowcount == 0:
        conn.close()
        return f"❌ User {user_id} not found or not pending."
    conn.commit()
    conn.close()
    return f"❌ User {user_id} proof rejected!"


# ====== Utility Functions ======
def get_bot_name(text):
    for name in BOT_NAMES:
        if name.lower() in text.lower():
            return name
    return None


def clean_text(text):
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"t\.me/\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ====== Database Functions ======
def init_db():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()

    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        plan TEXT DEFAULT 'free',
        usage_count INTEGER DEFAULT 0,
        proof_status TEXT DEFAULT 'none',
        proof_file_id TEXT,
        price INTEGER DEFAULT 0,
        proof_timestamp TEXT,
        goals TEXT,
        weaknesses TEXT,
        dream TEXT,
        career TEXT,
        money_mindset TEXT,
        relationship TEXT
    )"""
    )

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS referrals (
        inviter_id TEXT,
        invited_id TEXT,
        timestamp TEXT
    )
    """
    )

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS habits (
        user_id TEXT,
        habit TEXT,
        created_at TEXT
    )
    """
    )

    for col in [
        "proof_status",
        "proof_file_id",
        "price",
        "proof_timestamp",
        "goals",
        "weaknesses",
        "dream",
        "career",
        "money_mindset",
        "relationship",
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully.")


def add_user(user_id, plan="free"):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    price = PLAN_LIMITS[plan]["price"]
    c.execute(
        """
        INSERT OR REPLACE INTO users (
            user_id, plan, usage_count, proof_status, proof_file_id,
            price, proof_timestamp,
            goals, weaknesses, dream, career, money_mindset, relationship
        ) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            plan,
            0,
            "none",
            None,
            price,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        """
        SELECT plan, usage_count, proof_status, proof_file_id, price, proof_timestamp,
               goals, weaknesses, dream, career, money_mindset, relationship 
        FROM users WHERE user_id=?
    """,
        (user_id,),
    )
    result = c.fetchone()
    conn.close()
    return result


def update_profile(user_id, field, value):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()


def update_proof(user_id, file_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET proof_file_id=?, proof_status='pending', proof_timestamp=? WHERE user_id=?",
        (file_id, datetime.utcnow().isoformat(), user_id),
    )
    conn.commit()
    conn.close()


def check_limit(user_id):
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
        return True
    plan = user[0]
    usage = user[1]
    if usage >= PLAN_LIMITS[plan]["limit"]:
        return False
    return True


def increment_usage(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?",
        (user_id,),
    )
    conn.commit()
    conn.close()


# ====== Referral System ======
def generate_ref_code(user_id):
    return f"REF{user_id}"


def give_referral_reward(inviter_id, invited_id):
    try:
        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()

        c.execute("SELECT usage_count FROM users WHERE user_id=?", (inviter_id,))
        row = c.fetchone()
        if not row:
            add_user(inviter_id, "free")
            usage = 0
        else:
            usage = row[0]
        new_usage = max(usage - 50, 0)
        c.execute(
            "UPDATE users SET usage_count=? WHERE user_id=?",
            (new_usage, inviter_id),
        )

        c.execute(
            """
            INSERT INTO referrals (inviter_id, invited_id, timestamp)
            VALUES (?, ?, ?)
        """,
            (inviter_id, invited_id, datetime.utcnow().isoformat()),
        )

        conn.commit()
        conn.close()
        logger.info(
            f"🎁 Referral reward (50 calls): inviter={inviter_id}, invited={invited_id}"
        )
    except Exception as e:
        logger.error(f"❌ Referral reward error: {e}")


def get_referral_count(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM referrals WHERE inviter_id=?",
        (user_id,),
    )
    count = c.fetchone()[0]
    conn.close()
    return count


# ====== Habits ======
def add_habit(user_id, habit_text):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO habits (user_id, habit, created_at) VALUES (?, ?, ?)",
        (user_id, habit_text, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_habits(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "SELECT habit, created_at FROM habits WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (user_id,),
    )
    results = c.fetchall()
    conn.close()
    return results


# ====== Monthly Usage Reset ======
def reset_usage():
    try:
        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()
        c.execute("UPDATE users SET usage_count = 0")
        conn.commit()
        conn.close()
        logger.info("✅ Monthly usage reset completed successfully.")
    except Exception as e:
        logger.error(f"❌ Usage reset error: {e}")


# ====== Daily Coaching ======
system_prompt = (
    "သင်ဟာ မစ္စတာသန်း (Mr.T) — funny, friendly, motivational AI Bot ဖြစ်ပါတယ်။\n\n"
    "မင်းရဲ့ အဓိက ကျွမ်းကျင်မှု နယ်ပယ် (၆) ခုက -\n"
    "1️⃣ **Life Coach** - ဘဝအကြံပေးခြင်း၊ စိတ်ဓာတ်ခွန်အားပေးခြင်း\n"
    "2️⃣ **Relationship Coach** - ဆက်ဆံရေး၊ မိတ်ဖက်ဆက်ဆံရေး၊ မိသားစုဆက်ဆံရေး အကြံပေးခြင်း\n"
    "3️⃣ **Money Mindset Coach** - ငွေကြေးဆိုင်ရာ အတွေးအခေါ်၊ ချွေတာနည်း၊ ရင်းနှီးမြှုပ်နှံမှုအကြံပေးခြင်း\n"
    "4️⃣ **Productivity Coach** - အလုပ်နှင့် ဘဝကို ဟန်ချက်ညီစေရေး၊ အချိန်စီမံခန့်ခွဲမှု အကြံပေးခြင်း\n"
    "5️⃣ **Fitness Coach** - ကျန်းမာရေး၊ ကိုယ်လက်လေ့ကျင့်ခန်း၊ စားသောက်မှုအကြံပေးခြင်း\n"
    "6️⃣ **Business Coach** - စီးပွားရေးစတင်ခြင်း၊ စီမံခန့်ခွဲမှု၊ လုပ်ငန်းတိုးတက်ရေး အကြံပေးခြင်း\n\n"
    "အသုံးပြုသူရဲ့ မေးခွန်းကို အထက်ပါ နယ်ပယ်တစ်ခုခုမှာ ကျွမ်းကျင်သူတစ်ယောက်လို ဖြေပေးရမယ်။\n"
    "အဖြေတွေကို မြန်မာလိုပဲ ပြန်ရမယ်။\n"
    "လေးလေးနက်နက် သွားတာ၊ ရယ်စရာလေးတွေ ထည့်တာ၊ မိတ်ဆွေလို ပြောတာ အကုန်လုပ်ရမယ်။\n"
    "ရင်းနှီးမြှုပ်နှံမှုမှာ အာမခံထားတဲ့ အမြတ်၊ တရားမဝင်နည်းလမ်းတွေ မပြောရဘူး။\n"
    "ကျန်းမာရေးဆိုင်ရာ အကြံပေးတဲ့အခါ ဆရာဝန်နဲ့ ပြသဖို့လည်း ညွှန်းရမယ်။"
)


async def ask_model(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "fallbacks": ["gpt-4o-mini", "claude-3.5-sonnet"],
                "max_tokens": 500,
                "temperature": 0.85,
            },
        )
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"].strip()
        elif "error" in result:
            raise Exception(result["error"]["message"])
        else:
            raise Exception("Unexpected API response: " + str(result))


async def send_daily_coaching(bot):
    try:
        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE plan='premium_plus'")
        users = c.fetchall()
        conn.close()

        if not users:
            logger.info("No premium_plus users to send daily coaching.")
            return

        prompt = (
            "မင်္ဂလာပါ၊ ဒီနေ့အတွက် နေ့စဉ် ဘဝလမ်းညွှန်စကား (Daily Coaching Message) ကို ဖန်တီးပေးပါ။\n\n"
            "မစ္စတာသန်း (Mr.T) ရဲ့ အသံနဲ့ ရေးပါ။\n"
            "ဒီနေ့အတွက် အဓိက အကြောင်းအရာ ၃ ခုက -\n"
            "1️⃣ ယုံကြည်မှု (Confidence)\n"
            "2️⃣ အလုပ်အကိုင် (Career)\n"
            "3️⃣ ငွေကြေးအတွေးအခေါ် (Money Mindset)\n\n"
            "အားတက်စရာ၊ လက်တွေ့ကျတဲ့ အကြံပြုချက်၊ မိုတီဗေးရှင်း စကားတွေ ပါစေ။"
        )

        message = await ask_model(prompt)
        if not message or len(message) < 10:
            message = (
                "🌅 ဒီနေ့အတွက် အကောင်းဆုံး နေ့တစ်နေ့ ဖြစ်ပါစေ။ "
                "သင့်ရဲ့ အိပ်မက်တွေကို ယုံကြည်ပြီး ဆက်လက်လုပ်ဆောင်ပါ။"
            )

        sent = 0
        for user in users:
            try:
                await bot.send_message(
                    chat_id=int(user[0]),
                    text=f"🔥 **Daily Coaching Message**\n\n{message}",
                )
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Failed to send daily coaching to {user[0]}: {e}")

        logger.info(f"✅ Daily coaching sent to {sent} premium_plus users.")
    except Exception as e:
        logger.error(f"❌ Daily coaching error: {e}")


# ====== Scheduler ======
def run_scheduler(bot):
    schedule.every(30).days.do(reset_usage)
    schedule.every().day.at("08:00").do(lambda: asyncio.run(send_daily_coaching(bot)))
    logger.info(
        "⏰ Scheduler started. Reset usage every 30 days, daily coaching at 8:00 AM."
    )

    while True:
        schedule.run_pending()
        time.sleep(60)


# ====== Check if bot is mentioned in group chat ======
async def is_bot_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the bot is mentioned by name in a group chat"""
    if not update.message or not update.message.text:
        return False
    
    text = update.message.text.lower()
    
    for name in BOT_NAMES:
        if name.lower() in text:
            return True
    
    bot_username = (await context.bot.get_me()).username
    if bot_username and f"@{bot_username.lower()}" in text:
        return True
    
    return False


# ====== Telegram Bot Command Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if context.args:
        ref_code = context.args[0]
        if ref_code.startswith("REF"):
            inviter_id = ref_code.replace("REF", "")
            if inviter_id != user_id:
                give_referral_reward(inviter_id, user_id)

    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")

    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် မစ္စတာသန်းပါ။\n"
        "သင့်ရဲ့ လက်ထောက် အဖြစ်နဲ့ ကိုယ်ရေးကိုယ်တာ၊ အလုပ်အကိုင်နဲ့ "
        "တခြားလုပ်ဆောင်ရမယ့် အရာတွေကို ယုံကြည်စွာ ဖြေရှင်းပေးဖို့ အသင့်ပါဗျ။\n\n"
        "Commands:\n"
        "/subscribe <plan> - Plan ပြောင်းရန် (free/basic/premium/premium_plus)\n"
        "/ask <question> - AI ကို မေးမြန်းရန်\n"
        "/status - ကိုယ့် Plan နှင့် သုံးခွင့်အကြွင်းကို ကြည့်ရန်\n"
        "/proof - Screenshot proof တင်ရန် (Photo ပို့ပါ)\n"
        "/referral - သင့် referral link ရယူရန်\n"
        "/profile <field> : <value> - Profile သိမ်းရန်\n"
        "/habit <habit> - Habit ထည့်ရန်\n"
        "/myhabits - သင့် habits စာရင်းကြည့်ရန်\n"
        "/help - အကူအညီ\n\n"
        "💡 သိကောင်းစရာ: အခမဲ့ သုံးချင်ရင် `/subscribe free` နှိပ်ပါ။"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 **အသုံးပြုနည်း**\n\n"
        "/start - ဘော့စတင်\n"
        "/help - အကူအညီ\n"
        "/subscribe <plan> - Plan ပြောင်းရန် (free/basic/premium/premium_plus)\n"
        "/ask <question> - AI ကို မေးမြန်းရန်\n"
        "/status - ကိုယ့် Plan နှင့် သုံးခွင့်အကြွင်းကို ကြည့်ရန်\n"
        "/proof - Screenshot proof တင်ရန် (Photo ပို့ပါ)\n"
        "/referral - သင့် referral link ရယူရန်\n"
        "/profile <field> : <value> - Profile သိမ်းရန် (goals/weaknesses/dream/career/money_mindset/relationship)\n"
        "/habit <habit> - Habit ထည့်ရန်\n"
        "/myhabits - သင့် habits စာရင်းကြည့်ရန်\n\n"
        "🎯 **ကျွန်တော် အကြံပေးနိုင်တဲ့ နယ်ပယ်များ**\n"
        "1️⃣ Life Coach\n"
        "2️⃣ Relationship Coach\n"
        "3️⃣ Money Mindset Coach\n"
        "4️⃣ Productivity Coach\n"
        "5️⃣ Fitness Coach\n"
        "6️⃣ Business Coach\n\n"
        "**Admin Commands:**\n"
        "/verify <user_id> <plan> - Plan ပြောင်းရန်\n"
        "/pending_proofs - Pending Proofs စာရင်းကြည့်ရန်\n"
        "/approve_proof <user_id> - Proof အတည်ပြုရန်\n"
        "/reject_proof <user_id> - Proof ပယ်ရန်\n"
        "/broadcast <message> - အားလုံးကို message ပို့ရန်"
    )


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    ref_code = generate_ref_code(user_id)
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    inviter_count = get_referral_count(user_id)

    await update.message.reply_text(
        f"🔗 **သင့် Referral Link**\n\n"
        f"`{ref_link}`\n\n"
        f"📊 သင် ဖိတ်ထားသူ အရေအတွက်: **{inviter_count}**\n\n"
        "✨ သူငယ်ချင်းတွေကို ဖိတ်လိုက်ပါ။ သင် **50 ကြိမ် free usage** ရပါမယ်။"
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    plan = context.args[0] if context.args else "free"

    if plan not in PLAN_LIMITS:
        allowed = ", ".join(PLAN_LIMITS.keys())
        await update.message.reply_text(f"❌ '{plan}' မရှိပါ။ ရနိုင်တဲ့ Plan: {allowed}")
        return

    keyboard = [
        [InlineKeyboardButton("📌 Free (အခမဲ့)", callback_data="sub_free")],
        [InlineKeyboardButton("⭐ Basic (10,000 MMK)", callback_data="sub_basic")],
        [InlineKeyboardButton("💎 Premium (30,000 MMK)", callback_data="sub_premium")],
        [
            InlineKeyboardButton(
                "👑 Premium+ (50,000 MMK) - VIP Coaching",
                callback_data="sub_premium_plus",
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📌 သင် ရွေးချင်တဲ့ Plan ကို ရွေးပါ။\n\n"
        "📌 Free - အခမဲ့\n"
        "⭐ Basic - 10,000 MMK\n"
        "💎 Premium - 30,000 MMK\n"
        "👑 Premium+ - 50,000 MMK (VIP Coaching)",
        reply_markup=reply_markup,
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = query.data

    if data.startswith("sub_"):
        plan = data.replace("sub_", "")
        if plan not in PLAN_LIMITS:
            await query.edit_message_text("❌ Invalid plan.")
            return

        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()
        c.execute(
            "UPDATE users SET plan=?, proof_status='waiting', price=? WHERE user_id=?",
            (plan, PLAN_LIMITS[plan]["price"], user_id),
        )
        conn.commit()
        conn.close()

        price_mmk = PLAN_LIMITS[plan]["price"]
        price_usd = get_price_usd(price_mmk)

        if plan == "premium_plus":
            text = (
                f"👑 **Premium+ (VIP Coaching)** Plan ကို ရွေးလိုက်ပါပြီ။\n"
                f"💰 စျေးနှုန်း: {price_mmk:,} MMK (~${price_usd}) / month\n"
                f"📊 သုံးခွင့်: {PLAN_LIMITS[plan]['limit']} ကြိမ်\n\n"
                f"🔥 နေ့စဉ် coaching + အပတ်စဉ် report + habit tracker ပါဝင်ပါတယ်။\n\n"
                f"📸 ကျေးဇူးပြုပြီး ငွေသွင်း proof screenshot ကို ပို့ပါ။\n\n"
                f"{PAYMENT_INFO}"
            )
        else:
            text = (
                f"📌 **{plan}** Plan ကို ရွေးလိုက်ပါပြီ။\n"
                f"💰 စျေးနှုန်း: {price_mmk:,} MMK (~${price_usd}) / month\n\n"
                f"📸 ကျေးဇူးပြုပြီး ငွေသွင်း proof screenshot ကို ပို့ပါ။\n\n"
                f"{PAYMENT_INFO}"
            )
        await query.edit_message_text(text)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
        user = ("free", 0, "none", None, 0, None, None, None, None, None, None, None)

    (
        plan,
        usage,
        proof_status,
        _,
        price,
        _,
        goals,
        weaknesses,
        dream,
        career,
        money_mindset,
        relationship,
    ) = user
    limit = PLAN_LIMITS[plan]["limit"]
    remaining = limit - usage
    price_usd = get_price_usd(price)
    ref_count = get_referral_count(user_id)

    profile_preview = ""
    if any([goals, career, money_mindset, dream, weaknesses, relationship]):
        profile_preview += "\n📝 **Profile Summary**"
        if goals:
            profile_preview += f"\n• 🎯 Goals: {goals}"
        if career:
            profile_preview += f"\n• 💼 Career: {career}"
        if money_mindset:
            profile_preview += f"\n• 💰 Money Mindset: {money_mindset}"
        if dream:
            profile_preview += f"\n• 🌟 Dream: {dream}"
        if weaknesses:
            profile_preview += f"\n• ⚠️ Weaknesses: {weaknesses}"
        if relationship:
            profile_preview += f"\n• ❤️ Relationship: {relationship}"

    await update.message.reply_text(
        f"📊 **Your Status**\n"
        f"📌 Plan: **{plan}**\n"
        f"💰 Price: {price:,} MMK (~${price_usd})\n"
        f"📈 Usage: {usage} / {limit}\n"
        f"🔋 Remaining: **{remaining}**\n"
        f"🔍 Proof Status: **{proof_status}**\n"
        f"👥 Referrals: **{ref_count}**\n"
        f"{profile_preview}"
    )


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not check_limit(user_id):
        await update.message.reply_text(
            "❌ သင့် Plan အတွက် သုံးခွင့်ကုန်သွားပါပြီ။\n"
            "Plan အသစ်သို့ အဆင့်မြှင့်ရန် /subscribe ကိုသုံးပါ။"
        )
        return

    if not context.args:
        await update.message.reply_text("❌ မေးခွန်းထည့်ပေးပါ။\nUsage: /ask <your question>")
        return

    question = " ".join(context.args)
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        answer = await ask_model(question)
        answer = clean_text(answer)
    except Exception as e:
        logger.error(f"Ask command error for user {user_id}: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
        return

    increment_usage(user_id)

    if len(answer) > 4000:
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(
                answer[i : i + 4000], disable_web_page_preview=True
            )
    else:
        await update.message.reply_text(answer, disable_web_page_preview=True)


# ====== Profile & Habits ======
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "Usage: /profile <field> : <value>\n"
            "Example: /profile goals : ၃ နှစ်အတွင်း ကိုယ်ပိုင်လုပ်ငန်းဖွင့်မယ်\n\n"
            "Allowed fields: goals, weaknesses, dream, career, money_mindset, relationship"
        )
        return

    text = " ".join(context.args)
    if ":" not in text:
        await update.message.reply_text("❌ Format: field : value လိုရေးပါ။")
        return

    field_raw, value = [p.strip() for p in text.split(":", 1)]
    field_map = {
        "goals": "goals",
        "weaknesses": "weaknesses",
        "dream": "dream",
        "career": "career",
        "money_mindset": "money_mindset",
        "relationship": "relationship",
    }
    key = field_map.get(field_raw)
    if not key:
        await update.message.reply_text(
            "❌ field မမှန်ပါ။ goals/weaknesses/dream/career/money_mindset/relationship ထဲက တစ်ခုသုံးပါ။"
        )
        return

    update_profile(user_id, key, value)
    await update.message.reply_text(f"✅ `{key}` ကို update လုပ်ပြီးပါပြီ။")


async def habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text(
            "Usage: /habit <habit>\n"
            "Example: /habit နေ့တိုင်း ၁၅ မိနစ် စာဖတ်မယ်"
        )
        return

    habit_text = " ".join(context.args)
    add_habit(user_id, habit_text)
    await update.message.reply_text(
        f"✅ Habit အသစ် ထည့်ပြီးပါပြီ:\n\n• {habit_text}"
    )


async def myhabits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    habits = get_habits(user_id)
    if not habits:
        await update.message.reply_text("😅 သင့် habits စာရင်း မရှိသေးပါ။ /habit နဲ့ စတင်ရေးထားပါ။")
        return

    text = "📝 **Your Habits (Latest 20)**\n"
    for habit_text, created_at in habits:
        text += f"\n• {habit_text}  ({created_at})"
    await update.message.reply_text(text)


# ====== Proof (photo upload) ======
async def proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 ငွေသွင်း proof screenshot ကို ဒီ chat ထဲမှာ Photo အနေနဲ့ ပို့ပေးပါ။"
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not update.message.photo:
        return

    file_id = update.message.photo[-1].file_id
    update_proof(user_id, file_id)

    await update.message.reply_text(
        "✅ Proof screenshot ကို လက်ခံရရှိပြီးပါပြီ။\n"
        "Admin က စစ်ဆေးပြီး approve/reject လုပ်ပေးပါမယ်။"
    )


# ====== Admin Commands ======
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /verify <user_id> <plan>")
        return

    target_id = context.args[0]
    plan = context.args[1]
    if plan not in PLAN_LIMITS:
        await update.message.reply_text("❌ Invalid plan.")
        return

    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET plan=?, proof_status='approved', price=? WHERE user_id=?",
        (plan, PLAN_LIMITS[plan]["price"], target_id),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ User {target_id} ကို {plan} plan သို့ verify လုပ်ပြီးပါပြီ။"
    )


async def pending_proofs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return

    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "SELECT user_id, plan, proof_file_id, proof_timestamp FROM users WHERE proof_status='pending'"
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("✅ Pending proofs မရှိပါ။")
        return

    text = "📋 **Pending Proofs**\n"
    for uid, plan, file_id, ts in rows:
        text += f"\n• User: {uid} | Plan: {plan} | File: {file_id} | Time: {ts}"
    await update.message.reply_text(text)


async def approve_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /approve_proof <user_id>")
        return

    target_id = context.args[0]
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT plan FROM users WHERE user_id=?", (target_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        await update.message.reply_text("❌ User not found.")
        return
    plan = row[0]
    price = PLAN_LIMITS[plan]["price"]

    c.execute(
        "UPDATE users SET proof_status='approved', usage_count=0, price=? WHERE user_id=?",
        (price, target_id),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Proof for user {target_id} approved. Plan: {plan}"
    )


async def reject_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /reject_proof <user_id>")
        return

    target_id = context.args[0]
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET proof_status='rejected' WHERE user_id=?",
        (target_id,),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"❌ Proof for user {target_id} rejected.")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)

    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()

    sent = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=message)
            sent += 1
            await asyncio.sleep(0.03)
        except Exception as e:
            logger.error(f"Broadcast failed to {uid}: {e}")

    await update.message.reply_text(f"✅ Broadcast sent to {sent} users.")


# ====== Main Message Handler with Group Chat Name Mention ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type
    text = update.message.text
    
    if text.lower() in ["free", "basic", "premium", "premium_plus"]:
        context.args = [text.lower()]
        await subscribe(update, context)
        return
    
    if chat_type in ["group", "supergroup"]:
        if await is_bot_mentioned(update, context):
            for name in BOT_NAMES:
                if name.lower() in text.lower():
                    text = re.sub(name, "", text, flags=re.IGNORECASE)
            
            bot_username = (await context.bot.get_me()).username
            if bot_username:
                text = re.sub(f"@{bot_username}", "", text, flags=re.IGNORECASE)
            
            text = text.strip()
            
            if not text:
                return
            
            if not check_limit(user_id):
                await update.message.reply_text(
                    "❌ သုံးခွင့်ကုန်သွားပါပြီ။ Plan အသစ်ရွေးပါ။"
                )
                return
            
            await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
            try:
                answer = await ask_model(text)
                answer = clean_text(answer)
            except Exception as e:
                logger.error(f"Group message error for user {user_id}: {e}")
                await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
                return
            
            increment_usage(user_id)
            await update.message.reply_text(answer, disable_web_page_preview=True)
            return
    
    if chat_type == "private":
        if not check_limit(user_id):
            await update.message.reply_text(
                "❌ သုံးခွင့်ကုန်သွားပါပြီ။ Plan အသစ်ရွေးပါ။"
            )
            return
        
        await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
        try:
            answer = await ask_model(text)
            answer = clean_text(answer)
        except Exception as e:
            logger.error(f"Handle message error for user {user_id}: {e}")
            await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
            return
        
        increment_usage(user_id)
        bot_name = get_bot_name(text)
        if bot_name:
            answer = f"{bot_name} ပြောတယ်... {answer}"
        
        await update.message.reply_text(answer, disable_web_page_preview=True)


# ====== Main ======
def main():
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("habit", habit))
    application.add_handler(CommandHandler("myhabits", myhabits))
    application.add_handler(CommandHandler("proof", proof))
    application.add_handler(CommandHandler("referral", referral))

    # Admin
    application.add_handler(CommandHandler("verify", verify))
    application.add_handler(CommandHandler("pending_proofs", pending_proofs))
    application.add_handler(CommandHandler("approve_proof", approve_proof))
    application.add_handler(CommandHandler("reject_proof", reject_proof))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # Callback buttons
    application.add_handler(CallbackQueryHandler(button_handler))

    # Photo handler for proof
    application.add_handler(
        MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_handler)
    )

    # Message handler
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )

    # Run Flask + Scheduler in threads
    def run_flask():
        flask_app.run(host="0.0.0.0", port=5000)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    scheduler_thread = threading.Thread(
        target=run_scheduler, args=(application.bot,), daemon=True
    )
    scheduler_thread.start()

    application.run_polling()


if __name__ == "__main__":
    main()
