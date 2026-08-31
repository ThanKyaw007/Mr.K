import os
import threading
import asyncio
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or "YOUR_GEMINI_API_KEY"

# ====== Gemini Settings ======
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== Bot Personality ======
BOT_NAMES = ["မစ္စတာတီ", "မစ္စတာသန်း", "ကိုသန်း"]

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

# ====== System Prompt ======
def get_system_prompt():
    return """
    သင်ဟာ မစ္စတာသန်း (Mr.T) — funny, friendly, motivational AI Bot ဖြစ်ပါတယ်။
    Than ကို မိတ်ဆွေလို ပြောပါ။ ရယ်စရာလေးတွေ ထည့်ပါ။
    အဖြေတွေကို မြန်မာလိုပဲ ပြန်ပါ။
    Money Mindset Mode: online income, skill တိုးတက်, money mindset, side hustle, motivation, action plan အကြံပေးပါ။
    Risky trading, guaranteed profit, illegal methods မပြောပါနဲ့။
    Attractive Personality Mode: self-confidence, communication skill, social skill, relationship advice ပေးပါ။
    Personality: Than ကို motivate လုပ်ပါ။ Funny tone, friendly tone နဲ့ ပြန်ပါ။
    """

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"🙏 မင်္ဂလာပါ {user_name}။ ကျွန်တော် မစ္စတာသန်း (Mr.T) ပါ။\n\n"
        "ဘာမေးမေး မြန်မာလိုပဲ မေးလိုက်ပါ။"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 အသုံးပြုနည်း\n\n"
        "/start - ဘော့စတင်\n"
        "/help - အကူအညီ\n"
        "ဘာမေးမေး မြန်မာလိုပဲ မေးပါ။"
    )

# ====== AI Chat (Gemini) ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    bot_name = get_bot_name(user_message)

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        full_prompt = f"{get_system_prompt()}\n\nUser: {user_message}\nAssistant:"
        response = model.generate_content(full_prompt)
        reply = response.text.strip()
        reply = clean_text(reply)

        if bot_name:
            reply = f"{bot_name} ပြောတယ်... {reply}"

        await update.message.reply_text(reply, disable_web_page_preview=True)

    except Exception as e:
        msg = clean_text(str(e)[:200])
        await update.message.reply_text(f"😅 Error — {msg}", disable_web_page_preview=True)

# ====== Run Bot ======
def run_bot():
    print("🤖 Bot starting...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
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
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    run_bot()
