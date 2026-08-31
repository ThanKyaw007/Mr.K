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
TELEGRAM_BOT_TOKEN = "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
HF_TOKEN = "HFAKaYCqGLogsxVCcKihWZCStnMRFzJ"  # Hugging Face Token

# ====== Hugging Face Settings ======
MODEL = "microsoft/DialoGPT-medium"
HF_URL = f"https://api-inference.huggingface.co/models/{MODEL}"

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

# ====== AI Chat (Hugging Face) ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    bot_name = get_bot_name(user_message)

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}".strip(),
            "Content-Type": "application/json"
        }

        # Hugging Face API ကို ခေါ်မယ် (system prompt မပါဘူး)
        payload = {
            "inputs": user_message,
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.85,
                "do_sample": True
            }
        }

        response = requests.post(
            HF_URL,  # ← ပြင်ထားတယ်
            headers=headers,
            json=payload
        )
        response_data = response.json()

        # Response ကို ထုတ်ယူမယ်
        if response.status_code == 200:
            if isinstance(response_data, list) and len(response_data) > 0:
                reply = response_data[0].get("generated_text", "").strip()
                # user_message ကို ဖယ်ရှားမယ် (တစ်ခါတရံ ပါတတ်တယ်)
                if reply.startswith(user_message):
                    reply = reply[len(user_message):].strip()
                reply = clean_text(reply)
            else:
                reply = "အဖြေမရှိပါ"
        else:
            error_msg = response_data.get("error", "Unknown error")
            await update.message.reply_text(f"😅 {error_msg}", disable_web_page_preview=True)
            return

        if bot_name:
            reply = f"{bot_name} ပြောတယ်... {reply}"

        await update.message.reply_text(reply, disable_web_page_preview=True)

    except Exception as e:
        msg = str(e)[:100]
        msg = re.sub(r'https?://\S+', '', msg)
        msg = re.sub(r'www\.\S+', '', msg)
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
