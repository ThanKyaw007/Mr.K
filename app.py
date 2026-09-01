import os
import re
import sqlite3
import threading
import asyncio
import httpx
from flask import Flask, request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====== Configuration ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or "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"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "mysecret123"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ADMIN_ID = 123456789  # မင်း Telegram ID ထည့်ပါ

# ---- Plan Limits ----
PLAN_LIMITS = {
    "free": {"limit": 50, "price": 0},
    "basic": {"limit": 500, "price": 10000},
    "premium": {"limit": 1500, "price": 30000}
}

BOT_NAMES = ["မစ္စတာသန်း"]

# ====== Flask App ======
flask_app = Flask(__name__)

# ====== Auth Functions ======
def check_auth(password):
    return password == ADMIN_PASSWORD

def authenticate():
    return Response(
        "❌ Unauthorized! Password required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ====== Flask Routes ======
@flask_app.route('/')
def home():
    return "🤖 Bot is running!"

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
    
    html = """
    <html>
    <head><title>📋 Proofs Dashboard</title></head>
    <body>
    <h2>📋 Proofs Dashboard</h2>
    <table border='1' cellpadding='5' style='border-collapse:collapse;'>
    <tr><th>User ID</th><th>Plan</th><th>Usage</th><th>Proof Status</th><th>File ID</th><th>Actions</th></tr>
    """
    for uid, plan, usage, status, file_id in results:
        html += f"<tr><td>{uid}</td><td>{plan}</td><td>{usage}</td><td>{status}</td><td>{file_id[:20] if file_id else '-'}...</td>"
        if status == "pending":
            html += f"<td><a href='/admin/approve/{uid}'>✅ Approve</a> | <a href='/admin/reject/{uid}'>❌ Reject</a></td>"
        else:
            html += "<td>-</td>"
        html += "</tr>"
    html += "</table></body></html>"
    return html

@flask_app.route('/admin/approve/<user_id>')
@requires_auth
def approve_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    price = PLAN_LIMITS["premium"]["price"]
    c.execute("""UPDATE users 
                 SET proof_status='approved', plan='premium', usage_count=0, price=? 
                 WHERE user_id=? AND proof_status='pending'""",
              (price, user_id))
    conn.commit()
    conn.close()
    return f"✅ User {user_id} upgraded to Premium!"

@flask_app.route('/admin/reject/<user_id>')
@requires_auth
def reject_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET proof_status='rejected' WHERE user_id=? AND proof_status='pending'", (user_id,))
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
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        plan TEXT,
        usage_count INTEGER,
        proof_status TEXT DEFAULT 'none',
        proof_file_id TEXT,
        price INTEGER DEFAULT 0
    )""")
    # Migration for existing columns
    for col in ["proof_status", "proof_file_id", "price"]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT 'none'")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def add_user(user_id, plan="free"):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    price = PLAN_LIMITS[plan]["price"]
    c.execute("""INSERT OR REPLACE INTO users 
                 (user_id, plan, usage_count, proof_status, proof_file_id, price) 
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (user_id, plan, 0, "none", None, price))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT plan, usage_count, proof_status, proof_file_id, price FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def check_limit(user_id):
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
        return True
    plan, usage, _, _, _ = user
    if usage >= PLAN_LIMITS[plan]["limit"]:
        return False
    return True

def increment_usage(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

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
        return result["choices"][0]["message"]["content"].strip()

# ====== Telegram Bot Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
    await update.message.reply_text(
        f"🙏 မင်္ဂလာပါ {update.effective_user.first_name}။\n"
        "Commands:\n"
        "/subscribe <plan> - Plan ပြောင်းရန် (free/basic/premium)\n"
        "/ask <question> - AI ကို မေးမြန်းရန်\n"
        "/status - ကိုယ့် Plan နှင့် သုံးခွင့်အကြွင်းကို ကြည့်ရန်\n"
        "/help - အကူအညီ"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Commands:\n"
        "/start - စတင်ရန်\n"
        "/help - အကူအညီ\n"
        "/subscribe <plan> - Plan ပြောင်းရန် (free/basic/premium)\n"
        "/ask <question> - AI မေးမြန်းရန်\n"
        "/status - ကိုယ့် Status ကြည့်ရန်\n"
        "/verify <user_id> <plan> - (Admin Only)\n"
        "/pending_proofs - (Admin Only)\n"
        "/approve_proof <user_id> - (Admin Only)\n"
        "/reject_proof <user_id> - (Admin Only)"
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    plan = context.args[0] if context.args else "free"
    
    if plan not in PLAN_LIMITS:
        allowed = ", ".join(PLAN_LIMITS.keys())
        await update.message.reply_text(f"❌ '{plan}' မရှိပါ။ ရနိုင်တဲ့ Plan: {allowed}")
        return
    
    add_user(user_id, plan)
    price = PLAN_LIMITS[plan]["price"]
    limit = PLAN_LIMITS[plan]["limit"]
    
    await update.message.reply_text(
        f"✅ **{plan}** Plan ကို အောင်မြင်စွာ Subscribe လုပ်ပြီးပါပြီ။\n"
        f"💰 စျေးနှုန်း: {price} MMK / month\n"
        f"📊 သုံးခွင့်: {limit} ကြိမ်"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    if not user:
        add_user(user_id, "free")
        user = ("free", 0, "none", None, 0)
    plan, usage, proof_status, _, price = user
    limit = PLAN_LIMITS[plan]["limit"]
    remaining = limit - usage
    
    await update.message.reply_text(
        f"📊 **Your Status**\n"
        f"📌 Plan: **{plan}**\n"
        f"💰 စျေးနှုန်း: {price} MMK / month\n"
        f"📊 သုံးပြီးသား: {usage} / {limit} ကြိမ်\n"
        f"✅ ကျန်သုံးခွင့်: **{remaining}** ကြိမ်\n"
        f"📸 Proof Status: **{proof_status}**"
    )

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not check_limit(user_id):
        await update.message.reply_text("❌ သုံးခွင့်ကုန်သွားပါပြီ။ /subscribe နဲ့ Plan အသစ်ရွေးပါ။")
        return
    
    if not context.args:
        await update.message.reply_text("❌ မေးခွန်းထည့်ပါ။ Usage: /ask <question>")
        return
    
    question = " ".join(context.args)
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        answer = await ask_model(question)
        answer = clean_text(answer)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
        return
    
    increment_usage(user_id)
    await update.message.reply_text(answer, disable_web_page_preview=True)

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /verify <user_id> <plan>")
        return
    target_user = context.args[0]
    plan = context.args[1]
    if plan not in PLAN_LIMITS:
        await update.message.reply_text("❌ Invalid plan")
        return
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET plan=?, usage_count=0 WHERE user_id=?", (plan, target_user))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ User {target_user} upgraded to {plan}!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    file_id = update.message.photo[-1].file_id
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET proof_status=?, proof_file_id=? WHERE user_id=?",
              ("pending", file_id, user_id))
    conn.commit()
    conn.close()
    await update.message.reply_text("📸 Proof လက်ခံပြီးပါပြီ။ Admin စစ်ဆေးနေပါမယ်။")

async def pending_proofs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, proof_file_id FROM users WHERE proof_status='pending'")
    results = c.fetchall()
    conn.close()
    if not results:
        await update.message.reply_text("📭 Pending proof မရှိပါ။")
        return
    msg = "📋 Pending Proofs:\n"
    for uid, fid in results:
        msg += f"• `{uid}` → {fid[:20]}...\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def approve_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve_proof <user_id>")
        return
    target_user = context.args[0]
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    price = PLAN_LIMITS["premium"]["price"]
    c.execute("""UPDATE users 
                 SET proof_status='approved', plan='premium', usage_count=0, price=? 
                 WHERE user_id=? AND proof_status='pending'""",
              (price, target_user))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ User `{target_user}` Premium သို့ အဆင့်မြှင့်ပြီးပါပြီ။")
    try:
        await context.bot.send_message(
            chat_id=int(target_user),
            text="🎉 သင့် Proof ကို အတည်ပြုပြီး Premium Plan ကို ရရှိပါပြီ။"
        )
    except Exception:
        pass

async def reject_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /reject_proof <user_id>")
        return
    target_user = context.args[0]
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET proof_status='rejected' WHERE user_id=?", (target_user,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ User `{target_user}` Proof ကို Reject လုပ်ပြီးပါပြီ။")
    try:
        await context.bot.send_message(
            chat_id=int(target_user),
            text="⚠️ သင့် Proof ကို ငြင်းပယ်ခံရပါသည်။ ပြန်လည်တင်ပေးပါ။"
        )
    except Exception:
        pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text
    bot_name = get_bot_name(user_message)
    
    if not check_limit(user_id):
        await update.message.reply_text("❌ သုံးခွင့်ကုန်သွားပါပြီ။ /subscribe နဲ့ Plan အသစ်ရွေးပါ။")
        return
    
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        answer = await ask_model(user_message)
        answer = clean_text(answer)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
        return
    
    if bot_name:
        answer = f"{bot_name} ပြောတယ်... {answer}"
    
    increment_usage(user_id)
    await update.message.reply_text(answer, disable_web_page_preview=True)

# ====== Run Bot ======
def run_bot():
    print("🤖 Bot starting...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("pending_proofs", pending_proofs))
    app.add_handler(CommandHandler("approve_proof", approve_proof))
    app.add_handler(CommandHandler("reject_proof", reject_proof))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot ready!")
    
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
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    run_bot()
