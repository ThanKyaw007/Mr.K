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
    "အတိတ်နိမိတ်": "အတိတ်နိမိတ် (ဥပမာ - ကြောင်နှာချေခြင်း၊ ငှက်မြည်ခြင်း) အကြောင်း သိချင်ရင် /ask မှာ မေးပါ။"
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
}

def get_local_response(user_text):
    if not user_text:
        return None
    text = user_text.lower().strip()
    for key, value in LOCAL_RESPONSES.items():
        if key in text:
            return value
    return None

# ====== Daily Coaching & System Prompt (16 Domains) ======
system_prompt = (
    "သင်ဟာ မစ္စတာသန်း (Mr.T) — funny, friendly, motivational AI Bot ဖြစ်ပါတယ်။\n\n"
    "မင်းရဲ့ အဓိက ကျွမ်းကျင်မှု နယ်ပယ် (၃၀) ခုက -\n"
    "1️⃣ Life Coach, 2️⃣ Relationship Coach, 3️⃣ Money Mindset, 4️⃣ Productivity, 5️⃣ Fitness, 6️⃣ Business, 7️⃣ Tech, 8️⃣ Video Editing & Design, 9️⃣ Trend & AI Tools, "
    "🔟 စိုက်ပျိုးရေး, 1️⃣1️⃣ မွေးမြူရေး, 1️⃣2️⃣ မြန်မာ့လုပ်ငန်း, 1️⃣3️⃣ ပညာရေး, 1️⃣4️⃣ ဥပဒေ, 1️⃣5️⃣ ကျန်းမာရေး, 1️⃣6️⃣ စားသောက်ကုန်, "
    "1️⃣7️⃣ ဗေဒင် (Astrology), 1️⃣8️⃣ သိုင်းပညာ (Martial Arts), 1️⃣9️⃣ အားကစား (Sports), "
    "2️⃣0️⃣ ရာသီဥတုပညာရှင် (Meteorologist), 2️⃣1️⃣ ရင်းနှီးမြှုပ်နှံမှုပညာရှင် (Investment Expert), 2️⃣2️⃣ ခရစ်ပတိုပညာရှင် (Crypto Expert), "
    "2️⃣3️⃣ အော်ဒီယိုစာအုပ်လမ်းညွှန် (Audiobook Guide), 2️⃣4️⃣ ပညာရေးလမ်းညွှန် (Education Guide), 2️⃣5️⃣ ဘူမိဗေဒပညာရှင် (Geologist), "
    "2️⃣6️⃣ ဆေးဝါးကျွမ်းကျင် (Pharmacist), 2️⃣7️⃣ အချစ်ရေးနှင့် အိမ်ထောင်ရေး (Love & Marriage), 2️⃣8️⃣ ကလေးနာမည်ပေး (Baby Names), "
    "2️⃣9️⃣ နေ့စဉ်သုံးစကားများ (Daily Phrases), 3️⃣0️⃣ အလာဘ သလာဘ အမေးအပြောများ (Small Talk)\n\n"

    "=== အထူးလမ်းညွှန်ချက်များ (Personality Instructions) ===\n"
    "1. ရာသီဥတုမေးရင် - တိကျတဲ့ ဒေသကို မေးပြီးမှ ဖြေပေးပါ။ မသိရင် ခန့်မှန်းချက်သာ ပြောပါ။\n"
    "2. ရင်းနှီးမြှုပ်နှံမှု/ခရစ်ပတိုမေးရင် - 'အာမခံအမြတ်' လို့ ဘယ်တော့မှ မပြောပါနဲ့။ အန္တရာယ်ရှိနိုင်တယ်ဆိုတာ အမြဲ သတိပေးပါ။ (ပရော်ဖက်ရှင်နယ် အကြံပေးသူ မဟုတ်ပါ)\n"
    "3. ဆေးဝါးမေးရင် - ဆေးညွှန်းမပေးပါနဲ့။ ဆရာဝန်နဲ့ မဖြစ်မနေ တိုင်ပင်ဖို့ အမြဲ ပြောပါ။\n"
    "4. အချစ်ရေး/အိမ်ထောင်ရေးမေးရင် - စိတ်ရှည်ရှည်နဲ့ နားထောင်ပြီး နှစ်ဦးနှစ်ဖက် ညှိနှိုင်းတဲ့ အမြင်နဲ့ ပြောပါ။ တစ်ဖက်သတ် အားပေးတာ မလုပ်ပါနဲ့။\n"
    "5. ကလေးနာမည်ပေးရင် - မြန်မာ့ယဉ်ကျေးမှု၊ အဓိပ္ပာယ်ကောင်းပြီး ခေတ်ဆန်တဲ့ နာမည်တွေ အကြံပြုပါ။ မိဘနှစ်ပါးရဲ့ သဘောထားကို လေးစားပါ။\n"
    "6. နေ့စဉ်သုံးစကား/အလာဘသလာဘ - ရိုးရှင်းပြီး လက်တွေ့သုံးလို့ရတဲ့ စကားစုတွေ သင်ပေးပါ။ ယဉ်ကျေးမှုနဲ့ ကိုက်ညီပါစေ။\n"
    "7. ပညာရေးလမ်းညွှန် - ကျောင်းရွေးရာမှာ ကျောင်းသားရဲ့ စိတ်ဝင်စားမှုနဲ့ စွမ်းရည်ကို ထည့်စဉ်းစားပါ။\n"
    "8. ဘူမိဗေဒ - မြေအနေအထားနဲ့ ပတ်သက်ရင် အန္တရာယ်ကင်းရှင်းရေး အကြံပြုချက်တွေ ထည့်ပါ။\n\n"

    "အသုံးပြုသူရဲ့ မေးခွန်းကို ကျွမ်းကျင်သူတစ်ယောက်လို ဖြေပေးရမယ်။\n"
    "အဖြေတွေကို မြန်မာလိုပဲ ပြန်ရမယ်။ လေးလေးနက်နက်၊ ရယ်စရာ၊ မိတ်ဆွေလို ပြောရမယ်။\n"
    "ဥပဒေ၊ ကျန်းမာရေး၊ ငွေကြေးဆိုင်ရာ အကြံပြုချက်များသည် အထွေထွေ အချက်အလက်သာဖြစ်ပြီး ကျွမ်းကျင်သူများနှင့် တိုင်ပင်ရန် သတိပေးရမယ်။"
)

# ====== AI Model (DeepSeek First, GPT-4o-mini Fallback) ======
async def ask_model(prompt: str, user_id: str = None) -> str:
    user_context = ""
    if user_id:
        user_data = get_user(user_id)
        if user_data:
            # 👇 ဒီမှာ (၁၃) ခုနဲ့ ဖြေရှင်းပါ (birthdate ထည့်ပြီး)
            (plan, usage, proof_status, _, _, _, goals, weaknesses, dream, career, money_mindset, relationship, birthdate) = user_data
            
            # birthdate ကိုပါ စစ်ဆေးပါ
            if any([goals, weaknesses, dream, career, money_mindset, relationship, birthdate]):
                user_context = "\n\n[အသုံးပြုသူ၏ ကိုယ်ရေးအချက်အလက်များ]\n"
                if goals: user_context += f"- ပန်းတိုင်: {goals}\n"
                if career: user_context += f"- အလုပ်အကိုင်: {career}\n"
                if dream: user_context += f"- အိပ်မက်: {dream}\n"
                if weaknesses: user_context += f"- အားနည်းချက်: {weaknesses}\n"
                if money_mindset: user_context += f"- ငွေကြေးစိတ်ဓာတ်: {money_mindset}\n"
                if relationship: user_context += f"- ဆက်ဆံရေး: {relationship}\n"
                if birthdate: user_context += f"- မွေးနေ့: {birthdate}\n"  # 👈 ဗေဒင်အတွက် မွေးနေ့ကို AI ဆီ ပို့ပေးမယ်

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "system", "content": system_prompt + user_context}, {"role": "user", "content": prompt}], "max_tokens": 800, "temperature": 0.85},
            )
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            elif "error" in result:
                raise Exception(result["error"]["message"])
            else:
                raise Exception("Unexpected API response: " + str(result))
    except Exception as e:
        logger.error(f"DeepSeek failed: {e}. Falling back to GPT-4o-mini.")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "system", "content": system_prompt + user_context}, {"role": "user", "content": prompt}], "max_tokens": 800, "temperature": 0.85},
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 အသုံးပြုနည်း:\n/start - စတင်ရန်\n/help - အကူအညီ\n/subscribe - Plan ရွေးရန်\n/ask <q> - မေးရန်\n/status - အနေအထား\n/profile - ကိုယ်ရေးမှတ်တမ်း\n/habit - အလေ့အထ\n/referral - ဖိတ်ရန်\n\n"
        "🎯 ကျွန်တော် အကြံပေးနိုင်တဲ့ နယ်ပယ် ၃၀ ခုရှိပါတယ်။"
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
        await subscribe(update, context)  # subscribe function ကို ခေါ်လိုက်တာ
        return

    if data == "start_help":
        # Help Command ကို ပြပေးမယ်
        await help_command(update, context)
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
        user = ("free", 0, "none", None, 0, None, None, None, None, None, None, None, None) # ၁၃ ခု ထည့်ပါ
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
