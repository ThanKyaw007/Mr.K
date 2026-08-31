import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from google import genai

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
GEMINI_API_KEY = "AQ.Ab8RN6K1YM_LneLp_lX5R7YyPa1RgBu9bR_1JzKa-q_WyocMug"  # Google AI Studio ကနေ ရယူပါ

# ====== Gemini Settings ======
client = genai.Client(api_key=GEMINI_API_KEY)

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် **Mr.T** (မစ္စတာသန်း) ပါ။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။"
    )

def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text
    update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_message
        )
        reply = response.text
        if len(reply) > 4000:
            reply = reply[:4000] + "..."
        update.message.reply_text(reply)
    except Exception as e:
        update.message.reply_text(f"😅 Error: {str(e)[:100]}")

def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
