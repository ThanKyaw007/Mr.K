import os
import threading
import asyncio
import requests
import json
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ====== Groq Settings ======
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

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
    import re
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
        f"🙏 မင်္ဂလာပါ {user_name}။ ကျွန်တော် **မစ္စတာသန်း** (Mr.T) ပါ။\n\n"
        "ဉာဏ်ကောင်းတယ်၊ ရယ်စရာကြိုက်တယ်၊ မြန်မာလိုလည်း ကောင်းကောင်းပြောတယ်။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 **အသုံးပြုနည်း**\n\n"
        "/start - ဘော့ကိုစတင်ရန်\n"
        "/help - အကူအညီ\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ မေးလိုက်ပါ။"
    )

# ====== AI စကားပြော ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    # နာမည်စစ်ဆေးခြင်း
    bot_name = get_bot_name(user_message)

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = (
            "သင်ဟာ **မစ္စတာသန်း** (Mr.T) ပါ။ "
            "သင်ဟာ ဉာဏ်ကောင်းတယ်၊ ရယ်စရာကြိုက်တယ်၊ မြန်မာလိုကောင်းကောင်းပြောတယ်။ "
            "အဖြေတွေကို မြန်မာလိုပဲ ဖြေပါ။ ရယ်စရာလေးတွေလည်း ထည့်ပါ။ "
            "မေးခွန်းတွေကို သဘာဝကျကျ၊ ရိုးရိုးသားသား ဖြေကြားပါ။"
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
            
            # နာမည်နဲ့ ဆက်စပ်ပြီး ရယ်စရာလေးထည့်မယ်
            if bot_name:
                reply = f"{bot_name} ပြောတယ်... {reply}"
            
            if len(reply) > 4000:
                reply = reply[:4000] + "..."
            await update.message.reply_text(reply)
        else:
            error_msg = response_data.get("error", {}).get("message", "Unknown error")
            await update.message.reply_text(f"😅 {error_msg}")

    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== run_bot ======
def run_bot():
    print("🤖 မစ္စတာသန်း (Mr.T) ဘော့စတင်နေပါပြီ...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.run_polling(allowed_updates=Update.ALL_TYPES))

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    # ဘော့ကို Thread နဲ့ စတင်မယ်
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    # Flask ဆာဗာကို 0.0.0.0 နဲ့ နားထောင်မယ်
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
