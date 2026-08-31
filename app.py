import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

TELEGRAM_BOT_TOKEN = "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

def start(update: Update, context: CallbackContext):
    update.message.reply_text("မင်္ဂလာပါ! ဘော့အလုပ်လုပ်နေပါပြီ။")

def echo(update: Update, context: CallbackContext):
    update.message.reply_text(f"မင်းပြောတာ: {update.message.text}")

def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
