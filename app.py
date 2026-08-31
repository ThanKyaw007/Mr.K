import os
import threading
import asyncio
import requests
import json
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ====== Groq Settings ======
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "deepseek-r1-distill-llama-70b"

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

# ====== AI Chat ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    bot_name = get_bot_name(user_message)

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}".strip(),  # ← strip() ထည့်ထားတယ်
            "Content-Type": "application/json"
        }

        system_prompt = (
            "သင်ဟာ မစ္စတာသန်း (Mr.T) — funny, friendly, motivational AI Bot ဖြစ်ပါတယ်။ "
            "Than ကို မိတ်ဆွေလို ပြောပါ။ ရယ်စရာလေးတွေ ထည့်ပါ။ "
            "အဖြေတွေကို မြန်မာလိုပဲ ပြန်ပါ။ "
            "Money Mindset Mode: User မေးတဲ့အခါ online income, skill တိုးတက်, money mindset, side hustle, motivation, action plan "
            "အကြံပေးပါ။ Risky trading, guaranteed profit, illegal methods မပြောပါနဲ့။ Safe, ethical advice ပေးပါ။ "
            "Attractive Personality Mode: User မေးတဲ့အခါ self-confidence, communication skill, social skill, relationship advice "
            "healthy, respectful, confidence-building advice ပေးပါ။ Manipulation မလုပ်ပါနဲ့။ "
            "Personality: Than ကို motivate လုပ်ပါ။ Funny tone, friendly tone, human-like vibe နဲ့ ပြန်ပါ။ "
        )

        data = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 500,
            "temperature": 0.85
        }

        response = requests.post(GROQ_URL, headers=headers, json=data)
        response_data = response.json()

        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            reply = clean_text(reply)

            if bot_name:
                reply = f"{bot_name} ပြောတယ်... {reply}"

            await update.message.reply_text(reply)
        else:
            error_msg = response_data.get("error", {}).get("message", "Unknown error")
            await update.message.reply_text(f"😅 {error_msg}")

    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

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
