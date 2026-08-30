import os
import threading
import re
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
OPENROUTER_API_KEY = "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"

# ====== OpenRouter Settings ======
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"

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
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် သင့်အတွက် အကူအညီပေးနိုင်တဲ့ လက်ထောက်တစ်ယောက်ပါ။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

# ====== handle_message ======
# ====== handle_message ======
def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text

    # နှုတ်ဆက်စကားတွေအတွက်
    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return

    update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "google/gemma-3-27b-it:free",  # ဒါမှမဟုတ် openrouter/free
            "messages": [
                {"role": "system", "content": "သင်ဟာ ယဉ်ကျေးပြီး အကူအညီပေးတတ်တဲ့ လက်ထောက်တစ်ယောက်ပါ။ မြန်မာလိုပဲ ဖြေပါ။ မေးခွန်းတွေကို သဘာဝကျကျ၊ ရိုးရိုးသားသား ဖြေကြားပါ။"},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }

        response = requests.post(OPENROUTER_URL, headers=headers, json=data)
        response_data = response.json()

        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            reply = re.sub(r'http\S+|https\S+', '', reply)
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
    print("🤖 ဘော့စတင်နေပါပြီ...")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN မရှိပါ!")
        return

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    updater.start_polling()
    updater.idle()

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
