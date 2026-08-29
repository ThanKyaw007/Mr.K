import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ====== Render Environment ကနေ Token ကို ယူမယ် ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== Telegram Handler ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("မင်္ဂလာပါ! ဘော့အလုပ်လုပ်နေပါပြီ။")

# ====== run_bot ======
def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN မရှိပါ! Environment Variables ကို စစ်ပါ။")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
