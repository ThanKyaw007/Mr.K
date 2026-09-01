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
from datetime import datetime, timedelta
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ====== Logging Configuration ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====== Configuration ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

ADMIN_IDS = [1119128553]  # @Thawkhyan999
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mysecret123")

EXCHANGE_RATE = 4545

PAYMENT_INFO = "💳 **ငွေလွှဲရန်**\nKBZPay: 09426419462\nWavePay: 09426419462"

PLAN_LIMITS = {
    "free": {"limit": 50, "price": 0},
    "basic": {"limit": 500, "price": 10000},
    "premium": {"limit": 1500, "price": 30000},
    "premium_plus": {"limit": 5000, "price": 50000}  # VIP Coaching Plan
}

def get_price_usd(price_mmk):
    return round(price_mmk / EXCHANGE_RATE, 2)

BOT_NAMES = ["မစ္စတာသန်း"]

# ====== Flask App ======
flask_app = Flask(__name__)

def check_auth(password):
    return password == ADMIN_PASSWORD

def authenticate():
    return Response(
        "❌ Unauthorized! Password required.", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@flask_app.route('/')
def home():
    return "🤖 Bot is running! Visit /admin/proofs for dashboard."

@flask_app.route('/health')
def health():
    return "OK", 200

@flask_app.route('/admin/proofs')
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
        html += f"<tr><td>{uid}</td><td>{plan}</td><td>{usage}</td><td>{status}</td><td>{file_id[:30] if file_id else '-'}...</td>"
        if status == "pending":
            html += f"<td><a href='/admin/approve/{uid}'>✅ Approve</a> | <a href='/admin/reject/{uid}'>❌ Reject</a></td>"
        else:
            html += "<td>-</td>"
        html += "</tr>"
    html += "</table>"
    return html

@flask_app.route('/admin/stats')
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

@flask_app.route('/admin/approve/<user_id>')
@requires_auth
def approve_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT plan FROM users WHERE user_id=? AND proof_status='pending'", (user_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return f"❌ User {user_id} not found or not pending."
    plan = result[0]
    price = PLAN_LIMITS[plan]["price"]
    
    c.execute("""
        UPDATE users 
        SET proof_status='approved', usage_count=0, price=? 
        WHERE user_id=? AND proof_status='pending'
    """, (price, user_id))
    conn.commit()
    conn.close()
    return f"✅ User {user_id} upgraded to {plan} Plan!"

@flask_app.route('/admin/reject/<user_id>')
@requires_auth
def reject_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET proof_status='rejected' WHERE user_id=? AND proof_status='pending'", (user_id,))
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
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ====== Database Functions ======
def init_db():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    
    # Users table with profile columns
    c.execute("""CREATE TABLE IF NOT EXISTS users (
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
    )""")
    
    # Referrals table
    c.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        inviter_id TEXT,
        invited_id TEXT,
        timestamp TEXT
    )
    """)
    
    # Habits table
    c.execute("""
    CREATE TABLE IF NOT EXISTS habits (
        user_id TEXT,
        habit TEXT,
        created_at TEXT
    )
    """)
    
    # Migration for missing columns
    for col in ["proof_status", "proof_file_id", "price", "proof_timestamp", 
                "goals", "weaknesses", "dream", "career", "money_mindset", "relationship"]:
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
    c.execute("""
        INSERT OR REPLACE INTO users (
            user_id, plan, usage_count, proof_status, proof_file_id,
            price, proof_timestamp,
            goals, weaknesses, dream, career, money_mindset, relationship
        ) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, plan, 0, "none", None,
        price, None,
        None, None, None, None, None, None
    ))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("""
        SELECT plan, usage_count, proof_status, proof_file_id, price, proof_timestamp,
               goals, weaknesses, dream, career, money_mindset, relationship 
        FROM users WHERE user_id=?
    """, (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_profile(user_id, field, value):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
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
    c.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?", (user_id,))
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
        c.execute("UPDATE users SET usage_count=? WHERE user_id=?", (new_usage, inviter_id))
        
        c.execute("""
            INSERT INTO referrals (inviter_id, invited_id, timestamp)
            VALUES (?, ?, ?)
        """, (inviter_id, invited_id, datetime.utcnow().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info(f"🎁 Referral reward (50 calls): inviter={inviter_id}, invited={invited_id}")
    except Exception as e:
        logger.error(f"❌ Referral reward error: {e}")

def get_referral_count(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

# ====== Habits ======
def add_habit(user_id, habit_text):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("INSERT INTO habits (user_id, habit, created_at) VALUES (?, ?, ?)",
              (user_id, habit_text, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_habits(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT habit, created_at FROM habits WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user_id,))
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

async def ask_model(prompt):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "fallbacks": ["gpt-4o-mini", "claude-3.5-sonnet"],
                "max_tokens": 500,
                "temperature": 0.85
            }
        )
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"].strip()
        elif "error" in result:
            raise Exception(result["error"]["message"])
        else:
            raise Exception("Unexpected API response: " + str(result))

async def send_daily_coaching(bot):
    """Send daily coaching message to all premium_plus users"""
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
            message = "🌅 ဒီနေ့အတွက် အကောင်းဆုံး နေ့တစ်နေ့ ဖြစ်ပါစေ။ သင့်ရဲ့ အိပ်မက်တွေကို ယုံကြည်ပြီး ဆက်လက်လုပ်ဆောင်ပါ။"
        
        sent = 0
        for user in users:
            try:
                await bot.send_message(
                    chat_id=int(user[0]),
                    text=f"🔥 **Daily Coaching Message**\n\n{message}"
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
    logger.info("⏰ Scheduler started. Reset usage every 30 days, daily coaching at 8:00 AM.")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

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
        "သင့်ရဲ့ လက်ထောက် အဖြစ်နဲ့ ကိုယ်ရေးကိုယ်တာ၊ အလုပ်အကိုင်နဲ့ တခြားလုပ်ဆောင်ရမယ့် အရာတွေကို ယုံကြည်စွာ ဖြေရှင်းပေးဖို့ အသင့်ပါဗျ။\n\n"
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
        "💡 သိကောင်းစရာ: အခမဲ့ သုံးချင်ရင် `free` နှိပ်ပါ။"
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
        [InlineKeyboardButton("📌 Free", callback_data="sub_free")],
        [InlineKeyboardButton("⭐ Basic (10,000 MMK)", callback_data="sub_basic")],
        [InlineKeyboardButton("💎 Premium (30,000 MMK)", callback_data="sub_premium")],
        [InlineKeyboardButton("👑 Premium+ (50,000 MMK) - VIP Coaching", callback_data="sub_premium_plus")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📌 သင် ရွေးချင်တဲ့ Plan ကို ရွေးပါ။\n\n"
        f"📊 Free: {PLAN_LIMITS['free']['limit']} ကြိမ် (အခမဲ့)\n"
        f"📊 Basic: {PLAN_LIMITS['basic']['limit']} ကြိမ် (10,000 MMK)\n"
        f"📊 Premium: {PLAN_LIMITS['premium']['limit']} ကြိမ် (30,000 MMK)\n"
        f"👑 Premium+: {PLAN_LIMITS['premium_plus']['limit']} ကြိမ် (50,000 MMK) - VIP Coaching",
        reply_markup=reply_markup
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
            (plan, PLAN_LIMITS[plan]["price"], user_id)
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

    plan, usage, proof_status, _, price, _, goals, weaknesses, dream, career, money_mindset, relationship = user
    limit = PLAN_LIMITS[plan]["limit"]
    remaining = limit - usage
    price_usd = get_price_usd(price)
    ref_count = get_referral_count(user_id)

    profile_preview = ""
    if goals or career or money_mindset or dream or weaknesses or relationship:
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
            await update.message.reply_text(answer[i:i+4000], disable_web_page_preview=True)
    else:
        await update.message.reply_text(answer, disable_web_page_preview=True)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /profile <field> : <value>\n"
            "Example: /profile goals : ၃ နှစ်အတွင်း ကိုယ်ပိုင်လုပ်ငန်းဖွင့်မယ်"
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
        await update.message.reply_text("❌ field မမှန်ပါ။ goals/weaknesses/dream/career/money_mindset/relationship ထဲက တစ်ခုသုံးပါ။")
        return
    
    update_profile(user_id, key, value)
    await update.message.reply_text(f"✅ `{key}` ကို update လုပ်ပြီးပါပြီ။")

async def habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /habit <habit>\nExample: /habit နေ့တိုင်း ၃၀ မိနစ်စာဖတ်မယ်")
        return
    habit_text = " ".join(context.args)
    add_habit(user_id, habit_text)
    await update.message.reply_text(f"✅ Habit သိမ်းပြီးပါပြီ:\n- {habit_text}")

async def myhabits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    habits = get_habits(user_id)
    if not habits:
        await update.message.reply_text("📭 Habit မရှိသေးပါ။ /habit နဲ့ အသစ်ထည့်ပါ။")
        return
    lines = ["📋 **Your Recent Habits**"]
    for h, ts in habits:
        lines.append(f"• {h} ({ts[:10]})")
    await update.message.reply_text("\n".join(lines))

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
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
    for user in users:
        try:
            await context.bot.send_message(chat_id=int(user[0]), text=f"📢 **Broadcast**\n\n{message}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send to {user[0]}: {e}")
    
    await update.message.reply_text(f"✅ Broadcast sent to {sent} users.")

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /verify <user_id> <plan>")
        return
    
    target_user = context.args[0]
    plan = context.args[1]
    
    if plan not in PLAN_LIMITS:
        allowed = ", ".join(PLAN_LIMITS.keys())
        await update.message.reply_text(f"❌ Invalid plan. Allowed: {allowed}")
        return
    
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    price = PLAN_LIMITS[plan]["price"]
    c.execute("UPDATE users SET plan=?, usage_count=0, price=? WHERE user_id=?", (plan, price, target_user))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ User {target_user} upgraded to {plan} plan!")

# ====== Proof System ======
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    photo = update.message.photo[-1].file_id
    timestamp = update.message.date
    
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    
    # Duplicate proof check
    c.execute("SELECT user_id FROM users WHERE proof_file_id=? AND user_id!=?", (photo, user_id))
    duplicate = c.fetchone()
    if duplicate:
        conn.close()
        await update.message.reply_text(
            "⚠️ ဒီ Screenshot ကို အခြားသူတစ်ယောက်ကလည်း သုံးထားပါတယ်။ "
            "Fraud ဖြစ်နိုင်ပါတယ်။ Proof အသစ်တင်ပေးပါ။"
        )
        return
    
    # Timestamp check (48 hours)
    if timestamp < datetime.utcnow() - timedelta(hours=48):
        conn.close()
        await update.message.reply_text(
            "⚠️ Proof screenshot ဟာ 48 နာရီကျော်ပြီးသား ဖြစ်နေပါတယ်။ "
            "အသစ်တင်ပေးပါ။"
        )
        return
    
    # Ensure user exists
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
    
    # Save proof
    c.execute("""
        UPDATE users 
        SET proof_file_id=?, proof_status='pending', proof_timestamp=? 
        WHERE user_id=?
    """, (photo, timestamp.isoformat(), user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("📸 Proof လက်ခံပြီးပါပြီ။ Admin စစ်ဆေးနေပါမယ်။")
    
    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"📋 User {user_id} က Proof တင်လိုက်ပါပြီ။\n⏰ {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo,
                caption=f"Proof from User {user_id}\n\nအတည်ပြုရန်: /approve_proof {user_id}\nပယ်ရန်: /reject_proof {user_id}"
            )
        except Exception as e:
            logger.error(f"Admin notification error for {admin_id}: {e}")

async def pending_proofs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, proof_file_id, proof_timestamp FROM users WHERE proof_status='pending'")
    results = c.fetchall()
    conn.close()
    if not results:
        await update.message.reply_text("📭 Pending proof မရှိပါ။")
        return
    msg = "📋 Pending Proofs:\n"
    for uid, fid, ts in results:
        msg += f"• User `{uid}` → {ts[:16] if ts else 'N/A'}...\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def approve_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve_proof <user_id>")
        return
    
    target_user = context.args[0]
    user_data = get_user(target_user)
    if not user_data:
        await update.message.reply_text(f"❌ User `{target_user}` မတွေ့ပါ။")
        return
    plan = user_data[0]
    price = PLAN_LIMITS[plan]["price"]
    
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("""UPDATE users 
                 SET proof_status='approved', usage_count=0, price=? 
                 WHERE user_id=? AND proof_status='pending'""",
              (price, target_user))
    if c.rowcount == 0:
        await update.message.reply_text(f"❌ User `{target_user}` မတွေ့ပါ သို့မဟုတ် pending မဟုတ်ပါ။")
        conn.close()
        return
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ User `{target_user}` ရဲ့ Proof အတည်ပြုပြီး **{plan}** Plan ကို အဆင့်မြှင့်ပေးလိုက်ပါပြီ။")
    try:
        await context.bot.send_message(chat_id=int(target_user),
                                       text=f"🎉 သင့် Proof အတည်ပြုပြီး **{plan}** Plan ရရှိပါပြီ။")
    except Exception as e:
        logger.error(f"Failed to notify user {target_user}: {e}")

async def reject_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /reject_proof <user_id>")
        return
    target_user = context.args[0]
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET proof_status='rejected' WHERE user_id=? AND proof_status='pending'", (target_user,))
    if c.rowcount == 0:
        await update.message.reply_text(f"❌ User `{target_user}` မတွေ့ပါ သို့မဟုတ် pending မဟုတ်ပါ။")
        conn.close()
        return
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ User `{target_user}` Proof ကို Reject လုပ်ပြီးပါပြီ။")
    try:
        await context.bot.send_message(chat_id=int(target_user),
                                       text="⚠️ သင့် Proof ကို ငြင်းပယ်ခံရပါသည်။ ပြန်လည်တင်ပေးပါ။")
    except Exception as e:
        logger.error(f"Failed to notify user {target_user}: {e}")

# ====== Auto Subscribe via text message ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    original_text = update.message.text
    user_text_lower = original_text.lower()
    
    if user_text_lower in ["free", "basic", "premium", "premium_plus"]:
        context.args = [user_text_lower]
        await subscribe(update, context)
        return
    
    user_id = str(update.effective_user.id)
    if not check_limit(user_id):
        await update.message.reply_text("❌ သုံးခွင့်ကုန်သွားပါပြီ။ Plan အသစ်ရွေးပါ။")
        return
    
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    try:
        answer = await ask_model(original_text)
        answer = clean_text(answer)
    except Exception as e:
        logger.error(f"Handle message error for user {user_id}: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
        return
    
    increment_usage(user_id)
    bot_name = get_bot_name(original_text)
    if bot_name:
        answer = f"{bot_name} ပြောတယ်... {answer}"
    
    await update.message.reply_text(answer, disable_web_page_preview=True)

# ====== Main ======
def main():
    init_db()
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add all handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("habit", habit))
    app.add_handler(CommandHandler("myhabits", myhabits))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("pending_proofs", pending_proofs))
    app.add_handler(CommandHandler("approve_proof", approve_proof))
    app.add_handler(CommandHandler("reject_proof", reject_proof))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Bot ready and polling started!")
    
    # Scheduler thread with bot instance
    scheduler_thread = threading.Thread(target=run_scheduler, args=(app.bot,), daemon=True)
    scheduler_thread.start()
    logger.info("🔄 Scheduler thread started.")
    
    # Flask thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask server thread started.")
    
    # Run bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
