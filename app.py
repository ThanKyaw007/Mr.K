import os
import threading
import asyncio
import requests
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
HF_TOKEN = os.environ.get("HF_TOKEN")  # Render မှာ ထည့်ပါ

# ====== Hugging Face Settings (ပိုကောင်းတဲ့ မော်ဒယ်) ======
MODEL = "google/gemma-2-2b-it"  # DialoGPT ထက် ပိုကောင်းတယ်
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

# ====== AI Chat (Hugging Face - Gemma) ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    bot_name = get_bot_name(user_message)

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        if not HF_TOKEN or HF_TOKEN == "hf_xxxxxxxxxxxxxxxxxxxxxxxxx":
            await update.message.reply_text("😅 Hugging Face Token မထည့်ရသေးဘူး။ Render မှာ HF_TOKEN ကို ထည့်ပါ။")
            return

        headers = {
            "Authorization": f"Bearer {HF_TOKEN}".strip(),
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": f"User: {user_message}\nAssistant:",
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.8,
                "do_sample": True
            }
        }

        response = requests.post(HF_URL, headers=headers, json=payload, timeout=60)
        response_data = response.json()

        if response.status_code == 200:
            if isinstance(response_data, list) and len(response_data) > 0:
                reply = response_data[0].get("generated_text", "").strip()
                # "Assistant:" ရဲ့ နောက်က အဖြေကို ယူမယ်
                if "Assistant:" in reply:
                    reply = reply.split("Assistant:")[-1].strip()
                elif reply.startswith("User:"):
                    reply = reply.split("User:")[0].strip()
                reply = clean_text(reply)
            else:
                reply = "အဖြေမရှိပါ"
        else:
            error_msg = response_data.get("error", "Unknown error")
            if "rate limit" in str(error_msg).lower():
                reply = "😅 တစ်ရက်ကို မေးခွန်းအရေအတွက် ပြည့်သွားပြီ။ နောက်နေ့မှ ပြန်မေးပါ။"
            elif "model" in str(error_msg).lower():
                reply = f"😅 မော်ဒယ် `{MODEL}` ကို ရှာမတွေ့ပါ။"
            else:
                reply = f"😅 Hugging Face error — {str(error_msg)[:100]}"

        if bot_name:
            reply = f"{bot_name} ပြောတယ်... {reply}"

        await update.message.reply_text(reply, disable_web_page_preview=True)

    except requests.exceptions.Timeout:
        await update.message.reply_text("😅 အချိန်လွန်သွားတယ်။ မော်ဒယ်က အိပ်စက်နေလို့ ပြန်နိုးဖို့ စက္ကန့် ၃၀ လောက် ကြာတယ်။ နောက်မှ ပြန်မေးပါ။")
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
