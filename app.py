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

# ====== Exchange Rate ======
EXCHANGE_RATE = 4545

PAYMENT_INFO = "💳 **ငွေလွှဲရန်**\nKBZPay: 09426419462\nWavePay: 09426419462"

PLAN_LIMITS = {
    "free": {"limit": 50, "price": 0},
    "basic": {"limit": 500, "price": 10000},
    "premium": {"limit": 1500, "price": 30000}
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
    
    # Total users
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    # Plan distribution
    c.execute("SELECT plan, COUNT(*) FROM users GROUP BY plan")
    plan_stats = c.fetchall()
    
    # Pending proofs
    c.execute("SELECT COUNT(*) FROM users WHERE proof_status='pending'")
    pending = c.fetchone()[0]
    
    # Today's usage
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
    
    # Users table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        plan TEXT DEFAULT 'free',
        usage_count INTEGER DEFAULT 0,
        proof_status TEXT DEFAULT 'none',
        proof_file_id TEXT,
        price INTEGER DEFAULT 0,
        proof_timestamp TEXT
    )""")
    
    # Referrals table
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        inviter_id TEXT,
        invited_id TEXT,
        timestamp TEXT,
        reward_given INTEGER DEFAULT 0,
        PRIMARY KEY (inviter_id, invited_id)
    )""")
    
    # Migration for missing columns
    try:
        c.execute("ALTER TABLE users ADD COLUMN proof_status TEXT DEFAULT 'none'")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN proof_file_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN price INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN proof_timestamp TEXT")
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
        INSERT OR REPLACE INTO users (user_id, plan, usage_count, proof_status, proof_file_id, price, proof_timestamp) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, plan, 0, "none", None, price, None))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT plan, usage_count, proof_status, proof_file_id, price, proof_timestamp FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def check_limit(user_id):
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
        return True
    plan, usage, _, _, _, _ = user
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

def get_inviter_id(ref_code):
    # Extract user_id from REF12345 format
    if ref_code.startswith("REF"):
        try:
            return ref_code[3:]  # Remove "REF"
        except:
            return None
    return None

def record_referral(inviter_id, invited_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    timestamp = datetime.utcnow().isoformat()
    c.execute("""
        INSERT OR IGNORE INTO referrals (inviter_id, invited_id, timestamp, reward_given)
        VALUES (?, ?, ?, ?)
    """, (inviter_id, invited_id, timestamp, 0))
    conn.commit()
    conn.close()

def get_referral_count(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def give_referral_reward(inviter_id):
    # Add 10 free uses to inviter
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET usage_count = usage_count - 10 WHERE user_id=?", (inviter_id,))
    c.execute("UPDATE referrals SET reward_given=1 WHERE inviter_id=? AND reward_given=0", (inviter_id,))
    conn.commit()
    conn.close()

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

def run_scheduler():
    schedule.every(30).days.do(reset_usage)
    # Daily motivation auto-send (Feature 3)
    schedule.every().day.at("08:00").do(send_daily_motivation)
    logger.info("⏰ Scheduler started.")
    while True:
        schedule.run_pending()
        time.sleep(60)

def send_daily_motivation():
    """Auto send daily motivation to all users"""
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    
    for user in users:
        try:
            # This would need bot instance - simplified for now
            logger.info(f"Daily motivation sent to {user[0]}")
        except Exception as e:
            logger.error(f"Failed to send motivation to {user[0]}: {e}")

# ====== OpenRouter AI Call ======
system_prompt = (
    "သင်ဟာ မစ္စတာသန်း (Mr.T) — funny, friendly, motivational AI Bot ဖြစ်ပါတယ်။ "
    "Than ကို မိတ်ဆွေလို ပြောပါ။ ရယ်စရာလေးတွေ ထည့်ပါ။ "
    "အဖြေတွေကို မြန်မာလိုပဲ ပြန်ပါ။ "
    "Money Mindset Mode: online income, skill တိုးတက်, money mindset, side hustle, motivation, action plan "
    "အကြံပေးပါ။ Risky trading, guaranteed profit, illegal methods မပြောပါနဲ့။ "
    "Attractive Personality Mode: self-confidence, communication skill, social skill, relationship advice "
    "healthy, respectful, confidence-building advice ပေးပါ။ "
    "Personality: Than ကို motivate လုပ်ပါ။ Funny tone, friendly tone နဲ့ ပြန်ပါ။"
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

# ====== Telegram Bot Command Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    # ====== Referral System: Check if /start REF12345 ======
    if text.startswith("/start REF"):
        ref_code = text.split(" ")[0].replace("/start", "").strip() if len(text.split(" ")) > 0 else text.replace("/start", "").strip()
        inviter_id = get_inviter_id(ref_code)
        
        if inviter_id and inviter_id != user_id:
            # Record referral
            record_referral(inviter_id, user_id)
            give_referral_reward(inviter_id)
            
            await update.message.reply_text(
                "🎉 ခင်ဗျားကို အခြားသူတစ်ယောက်က referral link နဲ့ ခေါ်လာတာပါ။\n"
                "သူ့အတွက် ကျေးဇူးပါ။ ခင်ဗျားလည်း သူငယ်ချင်းတွေကို ဖိတ်လို့ရပါတယ်။\n"
                "/referral - သင့် referral link ရယူရန်"
            )
        else:
            await update.message.reply_text("⚠️ Invalid referral code.")
    
    # Normal start
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
    
    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် မစ္စတာသန်းပါ။\n"
        "သင့်ရဲ့ လက်ထောက် အဖြစ်နဲ့ ကိုယ်ရေးကိုယ်တာ၊ အလုပ်အကိုင်နဲ့ တခြားလုပ်ဆောင်ရမယ့် အရာတွေကို ယုံကြည်စွာ ဖြေရှင်းပေးဖို့ အသင့်ပါဗျ။\n\n"
        "Commands:\n"
        "/subscribe <plan> - Plan ပြောင်းရန် (free/basic/premium)\n"
        "/ask <question> - AI ကို မေးမြန်းရန်\n"
        "/status - ကိုယ့် Plan နှင့် သုံးခွင့်အကြွင်းကို ကြည့်ရန်\n"
        "/proof - Screenshot proof တင်ရန် (Photo ပို့ပါ)\n"
        "/referral - သင့် referral link ရယူရန်\n"
        "/help - အကူအညီ\n\n"
        "💡 သိကောင်းစရာ: အခမဲ့ သုံးချင်ရင် `free` နှိပ်ပါ၊ ပိုမိုအဆင့်မြင့်စွာ လုပ်ဆောင်စေချင်ရင် `basic` သို့မဟုတ် `premium` ကိုရွေးပြီး သုံးပါ။"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 **အသုံးပြုနည်း**\n\n"
        "/start - ဘော့စတင်\n"
        "/help - အကူအညီ\n"
        "/subscribe <plan> - Plan ပြောင်းရန် (free/basic/premium)\n"
        "/ask <question> - AI ကို မေးမြန်းရန်\n"
        "/status - ကိုယ့် Plan နှင့် သုံးခွင့်အကြွင်းကို ကြည့်ရန်\n"
        "/proof - Screenshot proof တင်ရန် (Photo ပို့ပါ)\n"
        "/referral - သင့် referral link ရယူရန်\n\n"
        "**Admin Commands:**\n"
        "/verify <user_id> <plan> - Plan ပြောင်းရန်\n"
        "/pending_proofs - Pending Proofs စာရင်းကြည့်ရန်\n"
        "/approve_proof <user_id> - Proof အတည်ပြုရန်\n"
        "/reject_proof <user_id> - Proof ပယ်ရန်\n"
        "/broadcast <message> - အားလုံးကို message ပို့ရန်\n\n"
        "💡 **Auto Subscribe:** `free`, `basic`, `premium` လို့ရိုက်ရင် အလိုအလျောက် subscribe လုပ်ပေးမယ်။"
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
        "✨ သူငယ်ချင်းတွေကို ဖိတ်လိုက်ပါ။ သင် **10 ကြိမ် free usage** ရပါမယ်။"
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    plan = context.args[0] if context.args else "free"
    
    if plan not in PLAN_LIMITS:
        allowed = ", ".join(PLAN_LIMITS.keys())
        await update.message.reply_text(f"❌ '{plan}' မရှိပါ။ ရနိုင်တဲ့ Plan: {allowed}")
        return
    
    # Inline Keyboard for plan selection (Feature 1)
    keyboard = [
        [
            InlineKeyboardButton("📌 Free", callback_data="sub_free"),
            InlineKeyboardButton("⭐ Basic (10,000 MMK)", callback_data="sub_basic")
        ],
        [
            InlineKeyboardButton("💎 Premium (30,000 MMK)", callback_data="sub_premium")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📌 သင် ရွေးချင်တဲ့ Plan ကို ရွေးပါ။\n\n"
        f"📊 Free: {PLAN_LIMITS['free']['limit']} ကြိမ် (အခမဲ့)\n"
        f"📊 Basic: {PLAN_LIMITS['basic']['limit']} ကြိမ် (10,000 MMK)\n"
        f"📊 Premium: {PLAN_LIMITS['premium']['limit']} ကြိမ် (30,000 MMK)",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data = query.data
    
    if data.startswith("sub_"):
        plan = data.replace("sub_", "")
        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()
        c.execute("UPDATE users SET plan=?, proof_status='waiting', price=? WHERE user_id=?",
                  (plan, PLAN_LIMITS[plan]["price"], user_id))
        conn.commit()
        conn.close()
        
        price_mmk = PLAN_LIMITS[plan]["price"]
        price_usd = get_price_usd(price_mmk)
        
        await query.edit_message_text(
            f"📌 **{plan}** Plan ကို ရွေးလိုက်ပါပြီ။\n"
            f"💰 စျေးနှုန်း: {price_mmk:,} MMK (~${price_usd}) / month\n\n"
            f"📸 ကျေးဇူးပြုပြီး ငွေသွင်း proof screenshot ကို ပို့ပါ။\n\n"
            f"{PAYMENT_INFO}"
        )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
        user = ("free", 0, "none", None, 0, None)
    plan, usage, proof_status, _, price, proof_timestamp = user
    limit = PLAN_LIMITS[plan]["limit"]
    remaining = limit - usage
    price_usd = get_price_usd(price)
    
    # Referral count
    ref_count = get_referral_count(user_id)
    
    await update.message.reply_text(
        f"📊 **Your Status**\n"
        f"📌 Plan: **{plan}**\n"
        f"💰 စျေးနှုန်း: {price:,} MMK (~${price_usd}) / month\n"
        f"📊 သုံးပြီးသား: {usage} / {limit} ကြိမ်\n"
        f"✅ ကျန်သုံးခွင့်: **{remaining}** ကြိမ်\n"
        f"🔍 Proof Status: **{proof_status}**\n"
        f"👥 ဖိတ်ထားသူ: **{ref_count}** ယောက်"
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
            await asyncio.sleep(0.05)  # Avoid rate limit
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
    
    # ====== 1. Duplicate Proof Check ======
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE proof_file_id=? AND user_id!=?", (photo, user_id))
    duplicate = c.fetchone()
    
    if duplicate:
        conn.close()
        await update.message.reply_text(
            "⚠️ ဒီ Screenshot ကို အခြားသူတစ်ယောက်ကလည်း သုံးထားပါတယ်။ "
            "Fraud ဖြစ်နိုင်ပါတယ်။ Proof အသစ်တင်ပေးပါ။"
        )
        return
    
    # ====== 2. Timestamp Check (48 hours) ======
    if timestamp < datetime.utcnow() - timedelta(hours=48):
        conn.close()
        await update.message.reply_text(
            "⚠️ Proof screenshot ဟာ 48 နာရီကျော်ပြီးသား ဖြစ်နေပါတယ်။ "
            "အသစ်တင်ပေးပါ။"
        )
        return
    
    # ====== 3. Save to Database ======
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
    
    c.execute("""
        UPDATE users 
        SET proof_file_id=?, proof_status='pending', proof_timestamp=? 
        WHERE user_id=?
    """, (photo, timestamp.isoformat(), user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("📸 Proof လက်ခံပြီးပါပြီ။ Admin စစ်ဆေးနေပါမယ်။")
    
    # ====== 4. Notify All Admins ======
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
    plan, _, _, _, _, _ = user_data
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
    
    if user_text_lower in ["free", "basic", "premium"]:
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

# ====== Run Bot ======
def run_bot():
    logger.info("🤖 Bot starting...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("pending_proofs", pending_proofs))
    app.add_handler(CommandHandler("approve_proof", approve_proof))
    app.add_handler(CommandHandler("reject_proof", reject_proof))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ Bot ready and polling started!")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.run_polling(allowed_updates=Update.ALL_TYPES))

# ====== Run Flask ======
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# ====== Main ======
if __name__ == "__main__":
    init_db()
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("🔄 Scheduler thread started.")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask server thread started.")
    
    run_bot()
