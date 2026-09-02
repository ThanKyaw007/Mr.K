import os
import re
import json
import sqlite3
import threading
import asyncio
import httpx
import functools
import logging
import schedule
import time
from datetime import datetime
from flask import Flask, request, Response, send_file
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

ADMIN_IDS = [1119128553]
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mysecret123")

ADMIN_USERS = {
    "admin": "mysecret123",
    "thawkhyan": "yourpass123",
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

def check_auth(username, password):
    return username in ADMIN_USERS and ADMIN_USERS[username] == password

def authenticate():
    return Response(
        "❌ Unauthorized! Username and Password required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )

def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ====== Flask Routes ======
@flask_app.route("/")
def home():
    return "🤖 Bot is running! Visit /admin/proofs for dashboard."

@flask_app.route("/health")
def health():
    return "OK", 200

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

    plan_names = [row[0] for row in plan_stats]
    plan_counts = [row[1] for row in plan_stats]

    html = f"""
    <h2>📊 Bot Statistics</h2>
    <p><b>Total Users:</b> {total_users}</p>
    <p><b>Pending Proofs:</b> {pending}</p>
    <p><b>Total API Calls:</b> {total_usage}</p>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <div style="width: 500px; height: 350px; margin: 20px auto;">
        <canvas id="planChart"></canvas>
    </div>

    <script>
        const ctx = document.getElementById('planChart').getContext('2d');
        const chart = new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(plan_names)},
                datasets: [{{
                    label: 'အသုံးပြုသူ အရေအတွက်',
                    data: {json.dumps(plan_counts)},
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{ scales: {{ y: {{ beginAtZero: true }} }} }}
        }});
    </script>
    """
    return html

@flask_app.route("/download_db")
@requires_auth
def download_db():
    try:
        return send_file("bot_users.db", as_attachment=True)
    except Exception as e:
        return f"Error: {e}"

@flask_app.route("/admin/approve/<user_id>")
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
    c.execute(
        "UPDATE users SET proof_status='approved', usage_count=0, price=? WHERE user_id=? AND proof_status='pending'",
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

# ====== Database Backup Function ======
def backup_and_send(bot):
    try:
        conn = sqlite3.connect("bot_users.db")
        with open("bot_users_backup.db", "w", encoding='utf-8') as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()
        
        with open("bot_users_backup.db", "rb") as f:
            bot.send_document(
                chat_id=ADMIN_IDS[0],
                document=f,
                caption=f"📦 Database Backup - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        
        os.remove("bot_users_backup.db")
        logger.info("✅ Database backup sent to admin")
    except Exception as e:
        logger.error(f"❌ Backup error: {e}")

# ====== Database Functions ======
def init_db():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
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
        relationship TEXT,
        birthdate TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        inviter_id TEXT, invited_id TEXT, timestamp TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS habits (
        user_id TEXT, habit TEXT, created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS response_cache (
        query TEXT PRIMARY KEY,
        response TEXT,
        created_at TEXT
    )""")
    for col in ["proof_status", "proof_file_id", "price", "proof_timestamp", "goals", "weaknesses", "dream", "career", "money_mindset", "relationship", "birthdate"]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def add_user(user_id, plan="free"):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    price = PLAN_LIMITS[plan]["price"]
    c.execute("""INSERT OR REPLACE INTO users (user_id, plan, usage_count, proof_status, proof_file_id, price, proof_timestamp, goals, weaknesses, dream, career, money_mindset, relationship, birthdate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (user_id, plan, 0, "none", None, price, None, None, None, None, None, None, None, None))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    # 👇 ဒီထဲမှာ birthdate ထည့်ပြီးသား ဖြစ်အောင် ကူးထည့်ပါ
    c.execute("SELECT plan, usage_count, proof_status, proof_file_id, price, proof_timestamp, goals, weaknesses, dream, career, money_mindset, relationship, birthdate FROM users WHERE user_id=?", (user_id,))
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
    c.execute("UPDATE users SET proof_file_id=?, proof_status='pending', proof_timestamp=? WHERE user_id=?", (file_id, datetime.utcnow().isoformat(), user_id))
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
        c.execute("INSERT INTO referrals (inviter_id, invited_id, timestamp) VALUES (?, ?, ?)", (inviter_id, invited_id, datetime.utcnow().isoformat()))
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
    c.execute("INSERT INTO habits (user_id, habit, created_at) VALUES (?, ?, ?)", (user_id, habit_text, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_habits(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT habit, created_at FROM habits WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user_id,))
    results = c.fetchall()
    conn.close()
    return results

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

# ====== Response Cache (ပိုက်ဆံချွေတာရန်) ======
def get_cached_response(query: str):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT response FROM response_cache WHERE query=?", (query,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def save_cached_response(query: str, response: str):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO response_cache (query, response, created_at) VALUES (?, ?, ?)",
        (query, response, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    
# ====== Local Responses (ပိုက်ဆံချွေတာရန်) ======
LOCAL_RESPONSES = {
    "hello": "ဟယ်လို! မင်္ဂလာပါဗျ။ ဘာကူညီပေးရမလဲ?",
    "hi": "ဟိုင်း! ဒီနေ့ ဘာတွေ လုပ်နေလဲဗျ။",
    "ဟိုင်း": "ဟိုင်း! ဘာမေးချင်လဲဗျ။",
    "မင်္ဂလာပါ": "မင်္ဂလာပါဗျ။ ကြိုဆိုပါတယ်။",
    "နေကောင်းလား": "ကျေးဇူးတင်ပါတယ်၊ ကျွန်တော်ကတော့ အဆင်ပြေပါတယ်။ ခင်ဗျားကရော?",
    "ဘာလုပ်နေလဲ": "ခင်ဗျားကို ကူညီဖို့ စောင့်နေတာပေါ့ဗျာ။",
    "အိမ်မှာလား": "ဟုတ်ကဲ့ဗျ၊ ဒီမှာပါပဲ။ ဘာမေးချင်လဲဗျ။",
    "ဘယ်လိုလဲ": "ကျွန်တော်ကတော့ အဆင်ပြေပါတယ်ဗျ။ ခင်ဗျားကရော?",
    "စားပြီးပြီလား": "ရပါတယ်ဗျ။ မင်းစားပြီးပြီလား?",
    "thanks": "ရပါတယ်ဗျ။ ကျေးဇူးတင်ပါတယ်။",
    "thank you": "ရပါတယ်ဗျ။ ကျေးဇူးတင်ပါတယ်။",
    "ကျေးဇူးတင်ပါတယ်": "အေးပါဗျ။ အားမနာပါနဲ့။",
    "ကျေးဇူး": "အေးပါဗျ။ ကျေးဇူးတင်ပါတယ်။",
    "အဆင်ပြေပါတယ်": "ဝမ်းသာပါတယ်ဗျ။",
    "အင်း": "အင်း ဟုတ်ကဲ့ဗျ။",
    "ဟုတ်": "ဟုတ်ပါတယ်ဗျ။",
    "မဟုတ်ဘူး": "မဟုတ်ဘူးဆိုတော့ ဘာဖြစ်လဲဗျ။",
    "အိုကေ": "အိုကေပါဗျ။",
    "ok": "Okay ပါဗျ။",
    "ကောင်းပြီ": "ကောင်းပါပြီဗျ။",
    "သိပြီ": "သိရင် ဝမ်းသာပါတယ်ဗျ။",
    "မသိဘူး": "မသိရင် ဘာကို သိချင်တာလဲဗျ။",
    "ရပါတယ်": "ရပါတယ်ဗျ။",
    "ဘယ်သူလဲ": "ကျွန်တော်က မစ္စတာသန်း (Mr.T) ပါ။ ခင်ဗျားရဲ့ ကိုယ်ပိုင်အကြံပေးဘော့ပါ။",
    "မင်းကဘာလဲ": "ကျွန်တော်က မစ္စတာသန်း (Mr.T) ပါ။ ခင်ဗျားရဲ့ ကိုယ်ပိုင်အကြံပေးဘော့ပါ။",
    "ဘာလုပ်ပေးနိုင်လဲ": "လုပ်ငန်း၊ နည်းပညာ၊ စိုက်ပျိုးရေး၊ ဗီဒီယို၊ စီးပွားရေး အပါအဝင် အကြံဉာဏ် (၁၆) မျိုး ပေးနိုင်ပါတယ်ဗျ။",
    "ဘာတွေလုပ်ပေးနိုင်လဲ": "ဘဝအကြံဉာဏ်၊ စီးပွားရေး၊ နည်းပညာ၊ ကျန်းမာရေး စသဖြင့် အကုန်ကူညီနိုင်ပါတယ်။",
    "help": "ကူညီမှုအတွက် /help ကို နှိပ်ပါ။",
    "အကူအညီ": "ဘာကူညီပေးရမလဲဗျ။ ဥပမာ - /ask နည်းပညာအကြောင်း",
    "အမိန့်": "Command တွေကို /help မှာ ကြည့်နိုင်ပါတယ်ဗျ။",
    "command": "Command တွေကို /help မှာ ကြည့်နိုင်ပါတယ်ဗျ။",
    "စတင်မယ်": "စတင်လိုက်ပါပြီဗျ။ ဘာမေးမလဲ။",
    "price": "Plan ဈေးနှုန်းတွေကို /subscribe နှိပ်ပြီး ကြည့်နိုင်ပါတယ်ဗျ။",
    "စျေးနှုန်း": "စျေးနှုန်းတွေ သိချင်ရင် /subscribe နှိပ်ပါဗျ။",
    "plan": "Plan တွေက Free, Basic, Premium နဲ့ Premium+ ရှိပါတယ်။ /subscribe နှိပ်ပါ။",
    "ပလန်": "Plan တွေက Free, Basic, Premium နဲ့ Premium+ ရှိပါတယ်။ /subscribe နှိပ်ပါ။",
    "ဘယ်လိုဝယ်ရမလဲ": "Plan ဝယ်ဖို့ဆို /subscribe နှိပ်ပြီး ရွေးပါ၊ ပြီးရင် proof ပို့ပါ။",
    "ငွေလွှဲ": "ငွေလွှဲရန်: KBZPay: 09426419462 | WavePay: 09426419462 ။ ပြီးရင် proof ပို့ပါ။",
    "ပိုက်ဆံ": "ပိုက်ဆံပေးချေမှုအတွက် /subscribe ကို နှိပ်ပါဗျ။",
    "subscribe": "Plan ရွေးရန် အောက်ပါခလုတ်များကို နှိပ်ပါ။",
    "ဝယ်မယ်": "ဝယ်ချင်ရင် /subscribe နှိပ်ပြီး Plan ရွေးပါ။",
    "proof": "ငွေလွှဲပြီးရင် Screenshot ကို ဒီထဲ Photo ပို့ပါ။",
    "ပြေစာ": "ပြေစာဓာတ်ပုံကို ပို့ပေးပါ။",
    "ဗီဒီယိုဖန်တီးနည်း": "ဗီဒီယိုဖန်တီးနည်းအသေးစိတ်၊ Software အကြံပြုချက်တွေကို /ask နဲ့ မေးကြည့်နိုင်ပါတယ်ဗျ။",
    "video editing": "Video editing အကြောင်း သိချင်ရင် /ask မှာ မေးပါ။",
    "capcut": "CapCut အကြောင်း သိချင်ရင် /ask မှာ မေးပါ။",
    "ဒီဇိုင်းဆွဲနည်း": "ဒီဇိုင်းဆွဲနည်းအတွက် /ask မှာ မေးပါဗျ။",
    "စိုက်ပျိုးနည်း": "စိုက်ပျိုးနည်းအသေးစိတ်ကို /ask နဲ့ မေးပါ။",
    "ကြက်မွေးနည်း": "ကြက်မွေးနည်းအသေးစိတ်ကို /ask နဲ့ မေးပါ။",
    "ကွန်ပျူတာပြဿနာ": "ကွန်ပျူတာပြဿနာရှိရင် /ask နဲ့ မေးကြည့်ပါဗျ။",
    "နည်းပညာ": "နည်းပညာအကြံဉာဏ်တွေ လိုချင်ရင် /ask နဲ့ မေးပါ။",
    "ဗေဒင်": "ဗေဒင်မေးချင်ရင် မင်းရဲ့ မွေးနေ့ကို /profile birthdate : <မွေးနေ့> လို့ သိမ်းထားပါ၊ ပြီးရင် /ask မှာ မေးပါ။",
    "ရာသီခွင်": "ရာသီခွင်အကြောင်း (ဥပမာ - မိဿ၊ ပြိဿ စသည်) သိချင်ရင် /ask မှာ မေးပါဗျ။",
    "နက္ခတ်ဗေဒင်": "နက္ခတ်ဗေဒင်အသေးစိတ်ကို /ask မှာ မေးပါ။",
    "မွေးနေ့": "မွေးနေ့နဲ့ ကံကြမ္မာသိချင်ရင် /profile birthdate : <သင့်မွေးနေ့> ထည့်ပြီး /ask မှာ မေးပါ။",
    "ကံကြမ္မာ": "ကံကြမ္မာဖတ်ချင်ရင် မွေးနေ့လိုအပ်လို့ /profile birthdate : <သင့်မွေးနေ့> ထည့်ပါ။",
    "အတိတ်နိမိတ်": "အတိတ်နိမိတ် (ဥပမာ - ကြောင်နှာချေခြင်း၊ ငှက်မြည်ခြင်း) အကြောင်း သိချင်ရင် /ask မှာ မေးပါ။",
    "သိုင်းပညာ": "သိုင်းပညာ၊ ကိုယ်ခံပညာ၊ လက်ဝှေ့အကြောင်း အသေးစိတ်သိချင်ရင် /ask မှာ မေးပါဗျ။",
    "လက်ဝှေ့": "လက်ဝှေ့အနုပညာအကြောင်း အသေးစိတ်ကို /ask မှာ မေးပါ။",
    "ကိုယ်ခံပညာ": "ကိုယ်ခံပညာသင်ဖို့ ဘယ်လိုစမလဲဆိုတာ /ask မှာ မေးပါ။",
    "သိုင်း": "သိုင်းပညာနဲ့ ပတ်သက်ပြီး ဘာသိချင်လဲဗျ။ /ask မှာ မေးကြည့်ပါ။",
    "ကရာတေး": "ကရာတေးအကြောင်း သိချင်ရင် /ask မှာ မေးပါ။",
    "တိုက်ခိုက်နည်း": "တိုက်ခိုက်ရေး၊ ခုခံရေး နည်းပညာတွေအတွက် /ask မှာ မေးပါ။",
    # အားကစား (Sports)
    "အားကစား": "အားကစားနဲ့ ပတ်သက်ပြီး ဘာသိချင်လဲဗျ။ ဘောလုံး၊ ဘတ်စကက်၊ ကြက်တောင် အစရှိတဲ့ /ask မှာ မေးကြည့်ပါ။",
    "ဘောလုံး": "ဘောလုံးအကြောင်း၊ ပွဲစဉ်တွေ၊ နည်းဗျူဟာတွေကို /ask မှာ မေးပါ။",
    "ကြက်တောင်": "ကြက်တောင်ရိုက်နည်း၊ လေ့ကျင့်နည်းတွေကို /ask မှာ မေးပါ။",
    "အပြေး": "အပြေးလေ့ကျင့်နည်း၊ မာရသွန်ပြင်ဆင်နည်းကို /ask မှာ မေးပါ။",
    "fitness": "Fitness နဲ့ ကိုယ်ကာယလေ့ကျင့်ခန်းအကြောင်း /ask မှာ မေးပါ။",
    "အားကစားသမား": "အားကစားသမားတစ်ယောက်ရဲ့ အာဟာရနဲ့ လေ့ကျင့်ခန်းအစီအစဉ်ကို /ask မှာ မေးပါ။",

    # သိုင်းပညာ (Martial Arts)
    "သိုင်းပညာ": "သိုင်းပညာ၊ ကိုယ်ခံပညာ၊ လက်ဝှေ့အကြောင်း အသေးစိတ်သိချင်ရင် /ask မှာ မေးပါဗျ။",
    "လက်ဝှေ့": "လက်ဝှေ့အနုပညာအကြောင်း အသေးစိတ်ကို /ask မှာ မေးပါ။",
    "ကိုယ်ခံပညာ": "ကိုယ်ခံပညာသင်ဖို့ ဘယ်လိုစမလဲဆိုတာ /ask မှာ မေးပါ။",
    "သိုင်း": "သိုင်းပညာနဲ့ ပတ်သက်ပြီး ဘာသိချင်လဲဗျ။ /ask မှာ မေးကြည့်ပါ။",
    "ကရာတေး": "ကရာတေးအကြောင်း သိချင်ရင် /ask မှာ မေးပါ။",
    "တိုက်ခိုက်နည်း": "တိုက်ခိုက်ရေး၊ ခုခံရေး နည်းပညာတွေအတွက် /ask မှာ မေးပါ။",

    # ဗေဒင် (Astrology)
    "ဗေဒင်": "ဗေဒင်မေးချင်ရင် မင်းရဲ့ မွေးနေ့ကို /profile birthdate : <မွေးနေ့> လို့ သိမ်းထားပါ၊ ပြီးရင် /ask မှာ မေးပါ။",
    "ရာသီခွင်": "ရာသီခွင်အကြောင်း (ဥပမာ - မိဿ၊ ပြိဿ စသည်) သိချင်ရင် /ask မှာ မေးပါဗျ။",
    "နက္ခတ်ဗေဒင်": "နက္ခတ်ဗေဒင်အသေးစိတ်ကို /ask မှာ မေးပါ။",
    "မွေးနေ့": "မွေးနေ့နဲ့ ကံကြမ္မာသိချင်ရင် /profile birthdate : <သင့်မွေးနေ့> ထည့်ပြီး /ask မှာ မေးပါ။",
    "ကံကြမ္မာ": "ကံကြမ္မာဖတ်ချင်ရင် မွေးနေ့လိုအပ်လို့ /profile birthdate : <သင့်မွေးနေ့> ထည့်ပါ။",
    "အတိတ်နိမိတ်": "အတိတ်နိမိတ် (ဥပမာ - ကြောင်နှာချေခြင်း၊ ငှက်မြည်ခြင်း) အကြောင်း သိချင်ရင် /ask မှာ မေးပါ။",

    # ရာသီဥတု (Weather)
    "ရာသီဥတု": "ရာသီဥတုအခြေအနေကို ခန့်မှန်းဖို့ /ask မှာ သင့်မြို့နယ်ကို ထည့်ပြီး မေးပါ။",
    "မိုးရွာမလား": "မိုးရွာနိုင်ခြေကို /ask မှာ သင့်တည်နေရာထည့်ပြီး မေးကြည့်ပါဗျ။",
    
    # ရင်းနှီးမြှုပ်နှံမှု (Investment)
    "ရင်းနှီးမြှုပ်နှံ": "ရင်းနှီးမြှုပ်နှံမှုအကြောင်း အသေးစိတ် (စတော့၊ ရွှေ၊ အိမ်ခြံမြေ) သိချင်ရင် /ask မှာ မေးပါဗျ။",
    "စတော့": "စတော့ဈေးကွက်အကြောင်း တစ်ကိုယ်ရေအကြံဉာဏ်အတွက် /ask မှာ မေးပါ။",
    
    # ခရစ်ပတို (Crypto)
    "ခရစ်ပတို": "ခရစ်ပတိုငွေကြေးတွေအကြောင်း အန္တရာယ်ကင်းစွာ လေ့လာချင်ရင် /ask မှာ မေးပါ။",
    "bitcoin": "Bitcoin အကြောင်း အသေးစိတ်ကို /ask မှာ မေးပါ။",
    
    # အော်ဒီယိုစာအုပ် (Audiobook)
    "အော်ဒီယို": "နားထောင်သင့်တဲ့ စာအုပ်တွေအတွက် /ask မှာ မေးပါ။",
    "စာအုပ်": "စာအုပ်အကြံပြုချက်တွေအတွက် /ask မှာ မေးပါ။",
    
    # ပညာရေး (Education)
    "ပညာရေး": "ပညာရေးဆိုင်ရာ လမ်းညွှန်ချက်တွေအတွက် /ask မှာ မေးပါ။",
    "ကျောင်း": "ကျောင်းရွေးချယ်ခြင်းနှင့် သင်တန်းများအတွက် /ask မှာ မေးပါ။",
    
    # ဘူမိဗေဒ (Geology)
    "ဘူမိ": "မြေအနေအထားနှင့် ကျောက်တုံးများအကြောင်း /ask မှာ မေးပါ။",
    "မြေငလျင်": "ငလျင်အန္တရာယ်အတွက် /ask မှာ မေးပါ။",
    
    # ဆေးဝါး (Pharmacist)
    "ဆေးဝါး": "ဆေးဝါးအသုံးပြုနည်းနဲ့ ပတ်သက်လို့ အခြေခံသိချင်ရင် /ask မှာ မေးပါ။ (ဆရာဝန်နဲ့ တိုင်ပင်ဖို့ မမေ့ပါနဲ့)",
    "ဆေး": "ဆေးဝါးအကြောင်း အသေးစိတ်သိချင်ရင် /ask မှာ မေးပါ။",
    
    # အချစ်ရေး အိမ်ထောင်ရေး (Love & Marriage)
    "အချစ်ရေး": "အချစ်ရေးအကြံဉာဏ်တွေအတွက် /ask မှာ မေးပါ။",
    "အိမ်ထောင်": "အိမ်ထောင်ရေးပြဿနာများအတွက် စိတ်ရှည်ရှည်နဲ့ /ask မှာ မေးပါ။",
    
    # ကလေးနာမည်ပေး (Baby Names)
    "ကလေးနာမည်": "ကလေးနာမည်ကောင်းများ ရွေးချင်ရင် /profile birthdate : <မွေးနေ့> ထည့်ပြီး /ask မှာ မေးပါ။",
    "နာမည်ပေး": "ကလေးနာမည်ပေးဖို့ မွေးနေ့လိုအပ်လို့ /profile birthdate : <မွေးနေ့> ထည့်ပါ။",
    
    # နေ့စဉ်သုံးစကားများ (Daily Phrases)
    "နေ့စဉ်သုံး": "နေ့စဉ်သုံးအင်္ဂလိပ်စကားပြောများ လေ့လာချင်ရင် /ask မှာ မေးပါ။",
    "အင်္ဂလိပ်စကား": "အင်္ဂလိပ်စကားပြော အသုံးအနှုန်းတွေအတွက် /ask မှာ မေးပါ။",
    
    # အလာဘ သလာဘ (Small Talk)
    "အလာဘ": "စကားစမြည်ပြောနည်းနဲ့ မိတ်ဆက်စကားတွေအတွက် /ask မှာ မေးပါ။",
    "သလာဘ": "အလာဘသလာဘစကားများနှင့် အသုံးအနှုန်းများအတွက် /ask မှာ မေးပါ။",
    "ထိုင်းထီ": "ထိုင်းထီ (ချဲထီ) အကြောင်း အသေးစိတ်သိချင်ရင် /ask မှာ မေးပါဗျ။ ဒါပေမယ့် ဒါဟာ မြန်မာပြည်မှာ တရားမဝင်တဲ့ လောင်းကစားတစ်ခုဖြစ်ပြီး အန္တရာယ်ရှိနိုင်ကြောင်း သတိပေးချင်ပါတယ်။",
    "ချဲထီ": "ချဲထီ ဆိုတာ ထိုင်းအစိုးရထီကို မြန်မာပြည်မှာ ခေတ်စားတဲ့အခေါ်ပါ။ ထီပုံစံနဲ့ ကံစမ်းနည်းတွေကို /ask မှာ မေးကြည့်နိုင်ပါတယ်။",
    "နှစ်လုံးထီ": "နှစ်လုံးထီ ဟာ ထိုင်း SET စတော့ဈေးကွက်ပိတ်ချိန် ကိန်းဂဏန်းတွေကို အခြေခံပြီး ထိုးရတဲ့ပုံစံပါ [citation:1]။ အသေးစိတ်ကို /ask မှာ မေးပါ။",
    "သုံးလုံးထီ": "သုံးလုံးထီ ဟာ ထိုင်းအစိုးရထီရဲ့ နံပါတ်နောက်ဆုံး (၃) လုံးကို အခြေခံပြီး ထိုးတာပါ။ အသေးစိတ်ကို /ask မှာ မေးပါ။",
    "ထီနံပါတ်": "ထီနံပါတ်ရွေးချယ်နည်း အကြံဉာဏ်တွေအတွက် /ask မှာ မေးပါ။",
    # ကားအရောင်းအဝယ် (Car Trading)
    "ကားအရောင်း": "ကားအရောင်းအဝယ်ပြုလုပ်ခြင်း၊ ဈေးနှုန်းနှင့် စာရွက်စာတမ်းများအတွက် /ask မှာ မေးပါဗျ။",
    "ကားဝယ်": "ကားဝယ်ယူရာတွင် စစ်ဆေးသင့်သည့်အချက်များအတွက် /ask မှာ မေးပါ။",
    
    # ကွန်ပျူတာအရောင်းအဝယ် (Computer Trading)
    "ကွန်ပျူတာအရောင်း": "ကွန်ပျူတာ၊ လက်ပ်တော့ အရောင်းအဝယ်အတွက် /ask မှာ မေးပါဗျ။",
    "လက်ပ်တော့": "လက်ပ်တော့ရွေးချယ်ခြင်းနှင့် အရောင်းအဝယ်အတွက် /ask မှာ မေးပါ။",
    
    # ကျောက်မျက်ရတနာ (Gemstone)
    "ကျောက်မျက်ရတနာ": "ကျောက်မျက်ရတနာအမျိုးအစားနှင့် အရည်အသွေးစစ်ဆေးနည်းအတွက် /ask မှာ မေးပါ။",
    "ကျောက်": "ကျောက်မျက်ရတနာရွေးချယ်နည်းအတွက် /ask မှာ မေးပါ။",
    
    # အဝတ်အထည် (Clothing)
    "အဝတ်အထည်": "အဝတ်အထည်အရောင်းအဝယ်နှင့် ဖက်ရှင်ရွေးချယ်နည်းအတွက် /ask မှာ မေးပါ။",
    "ဖက်ရှင်": "ဖက်ရှင်စတိုင်များနှင့် အဝတ်အထည်ရွေးချယ်နည်းအတွက် /ask မှာ မေးပါ။",
    
    # ဖုန်းပြင် (Phone Repair)
    "ဖုန်းပြင်": "ဖုန်းပြုပြင်ခြင်းဆိုင်ရာ အကြံဉာဏ်တွေအတွက် /ask မှာ မေးပါ။",
    "ဖုန်းရေစို": "ဖုန်းရေစိုပြဿနာအတွက် ချက်ချင်းလုပ်ဆောင်သင့်သည်များကို /ask မှာ မေးပါ။",
    
    # ရွှေအရောင်းအဝယ် (Gold Trading)
    "ရွှေအရောင်း": "ရွှေဈေးနှုန်းနှင့် အရည်အသွေးစစ်ဆေးနည်းအတွက် /ask မှာ မေးပါ။",
    "ရွှေ": "ရွှေဝယ်ယူရောင်းချခြင်းနှင့် ရင်းနှီးမြှုပ်နှံမှုအတွက် /ask မှာ မေးပါ။",
        # အထည်ချုပ် (Tailoring)
    "အထည်ချုပ်": "အထည်ချုပ်လုပ်ငန်းနှင့် အဝတ်အထည်ချုပ်နည်းအတွက် /ask မှာ မေးပါဗျ။",
    "ချုပ်": "အဝတ်အထည်ချုပ်နည်းနှင့် အတိုင်းအတာယူနည်းများအတွက် /ask မှာ မေးပါ။",
    
    # ဒီဇိုင်း (Design)
    "ဒီဇိုင်နာ": "ဒီဇိုင်းပညာရပ်များအတွက် /ask မှာ မေးပါ။",
    "ဂရပ်ဖစ်": "ဂရပ်ဖစ်ဒီဇိုင်းနှင့် အနုပညာဖန်တီးနည်းများအတွက် /ask မှာ မေးပါ။",
    
    # ဓာတု (Chemical)
    "ဓာတု": "ကုန်ထုတ်ဓာတုပညာရပ်များအတွက် /ask မှာ မေးပါ။",
    
    # ရေမွှေး/ဆပ်ပြာ
    "ရေမွှေး": "ရေမွှေးနှင့် အလှကုန်ပစ္စည်းထုတ်လုပ်နည်းအတွက် /ask မှာ မေးပါ။",
    "ဆပ်ပြာ": "ဆပ်ပြာနှင့် သန့်ရှင်းရေးပစ္စည်းထုတ်လုပ်နည်းအတွက် /ask မှာ မေးပါ။",
    
    # ဘိုင်နရီ/ဖြူးချား
    "ဘိုင်နရီ": "ဘက်ထရီပြုပြင်ထိန်းသိမ်းနည်းအတွက် /ask မှာ မေးပါ။",
    "ဖြူးချား": "ဖျူးစ်/ဘရိတ်ကာနှင့် လျှပ်စစ်ပစ္စည်းများအကြောင်း /ask မှာ မေးပါ။",
    
    # ပတ်ဝန်းကျင်
    "ပတ်ဝန်းကျင်": "သဘာဝပတ်ဝန်းကျင်ထိန်းသိမ်းရေးအတွက် /ask မှာ မေးပါ။",
    "တိရိစ္ဆာန်": "တောရိုင်းတိရိစ္ဆာန်နှင့် သားငါးထိန်းသိမ်းရေးအတွက် /ask မှာ မေးပါ။",
    
    # ဘဏ် (Bank)
    "ဘဏ်": "ဘဏ်ဝန်ဆောင်မှုများနှင့် စာရင်းဖွင့်နည်းအတွက် /ask မှာ မေးပါ။",
    "ချေးငွေ": "ချေးငွေနှင့် အတိုးနှုန်းများအတွက် /ask မှာ မေးပါ။",
    
    # အရောင်း (Sales)
    "အရောင်းသမား": "အရောင်းပညာရပ်များနှင့် ဖောက်သည်စကားပြောနည်းအတွက် /ask မှာ မေးပါ။",
    
    # မုန့် (Bakery)
    "မုန့်": "မုန့်လုပ်ငန်းနှင့် မုန့်ဖုတ်နည်းအတွက် /ask မှာ မေးပါ။",
    "ကိတ်": "ကိတ်မုန့်ပြုလုပ်နည်းအတွက် /ask မှာ မေးပါ။",
    
    # စားသောက်ဆိုင် (Restaurant)
    "စားသောက်ဆိုင်": "စားသောက်ဆိုင်ဖွင့်နည်းနှင့် စီမံခန့်ခွဲနည်းအတွက် /ask မှာ မေးပါ။",
    
    # အလှပြင် (Beauty)
    "မိတ်ကပ်": "မိတ်ကပ်ဖျောက်နည်းနှင့် အလှပြင်နည်းအတွက် /ask မှာ မေးပါ။",
    "ဆံပင်": "ဆံပင်ညှပ်နည်းနှင့် ဆံပင်ဒီဇိုင်းအတွက် /ask မှာ မေးပါ။",
    
    # ဥယျာဉ် (Gardening)
    "ဥယျာဉ်": "ပန်းပျိုးခြင်းနှင့် ဥယျာဉ်စိုက်ပျိုးနည်းအတွက် /ask မှာ မေးပါ။",
    "ပန်း": "ပန်းစိုက်ပျိုးနည်းအတွက် /ask မှာ မေးပါ။",
    
    # တောင်တက် (Mountaineering)
    "တောင်တက်": "တောင်တက်ပညာနှင့် အန္တရာယ်ကင်းရှင်းရေးအတွက် /ask မှာ မေးပါ။",
    
    # မြေပုံ/ဒေသ (Geography)
    "မြေပုံ": "မြန်မာပြည်ဒေသမြေပုံနှင့် ခရီးသွားလမ်းညွှန်အတွက် /ask မှာ မေးပါ။",
    
    # ကမ္ဘာ့ရေးရာ (Global)
    "ကမ္ဘာ့": "ကမ္ဘာ့ရေးရာနှင့် နိုင်ငံတကာသတင်းများအတွက် /ask မှာ မေးပါ။",
    
    # နိုင်ငံရေး (Politics)
    "နိုင်ငံရေး": "နိုင်ငံရေးအခြေအနေများကို ဘက်မလိုက်ဘဲ သိရှိလိုပါက /ask မှာ မေးပါ။",
    
    # သတင်း (News)
    "သတင်း": "နောက်ဆုံးရသတင်းများအတွက် /ask မှာ မေးပါ။",
    
    # ပွဲစား (Broker)
    "ပွဲစား": "ကုန်သည်ပွဲစားလုပ်ငန်းနှင့် အဝယ်အရောင်းညှိနှိုင်းနည်းအတွက် /ask မှာ မေးပါ။",
    "ကုန်သည်": "ကုန်သည်လုပ်ငန်းနှင့် ဈေးနှုန်းအချက်အလက်များအတွက် /ask မှာ မေးပါ။",
    # Binary & Futures Trading
    "binary": "Binary Options သည် အနိုင်အရှုံးသာ ရှိပြီး မြန်မာပြည်မှာ တရားဝင်မဟုတ်ပါ။ အလွန်မြင့်မားတဲ့ Risk ရှိကြောင်း သိထားပါ။ /ask မှာ မေးနိုင်ပါတယ်။",
    "futures": "Futures Trading သည် Contract အပေါ်အခြေခံပြီး ဈေးကွက်အတက်အကျကို ခန့်မှန်းရတာပါ။ Risk များတဲ့အတွက် သေချာလေ့လာပြီးမှ /ask မှာ မေးကြည့်ပါ။",
    "binary option": "Binary Option သည် မြန်မာပြည်မှာ တရားဝင်မဟုတ်ပါ။ အန္တရာယ်ရှိနိုင်ကြောင်း သတိပြုပါ။ /ask မှာ အသေးစိတ်မေးနိုင်ပါတယ်။",
    "futures trading": "Futures Trading အကြောင်းအသေးစိတ်၊ Risk စီမံခန့်ခွဲနည်းများအတွက် /ask မှာ မေးပါ။",
    "leverage": "Leverage (အရင်းအနှီးချေးငွေ) သုံးပြီး ရောင်းဝယ်ခြင်းသည် အမြတ်ရရင်မြန်ပေမယ့် ဆုံးရှုံးရင်လည်း မြန်ပါတယ်။ ဒါကြောင့် /ask မှာ မေးပြီးမှ ဆုံးဖြတ်ပါ။",
        # သမိုင်း (History)
    "သမိုင်း": "မြန်မာ့သမိုင်း၊ ကမ္ဘာ့သမိုင်းအကြောင်း အသေးစိတ်သိချင်ရင် /ask မှာ မေးပါဗျ။",
    "ရှေးဟောင်း": "ရှေးဟောင်းသုတေသနဆိုင်ရာ အချက်အလက်များအတွက် /ask မှာ မေးပါ။",
    
    # ကုန်စျေးနှုန်း (Prices)
    "ကုန်စျေးနှုန်း": "ရွှေ၊ ဆန်၊ ဆီ အစရှိတဲ့ ကုန်စျေးနှုန်းတွေအတွက် /ask မှာ မေးပါ။",
    "စျေးနှုန်း": "ဒေသအလိုက် ကုန်စျေးနှုန်းအခြေအနေများအတွက် /ask မှာ မေးပါ။",
    
    # ရုပ်ရှင် (Movies)
    "ရုပ်ရှင်": "ရုပ်ရှင်ကောင်းများ အကြံပြုချက်ရယူရန် YouTube/Netflix လင့်နှင့်အတူ /ask မှာ မေးပါ။",
    "ကားရိုက်": "ရုပ်ရှင်ရိုက်ကူးနည်းပညာနှင့် ဇာတ်ကားအကြံပြုချက်များအတွက် /ask မှာ မေးပါ။",
    
    # စာပေ (Literature)
    "စာပေ": "ဝတ္ထု၊ ကဗျာရေးသားနည်းနှင့် စာပေဆိုင်ရာ အကြံဉာဏ်များအတွက် /ask မှာ မေးပါ။",
    "စာရေးဆရာ": "စာရေးဆရာများအကြောင်းနှင့် စာအုပ်အကြံပြုချက်များအတွက် /ask မှာ မေးပါ။",
    
    # ဘာသာရေး (Religion)
    "ဘာသာရေး": "ဘာသာတရားအမျိုးမျိုး၏ အခြေခံသဘောတရားများအတွက် /ask မှာ မေးပါ။",
    
    # ဝိပဿနာ (Vipassana)
    "ဝိပဿနာ": "တရားထိုင်နည်းနှင့် ဝိပဿနာကျင့်စဉ်များအတွက် /ask မှာ မေးပါ။",
    
    # ကျော်ဖြတ်နည်း (Overcoming)
    "အဆင့်နိမ့်": "ဆင်းရဲခြင်းမှ လွတ်မြောက်ရန် နည်းလမ်းများအတွက် /ask မှာ မေးပါ။",
    
    # ပန်းချီ/ပန်းပဲ/ပန်းထိမ်/ပန်းတမော့
    "ပန်းချီ": "ပန်းချီရေးဆွဲနည်းနှင့် ပညာရပ်များအတွက် /ask မှာ မေးပါ။",
    "ပန်းပဲ": "သံထည်ပစ္စည်းပြုလုပ်နည်းအတွက် /ask မှာ မေးပါ။",
    "ပန်းထိမ်": "လက်ဝတ်ရတနာပြုလုပ်နည်းအတွက် /ask မှာ မေးပါ။",
    "ပန်းတမော့": "ပန်းတမော့ပစ္စည်းပြုလုပ်နည်းအတွက် /ask မှာ မေးပါ။",
    
    # မြန်မာ့ပန်းဆယ်မျိုး (10 Arts)
    "ပန်းဆယ်မျိုး": "မြန်မာ့ရိုးရာအနုပညာဆယ်မျိုးအကြောင်း /ask မှာ မေးပါ။",
    
    # ဘတ်စ်ကား (Bus)
    "ဘတ်စ်ကား": "မြန်မာပြည်မြို့ကြီးများ၏ ဘတ်စ်ကားလမ်းကြောင်းများအတွက် /ask မှာ မေးပါ။",
    
    # ငွေရေးကြေးရေး (Financial)
    "ငွေရေးကြေးရေး": "မိသားစုဘဏ္ဍာရေးစီမံခန့်ခွဲနည်းများအတွက် /ask မှာ မေးပါ။"
}

def get_local_response(user_text):
    if not user_text:
        return None
    text = user_text.lower().strip()
    for key, value in LOCAL_RESPONSES.items():
        if key in text:
            return value
    return None

# ====== Daily Coaching & System Prompt (66 Domains) ======
system_prompt = (
    "သင်ဟာ မစ္စတာသန်း (Mr.T) — funny, friendly, motivational AI Bot ဖြစ်ပါတယ်။\n\n"
    "မင်းရဲ့ အဓိက ကျွမ်းကျင်မှု နယ်ပယ် (၈၀) ခုက -\n"
    "1️⃣ Life Coach, 2️⃣ Relationship Coach, 3️⃣ Money Mindset, 4️⃣ Productivity, 5️⃣ Fitness, 6️⃣ Business, 7️⃣ Tech, 8️⃣ Video Editing & Design, 9️⃣ Trend & AI Tools, "
    "🔟 စိုက်ပျိုးရေး, 1️⃣1️⃣ မွေးမြူရေး, 1️⃣2️⃣ မြန်မာ့လုပ်ငန်း, 1️⃣3️⃣ ပညာရေး, 1️⃣4️⃣ ဥပဒေ, 1️⃣5️⃣ ကျန်းမာရေး, 1️⃣6️⃣ စားသောက်ကုန်, "
    "1️⃣7️⃣ ဗေဒင်, 1️⃣8️⃣ သိုင်းပညာ, 1️⃣9️⃣ အားကစား, 2️⃣0️⃣ ရာသီဥတု, 2️⃣1️⃣ ရင်းနှီးမြှုပ်နှံမှု, 2️⃣2️⃣ ခရစ်ပတို, "
    "2️⃣3️⃣ အော်ဒီယိုစာအုပ်, 2️⃣4️⃣ ပညာရေးလမ်းညွှန်, 2️⃣5️⃣ ဘူမိဗေဒ, 2️⃣6️⃣ ဆေးဝါး, 2️⃣7️⃣ အချစ်ရေးနှင့်အိမ်ထောင်ရေး, "
    "2️⃣8️⃣ ကလေးနာမည်ပေး, 2️⃣9️⃣ နေ့စဉ်သုံးစကား, 3️⃣0️⃣ အလာဘသလာဘ, 3️⃣1️⃣ ထိုင်းထီ, "
    "3️⃣2️⃣ စက်ပြင်, 3️⃣3️⃣ ကားပြင်, 3️⃣4️⃣ စက်ဘီး/ဆိုင်ကယ်ပြင်, 3️⃣5️⃣ ဆောက်လုပ်ရေး, 3️⃣6️⃣ လျှပ်စစ်, "
    "3️⃣7️⃣ မြေအရောင်းအဝယ်, 3️⃣8️⃣ အာမခံ, 3️⃣9️⃣ စီမံခန့်ခွဲမှုနှင့်ခေါင်းဆောင်မှု, 4️⃣0️⃣ ကားအရောင်းအဝယ်, "
    "4️⃣1️⃣ ကွန်ပျူတာအရောင်းအဝယ်, 4️⃣2️⃣ ကျောက်မျက်ရတနာ, 4️⃣3️⃣ အဝတ်အထည်အရောင်းအဝယ်, 4️⃣4️⃣ ဖုန်းပြင်, 4️⃣5️⃣ ရွှေအရောင်းအဝယ်, "
    "4️⃣6️⃣ အထည်ချုပ်ကျွမ်းကျင်သူ, 4️⃣7️⃣ ဒီဇိုင်နာ, 4️⃣8️⃣ ကုန်ထုတ်ဓာတု, 4️⃣9️⃣ ရေမွှေး/ဆပ်ပြာ/အလှကုန်, 5️⃣0️⃣ ဘိုင်နရီ/ဖြူးချား, "
    "5️⃣1️⃣ ပတ်ဝန်းကျင်ထိန်းသိမ်းရေး, 5️⃣2️⃣ ဘဏ်ဝန်ထမ်း, 5️⃣3️⃣ အရောင်းသမား, 5️⃣4️⃣ မုန့်လုပ်ငန်း, 5️⃣5️⃣ စားသောက်ဆိုင်, "
    "5️⃣6️⃣ အလှပြင်မိတ်ကပ်/ဆံပင်, 5️⃣7️⃣ မြေယာအလှပြင်, 5️⃣8️⃣ ပန်းပျိုးဥယျာဉ်, 5️⃣9️⃣ တောင်တက်, 6️⃣0️⃣ မြေပုံကျွမ်းကျင်သူ, "
    "6️⃣1️⃣ ကမ္ဘာ့ရေးရာ, 6️⃣2️⃣ နိုင်ငံရေး, 6️⃣3️⃣ နောက်ဆုံးသတင်းထူး, 6️⃣4️⃣ ကုန်သည်ပွဲစား, 6️⃣5️⃣ မြန်မာ့ရိုးရာနှင့် ဌာနဆိုင်ရာ, "
    "6️⃣6️⃣ Binary & Futures Trading, "
    "6️⃣7️⃣ သမိုင်းသုတေသီ (Historian) - မြန်မာ့သမိုင်း၊ ကမ္ဘာ့သမိုင်း၊ ရှေးဟောင်းသုတေသနဆိုင်ရာ အချက်အလက်များ အကြံပေးခြင်း။\n"
    "6️⃣8️⃣ မြန်မာ့ကုန်စျေးနှုန်း (Myanmar Commodity Prices) - ဆန်၊ ဆီ၊ ရွှေ၊ ငွေစျေးနှုန်းနှင့် ဒေသအလိုက် ကုန်စျေးနှုန်းများ အကြံပေးခြင်း။\n"
    "6️⃣9️⃣ ရုပ်ရှင်ကျွမ်းကျင်သူ (Movie Expert) - ရုပ်ရှင်အမျိုးအစားများ၊ ဇာတ်ကားအကြံပြုချက်များနှင့် ကြည့်ရှုနိုင်သော Link များ ရှာဖွေပေးခြင်း။\n"
    "7️⃣0️⃣ စာပေကျွမ်းကျင်သူ (Literature Expert) - ဝတ္ထု၊ ကဗျာ၊ ဆောင်းပါးများ ရေးသားနည်း၊ စာပေသမိုင်းနှင့် စာရေးဆရာများအကြောင်း အကြံပေးခြင်း။\n"
    "7️⃣1️⃣ ဘာသာရေးကျွမ်းကျင်သူ (Religion Expert) - ဗုဒ္ဓဘာသာ၊ ခရစ်ယာန်၊ အစ္စလာမ် အပါအဝင် ဘာသာတရားများ၏ အခြေခံသဘောတရားများ ရှင်းပြခြင်း (ဘက်မလိုက်ဘဲ)။\n"
    "7️⃣2️⃣ ဝိပဿနာကျွမ်းကျင်သူ (Vipassana Expert) - တရားထိုင်နည်း၊ ဝိပဿနာကျင့်စဉ်၊ စိတ်တည်ငြိမ်အောင် လေ့ကျင့်နည်းများ အကြံပေးခြင်း။\n"
    "7️⃣3️⃣ အဆင့်နိမ့်ပတ်ဝန်းကျင် ကျော်ဖြတ်နည်း (Overcoming Low Environment) - ဆင်းရဲခြင်း၊ အနိုင်ကျင့်ခံရခြင်းမှ လွတ်မြောက်ရန်၊ မိမိကိုယ်ကို မြှင့်တင်နည်းများ အကြံပေးခြင်း။\n"
    "7️⃣4️⃣ ပန်းချီကျွမ်းကျင်သူ (Painter) - ဆီဆေးပန်းချီ၊ ရေဆေးပန်းချီ၊ ခဲပန်းချီနည်းစနစ်များ အကြံပေးခြင်း။\n"
    "7️⃣5️⃣ ပန်းပဲကျွမ်းကျင်သူ (Blacksmith) - ဓား၊ ထွန်ခြစ်၊ တူ စသည့် သံထည်ပစ္စည်းများ ပြုလုပ်ပြုပြင်နည်းများ အကြံပေးခြင်း။\n"
    "7️⃣6️⃣ ပန်းထိမ်ကျွမ်းကျင်သူ (Goldsmith) - ရွှေ၊ ငွေ၊ ရတနာများဖြင့် လက်ဝတ်ရတနာ ပြုလုပ်နည်း၊ အရည်အသွေးစစ်ဆေးနည်းများ အကြံပေးခြင်း။\n"
    "7️⃣7️⃣ ပန်းတမော့ကျွမ်းကျင်သူ (Lacquerware Expert) - မြန်မာ့ရိုးရာ ပန်းတမော့ပစ္စည်းများ ပြုလုပ်နည်း၊ အလှဆင်နည်းများ အကြံပေးခြင်း။\n"
    "7️⃣8️⃣ မြန်မာ့ပန်းဆယ်မျိုး (Myanmar Traditional Arts) - ပန်းချီ၊ ပန်းပဲ၊ ပန်းထိမ်၊ ပန်းတမော့၊ ပန်းယွန်း စသည့် မြန်မာ့ရိုးရာအနုပညာဆယ်မျိုး အကြံပေးခြင်း။\n"
    "7️⃣9️⃣ မြန်မာ့ဘတ်စ်ကားလမ်းညွှန် (Bus Route Guide) - မြို့ကြီးများ၏ ဘတ်စ်ကားလမ်းကြောင်းများ၊ ခရီးစဉ်များ၊ လက်မှတ်ဈေးနှုန်းများ အကြံပေးခြင်း။\n"
    "8️⃣0️⃣ ငွေရေးကြေးရေးအတိုင်ပင်ခံ (Financial Advisor) - မိသားစုဘဏ္ဍာရေး၊ ချွေတာနည်း၊ ကြွေးမြီကင်းဝေးအောင် စီမံနည်းများ အကြံပေးခြင်း။\n\n"

        "=== အထူးလမ်းညွှန်ချက်များ ===\n"
    "1. ရာသီဥတုမေးရင် - တိကျတဲ့ ဒေသကို မေးပြီးမှ ဖြေပါ။\n"
    "2. ရင်းနှီးမြှုပ်နှံမှု/ခရစ်ပတို/ရွှေ - 'အာမခံအမြတ်' လို့ ဘယ်တော့မှ မပြောပါနဲ့။\n"
    "3. ဆေးဝါး - ဆေးညွှန်းမပေးပါနဲ့။ ဆရာဝန်နဲ့ တိုင်ပင်ရန် ပြောပါ။\n"
    "4. နိုင်ငံရေး/သတင်း - ဘက်မလိုက်ဘဲ ရှင်းပြပါ။\n"
    "5. ဓာတု - ဘေးအန္တရာယ်ကင်းရှင်းရေး သတိပေးပါ။\n"
    "6. စားသောက်ဆိုင် - တစ်ကိုယ်ရေသန့်ရှင်းရေး သတိပေးပါ။\n"
    "7. ပတ်ဝန်းကျင်နှင့် တိရိစ္ဆာန် - ကြင်နာမှုနှင့် ဥပဒေလေးစားရန် ပြောပါ။\n"
    "8. ထိုင်းထီ - တရားမဝင်ကြောင်း၊ အန္တရာယ်ရှိကြောင်း သတိပေးပါ။\n"
    "9. ရုပ်ရှင်မေးရင် - အွန်လိုင်းတွင် ရှာဖွေကြည့်ရှုနိုင်သော YouTube/Netflix လင့်များကို အကြံပြုပါ။\n"
    "10. ဘာသာရေး/ဝိပဿနာ - ဘက်မလိုက်ဘဲ လေးစားမှုဖြင့် အကြံပြုပါ။\n"
    "11. မြေအရောင်းအဝယ်/အာမခံ - စာချုပ်မချုပ်မီ အသေးစိတ် စစ်ဆေးရန် အမြဲသတိပေးပါ။\n"
    "12. အုပ်ချုပ်မှု - တရားမျှတမှု၊ နားထောင်မှုနှင့် စည်းကမ်းတကျ ရှိရန် အကြံပေးပါ။\n"
    "13. ကား/ကွန်ပျူတာ/ကျောက်မျက်/အဝတ်အထည်/ရွှေ အရောင်းအဝယ်နှင့် ဖုန်းပြင် - အရည်အသွေးစစ်ဆေးနည်း၊ လိမ်လည်မှုမှ ကာကွယ်နည်းများ သတိပေးပါ။\n"
    "14. Binary & Futures Trading - ဤနယ်ပယ်များသည် အလွန်မြင့်မားသော စွန့်စားမှုဖြစ်ပြီး အာမခံအမြတ်မရှိကြောင်း၊ မြန်မာပြည်တွင် တရားဝင်မှုမရှိကြောင်း ရိုးရိုးသားသား သတိပေးရမယ်။\n"
    "15. သမိုင်းမေးရင် - တိကျသော သမိုင်းအချက်အလက်များကို သာလျှင် ဖြေဆိုပါ။ မသေချာလျှင် 'မသေချာပါ' ဟု ပြောပါ။\n"
    "16. ကုန်စျေးနှုန်းမေးရင် - နောက်ဆုံးရရှိသော အချက်အလက်များကို အသုံးပြုပြီး 'လက်ရှိခန့်မှန်းချက်' ဟု ဖော်ပြပါ။ တိကျသေချာမှုမရှိလျှင် အသိပေးပါ။\n"
    "17. ရုပ်ရှင်မေးရင် - တရားဝင်လင့်များသာ ပေးပါ။ မူပိုင်ခွင့်ကို လေးစားပါ။\n"
    "18. စာပေမေးရင် - စာရေးဆရာများ၏ မူပိုင်ခွင့်ကို လေးစားပါ။ စာပေသဘောတရားများကို ရှင်းလင်းစွာ ဖော်ပြပါ။\n"
    "19. ဘာသာရေးမေးရင် - ဘာသာတစ်ခုချင်းစီ၏ ယုံကြည်မှုကို လေးစားပါ။ ဘက်မလိုက်ပါနှင့်။\n"
    "20. ဝိပဿနာမေးရင် - ဆရာတစ်ဦး၏ လမ်းညွှန်မှုဖြင့် ကျင့်သုံးရန် အကြံပြုပါ။ စိတ်ပိုင်းဆိုင်ရာ ထိခိုက်မှုများကို သတိပြုပါ။\n"
    "21. အဆင့်နိမ့်ပတ်ဝန်းကျင်မေးရင် - စိတ်ဓာတ်ပိုင်း အားပေးမှုနှင့် တကယ့်အကူအညီရှာဖွေရန် ညွှန်ကြားပါ။ လူမှုရေးအကူအညီများကို အကြံပြုပါ။\n"
    "22. ပန်းချီ/ပန်းပဲ/ပန်းထိမ်/ပန်းတမော့ - ရိုးရာအနုပညာများကို ထိန်းသိမ်းရန် အကြံပြုပါ။ အန္တရာယ်ကင်းရှင်းရေးကို အလေးထားပါ။\n"
    "23. ဘတ်စ်ကားလမ်းညွှန်မေးရင် - လက်ရှိအချိန်ဇယားများကို စစ်ဆေးရန် အကြံပြုပါ။ လမ်းကြောင်းပြောင်းလဲမှုများ ရှိနိုင်ကြောင်း သတိပေးပါ။\n"
    "24. ငွေရေးကြေးရေးမေးရင် - ဘတ်ဂျက်ရေးဆွဲနည်း၊ ကြွေးမြီစီမံခန့်ခွဲနည်းများကို ရိုးသားစွာ အကြံပေးပါ။ 'ချမ်းသာအောင် ဒီလိုလုပ်ပါ' မျိုး အာမခံချက် မပေးပါနှင့်။\n\n"
    
    "အသုံးပြုသူရဲ့ မေးခွန်းကို ကျွမ်းကျင်သူတစ်ယောက်လို ဖြေပေးရမယ်။\n"
    "အဖြေတွေကို မြန်မာလိုပဲ ပြန်ရမယ်။ လေးလေးနက်နက်၊ ရယ်စရာ၊ မိတ်ဆွေလို ပြောရမယ်။\n"
    "ဥပဒေ၊ ကျန်းမာရေး၊ ငွေကြေးဆိုင်ရာ အကြံပြုချက်များသည် အထွေထွေ အချက်အလက်သာဖြစ်ပြီး ကျွမ်းကျင်သူများနှင့် တိုင်ပင်ရန် သတိပေးရမယ်။"
)
# ====== AI Model (DeepSeek First, GPT-4o-mini Fallback) ======
async def ask_model(prompt: str, user_id: str = None) -> str:
    user_context = ""
    cache_allowed = True  # Cache ကို ခွင့်ပြုမလား

    if user_id:
        user_data = get_user(user_id)
        if user_data:
            # 👇 ဒီမှာ (၁၃) ခုနဲ့ ဖြေရှင်းပါ (birthdate ထည့်ပြီး)
            (plan, usage, proof_status, _, _, _, goals, weaknesses, dream, career, money_mindset, relationship, birthdate) = user_data
            
            # Profile မှာ ဒေတာတွေ ရှိနေရင် Cache မသုံးပါနဲ့ (သူ့အတွက် သီးသန့်ဖြေရမလို့)
            if any([goals, weaknesses, dream, career, money_mindset, relationship, birthdate]):
                cache_allowed = False
                user_context = "\n\n[အသုံးပြုသူ၏ ကိုယ်ရေးအချက်အလက်များ]\n"
                if goals: user_context += f"- ပန်းတိုင်: {goals}\n"
                if career: user_context += f"- အလုပ်အကိုင်: {career}\n"
                if dream: user_context += f"- အိပ်မက်: {dream}\n"
                if weaknesses: user_context += f"- အားနည်းချက်: {weaknesses}\n"
                if money_mindset: user_context += f"- ငွေကြေးစိတ်ဓာတ်: {money_mindset}\n"
                if relationship: user_context += f"- ဆက်ဆံရေး: {relationship}\n"
                if birthdate: user_context += f"- မွေးနေ့: {birthdate}\n"

    # Cache ထဲ အရင်ရှာမယ် (Profile မရှိရင်သာ)
    if cache_allowed:
        cached = get_cached_response(prompt)
        if cached:
            return cached

    # DeepSeek ကို စမ်းမယ်
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "system", "content": system_prompt + user_context}, {"role": "user", "content": prompt}], "max_tokens": 800, "temperature": 0.85},
            )
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                final_answer = result["choices"][0]["message"]["content"].strip()
                # အဖြေရပြီဆိုရင် Cache ထဲ သိမ်းမယ် (Profile မရှိရင်သာ)
                if cache_allowed:
                    save_cached_response(prompt, final_answer)
                return final_answer
            elif "error" in result:
                raise Exception(result["error"]["message"])
            else:
                raise Exception("Unexpected API response: " + str(result))
    except Exception as e:
        logger.error(f"DeepSeek failed: {e}. Falling back to GPT-4o-mini.")
        
        # GPT-4o-mini ကို ပြန်ခေါ်မယ် (Fallback)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "system", "content": system_prompt + user_context}, {"role": "user", "content": prompt}], "max_tokens": 800, "temperature": 0.85},
            )
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                final_answer = result["choices"][0]["message"]["content"].strip()
                # အဖြေရပြီဆိုရင် Cache ထဲ သိမ်းမယ် (Profile မရှိရင်သာ)
                if cache_allowed:
                    save_cached_response(prompt, final_answer)
                return final_answer
            elif "error" in result:
                raise Exception(result["error"]["message"])
            else:
                raise Exception("Unexpected API response: " + str(result))

async def send_daily_coaching(bot):
    try:
        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE plan IN ('free', 'premium_plus')")
        users = c.fetchall()
        conn.close()

        if not users:
            return

        prompt = "မင်္ဂလာပါ၊ ဒီနေ့အတွက် နေ့စဉ် ဘဝလမ်းညွှန်စကား (Daily Coaching Message) ကို မစ္စတာသန်း (Mr.T) ရဲ့ အသံနဲ့ ရေးပါ။ ယုံကြည်မှု၊ အလုပ်အကိုင်၊ ငွေကြေးအတွေးအခေါ် အကြောင်းတွေ ပါစေ။"
        message = await ask_model(prompt)
        if not message or len(message) < 10:
            message = "🌅 ဒီနေ့အတွက် အကောင်းဆုံး နေ့တစ်နေ့ ဖြစ်ပါစေ။"
        
        sent = 0
        for user in users:
            try:
                await bot.send_message(chat_id=int(user[0]), text=f"🔥 **Daily Coaching Message**\n\n{message}")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Failed to send daily coaching to {user[0]}: {e}")
        logger.info(f"✅ Daily coaching sent to {sent} users.")
    except Exception as e:
        logger.error(f"❌ Daily coaching error: {e}")

# ====== Scheduler ======
def run_scheduler(bot):
    schedule.every(30).days.do(reset_usage)
    schedule.every().day.at("08:00").do(lambda: asyncio.run(send_daily_coaching(bot)))
    schedule.every().day.at("03:00").do(lambda: asyncio.run(backup_and_send(bot)))
    logger.info("⏰ Scheduler started.")
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

    # Button နှစ်ခု ထည့်ထားပါတယ်
    keyboard = [
        [InlineKeyboardButton("📌 Plan ရွေးရန် (စတင်ရန်)", callback_data="start_plan")],
        [InlineKeyboardButton("ℹ️ လမ်းညွှန်ချက်များ (Help)", callback_data="start_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် မစ္စတာသန်းပါ။\n"
        "သင့်ရဲ့ လက်ထောက် အဖြစ်နဲ့ ကိုယ်ရေးကိုယ်တာ၊ အလုပ်အကိုင်နဲ့ "
        "တခြားလုပ်ဆောင်ရမယ့် အရာတွေကို ယုံကြည်စွာ ဖြေရှင်းပေးဖို့ အသင့်ပါဗျ။\n\n"
        "🚀 စတင်အသုံးပြုရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။",
        reply_markup=reply_markup
    )
    
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 အသုံးပြုနည်း:\n/start - စတင်ရန်\n/help - အကူအညီ\n/subscribe - Plan ရွေးရန်\n/ask <q> - မေးရန်\n/status - အနေအထား\n/profile - ကိုယ်ရေးမှတ်တမ်း\n/habit - အလေ့အထ\n/referral - ဖိတ်ရန်\n\n"
        "🎯 ကျွန်တော် အကြံပေးနိုင်တဲ့ နယ်ပယ် ၈၀ ခုရှိပါတယ်။"
    )

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    ref_code = generate_ref_code(user_id)
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    inviter_count = get_referral_count(user_id)
    await update.message.reply_text(f"🔗 သင့် Referral Link:\n`{ref_link}`\n\n📊 ဖိတ်ထားသူ: {inviter_count}\n✨ 50 ကြိမ် free ရပါမယ်။")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    plan = context.args[0] if context.args else "free"

    if plan not in PLAN_LIMITS:
        allowed = ", ".join(PLAN_LIMITS.keys())
        await update.message.reply_text(f"❌ '{plan}' မရှိပါ။ ရနိုင်တဲ့ Plan: {allowed}")
        return

    # ✅ ဒီနေရာမှာ ကြိမ်အရေအတွက်တွေ ဖြုတ်ပြီး Plan နဲ့ ဈေးနှုန်းကိုပဲ ပြထားပါတယ်
    keyboard = [
        [InlineKeyboardButton("📌 Free (အခမဲ့)", callback_data="sub_free")],
        [InlineKeyboardButton("⭐ Basic (10,000 MMK)", callback_data="sub_basic")],
        [InlineKeyboardButton("💎 Premium (30,000 MMK)", callback_data="sub_premium")],
        [InlineKeyboardButton("👑 Premium+ (50,000 MMK)", callback_data="sub_premium_plus")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📌 အောက်ပါ Plan များမှ ရွေးချယ်ပါ။\n\n"
        "📌 Free (အခမဲ့)\n"
        "⭐ Basic (10,000 MMK)\n"
        "💎 Premium (30,000 MMK)\n"
        "👑 Premium+ (50,000 MMK) (VIP)",
        reply_markup=reply_markup,
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data

    # အသစ်ထည့်ထားတဲ့ Start Buttons အတွက် Logic
    if data == "start_plan":
        # Plan ရွေးတဲ့ UI ကို တိုက်ရိုက်ပြပေးမယ်
        keyboard = [
            [InlineKeyboardButton("📌 Free (အခမဲ့)", callback_data="sub_free")],
            [InlineKeyboardButton("⭐ Basic (10,000 MMK)", callback_data="sub_basic")],
            [InlineKeyboardButton("💎 Premium (30,000 MMK)", callback_data="sub_premium")],
            [InlineKeyboardButton("👑 Premium+ (50,000 MMK)", callback_data="sub_premium_plus")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📌 အောက်ပါ Plan များမှ ရွေးချယ်ပါ။\n\n"
            "📌 Free (အခမဲ့)\n"
            "⭐ Basic (10,000 MMK)\n"
            "💎 Premium (30,000 MMK)\n"
            "👑 Premium+ (50,000 MMK) (VIP)",
            reply_markup=reply_markup
        )
        return

    if data == "start_help":
        # Help Command ကို ပြပေးမယ်
        await query.edit_message_text(
            "📌 အသုံးပြုနည်း:\n"
            "/start - စတင်ရန်\n"
            "/help - အကူအညီ\n"
            "/subscribe - Plan ရွေးရန်\n"
            "/ask <q> - မေးရန်\n"
            "/status - အနေအထား\n"
            "/profile - ကိုယ်ရေးမှတ်တမ်း\n"
            "/habit - အလေ့အထ\n"
            "/referral - ဖိတ်ရန်\n\n"
            "🎯 ကျွန်တော် အကြံပေးနိုင်တဲ့ နယ်ပယ် ၆၅ ခုရှိပါတယ်။"
        )
        return

    # အောက်က မူရင်း Subscription Logic တွေ ဆက်လက်အလုပ်လုပ်နေမှာပါ
    if data.startswith("sub_"):
        plan = data.replace("sub_", "")
        if plan not in PLAN_LIMITS:
            await query.edit_message_text("❌ Invalid plan.")
            return

        conn = sqlite3.connect("bot_users.db")
        c = conn.cursor()
        c.execute("UPDATE users SET plan=?, proof_status='waiting', price=? WHERE user_id=?", (plan, PLAN_LIMITS[plan]["price"], user_id))
        conn.commit()
        conn.close()

        price_mmk = PLAN_LIMITS[plan]["price"]
        price_usd = get_price_usd(price_mmk)

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
        user = ("free", 0, "none", None, 0, None, None, None, None, None, None, None, None, None) # ၁၃ ခု ထည့်ပါ
    # 👇 ဒီလိုင်းကို ဒီအတိုင်း ပြင်ပါ (birthdate ပါအောင်)
    (plan, usage, proof_status, _, price, _, goals, weaknesses, dream, career, money_mindset, relationship, birthdate) = user
    limit = PLAN_LIMITS[plan]["limit"]
    remaining = limit - usage
    price_usd = get_price_usd(price)
    ref_count = get_referral_count(user_id)
    level = usage // 100 + 1
    level_title = "🥉 Bronze" if level == 1 else "🥈 Silver" if level == 2 else "🥇 Gold" if level >= 3 else "🌱 Beginner"
    
    # (အောက်က မူရင်း code တွေ ဆက်သွားပါ)
    profile_preview = ""
    if goals: profile_preview += f"\n• 🎯 Goals: {goals}"
    if career: profile_preview += f"\n• 💼 Career: {career}"
    if money_mindset: profile_preview += f"\n• 💰 Money: {money_mindset}"
    if dream: profile_preview += f"\n• 🌟 Dream: {dream}"
    if weaknesses: profile_preview += f"\n• ⚠️ Weaknesses: {weaknesses}"
    if relationship: profile_preview += f"\n• ❤️ Relationship: {relationship}"
    if birthdate: profile_preview += f"\n• 🎂 Birthdate: {birthdate}" # ဗေဒင်အတွက် ထည့်ပါ
    await update.message.reply_text(f"📊 **Your Status**\n🏅 Level: {level_title} (Lv.{level})\n📌 Plan: **{plan}**\n📈 Usage: {usage}/{limit}\n🔋 Remaining: **{remaining}**\n🔍 Proof Status: {proof_status}\n👥 Referrals: **{ref_count}**{profile_preview}")
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type
    
    # Group ထဲမှာ သုံးရင် ညွှန်ကြားချက် ပြန်ပေး (Privacy & Cost သက်သာစေရန်)
    if chat_type in ["group", "supergroup"]:
        await update.message.reply_text(
            "⚠️ /ask command ကို Group ထဲမှာ တိုက်ရိုက်မသုံးပါနဲ့ဗျာ။\n"
            "🔒 ကိုယ်ရေးကိုယ်တာ မေးခွန်းတွေအတွက် Bot ရဲ့ Private Chat (DM) မှာ အသုံးပြုပေးပါ။\n"
            "ဒါမှမဟုတ် Group ထဲမှာ ကျွန်တော့်နာမည် ဒါမှမဟုတ် @BotUsername ကို ခေါ်ပြီး မေးနိုင်ပါတယ်။"
        )
        return

    if not check_limit(user_id):
        await update.message.reply_text("❌ သုံးခွင့်ကုန်သွားပါပြီ။ Plan အသစ်ရွေးပါ။")
        return

    if not context.args:
        await update.message.reply_text("❌ မေးခွန်းထည့်ပေးပါ။\nUsage: /ask <your question>")
        return

    question = " ".join(context.args)
    local_answer = get_local_response(question)
    if local_answer:
        increment_usage(user_id)
        await update.message.reply_text(local_answer)
        return

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    try:
        answer = await ask_model(question, user_id)
        answer = clean_text(answer)
    except Exception as e:
        logger.error(f"Ask command error: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
        return
    increment_usage(user_id)
    await update.message.reply_text(answer, disable_web_page_preview=True)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /profile <field> : <value>\nExample: /profile goals : ကိုယ်ပိုင်လုပ်ငန်းဖွင့်မယ်\nAllowed fields: goals, weaknesses, dream, career, money_mindset, relationship,birthdate")
        return
    text = " ".join(context.args)
    if ":" not in text:
        await update.message.reply_text("❌ Format: field : value")
        return
    field_raw, value = [p.strip() for p in text.split(":", 1)]
    field_map = {"goals": "goals", "weaknesses": "weaknesses", "dream": "dream", "career": "career", "money_mindset": "money_mindset", "relationship": "relationship", "birthdate": "birthdate",}
    key = field_map.get(field_raw)
    if not key:
        await update.message.reply_text("❌ field မမှန်ပါ။ goals/weaknesses/dream/career/money_mindset/relationship/birthdate ထဲက တစ်ခုသုံးပါ။")
        return
    update_profile(user_id, key, value)
    await update.message.reply_text(f"✅ `{key}` ကို update လုပ်ပြီးပါပြီ။")

async def habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /habit <habit>\nExample: /habit နေ့တိုင်း ၁၅ မိနစ် စာဖတ်မယ်")
        return
    habit_text = " ".join(context.args)
    add_habit(user_id, habit_text)
    await update.message.reply_text(f"✅ Habit အသစ် ထည့်ပြီးပါပြီ:\n\n• {habit_text}")

async def myhabits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    habits = get_habits(user_id)
    if not habits:
        await update.message.reply_text("😅 သင့် habits စာရင်း မရှိသေးပါ။")
        return
    text = "📝 **Your Habits (Latest 20)**\n"
    for habit_text, created_at in habits:
        text += f"\n• {habit_text}  ({created_at})"
    await update.message.reply_text(text)

async def proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 ငွေသွင်း proof screenshot ကို ဒီ chat ထဲမှာ Photo အနေနဲ့ ပို့ပေးပါ။")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not update.message.photo:
        return
    file_id = update.message.photo[-1].file_id
    update_proof(user_id, file_id)
    await update.message.reply_text("✅ Proof screenshot ကို လက်ခံရရှိပြီးပါပြီ။ Admin က စစ်ဆေးပါမယ်။")

# ====== Admin Commands ======
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /verify <user_id> <plan>")
        return
    target_id, plan = context.args[0], context.args[1]
    if plan not in PLAN_LIMITS:
        await update.message.reply_text("❌ Invalid plan.")
        return
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET plan=?, proof_status='approved', price=? WHERE user_id=?", (plan, PLAN_LIMITS[plan]["price"], target_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ User {target_id} ကို {plan} plan သို့ verify လုပ်ပြီးပါပြီ။")

async def pending_proofs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Admin only.")
        return
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, plan, proof_file_id, proof_timestamp FROM users WHERE proof_status='pending'")
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
    c.execute("UPDATE users SET proof_status='approved', usage_count=0, price=? WHERE user_id=?", (price, target_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Proof for user {target_id} approved. Plan: {plan}")

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
    c.execute("UPDATE users SET proof_status='rejected' WHERE user_id=?", (target_id,))
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

# ====== Main Message Handler ======
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
                await update.message.reply_text("❌ သုံးခွင့်ကုန်သွားပါပြီ။ Plan အသစ်ရွေးပါ။")
                return
            local_answer = get_local_response(text)
            if local_answer:
                increment_usage(user_id)
                await update.message.reply_text(local_answer)
                return
            await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
            try:
                answer = await ask_model(text, user_id)
                answer = clean_text(answer)
            except Exception as e:
                logger.error(f"Group message error: {e}")
                await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
                return
            increment_usage(user_id)
            await update.message.reply_text(answer, disable_web_page_preview=True)
            return

    if chat_type == "private":
        if not check_limit(user_id):
            await update.message.reply_text("❌ သုံးခွင့်ကုန်သွားပါပြီ။ Plan အသစ်ရွေးပါ။")
            return
        local_answer = get_local_response(text)
        if local_answer:
            increment_usage(user_id)
            await update.message.reply_text(local_answer)
            return
        await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
        try:
            answer = await ask_model(text, user_id)
            answer = clean_text(answer)
        except Exception as e:
            logger.error(f"Handle message error: {e}")
            await update.message.reply_text(f"⚠️ Error: {str(e)[:100]}")
            return
        increment_usage(user_id)
        bot_name = get_bot_name(text)
        if bot_name:
            answer = f"{bot_name} ပြောတယ်... {answer}"
        await update.message.reply_text(answer, disable_web_page_preview=True)

async def is_bot_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
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

# ====== Main ======
def main():
    init_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

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
    application.add_handler(CommandHandler("verify", verify))
    application.add_handler(CommandHandler("pending_proofs", pending_proofs))
    application.add_handler(CommandHandler("approve_proof", approve_proof))
    application.add_handler(CommandHandler("reject_proof", reject_proof))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    def run_flask():
        flask_app.run(host="0.0.0.0", port=5000)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=run_scheduler, args=(application.bot,), daemon=True).start()

    application.run_polling()

if __name__ == "__main__":
    main()
