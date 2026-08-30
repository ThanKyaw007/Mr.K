import os
import threading
import re
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
GROQ_API_KEY = "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"

# ====== Groq Settings ======
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== /start ======
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် **မစ္စတာတီ (Mr.T)** ပါ။\n"
        "ကျွန်တော် သင့်အတွက် အကူအညီပေးနိုင်တဲ့ လက်ထောက်တစ်ယောက်ပါ။\n"
        "ဘာမေးခွန်းမဆို ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

# ====== AI စကားပြော ======
def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text

    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် မစ္စတာတီ ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return

    update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "သင်ဟာ **မစ္စတာတီ (Mr.T)** လို့ခေါ်တဲ့ ယဉ်ကျေးပြီး အကူအညီပေးတတ်တဲ့ လက်ထောက်တစ်ယောက်ပါ။ မြန်မာလိုပဲ ဖြေပါ။ သင့်ကိုယ်သင် ရည်ညွှန်းတဲ့အခါ 'ကျွန်တော် မစ္စတာတီ' လို့ သုံးပါ။ သင့်ရဲ့အဖြေတွေမှာ ဘယ်လိုလင့်ခ်မျိုးမှ မထည့်ပါနဲ့။"},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }

        response = requests.post(GROQ_URL, headers=headers, json=data)
        response_data = response.json()

        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            
            # လင့်ခ်တွေကို ဖယ်ရှားမယ်
            reply = re.sub(r'https?://\S+', '', reply)
            reply = re.sub(r't\.me/\S+', '', reply)
            reply = re.sub(r'www\.\S+', '', reply)
            reply = re.sub(r'\[.*?\]\(.*?\)', '', reply)
            reply = re.sub(r'\s+', ' ', reply)
            reply = reply.strip()
            
            if len(reply) > 4000:
                reply = reply[:4000] + "..."
            update.message.reply_text(reply)
        else:
            error_msg = response_data.get("error", {}).get("message", "Unknown error")
            update.message.reply_text(f"😅 {error_msg}")

    except Exception as e:
        clean_error = re.sub(r'http\S+|https\S+', '', str(e))
        update.message.reply_text(f"😅 အားနည်းချက်ရှိလို့ ပြန်မဖြေနိုင်ဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")

# ====== run_bot ======
def run_bot():
    print("🤖 မစ္စတာတီ ဘော့စတင်နေပါပြီ...")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN မရှိပါ!")
        return

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    print("✅ မစ္စတာတီ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    updater.start_polling()
    updater.idle()

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
