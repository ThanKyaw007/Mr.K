import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai  # ← import အသစ်

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = 8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE
GEMINI_API_KEY = "AQ.Ab8RN6K1YM_LneLp_lX5R7YyPa1RgBu9bR_1JzKa-q_WyocMug"

# ====== Gemini Client ======
client = genai.Client(api_key=GEMINI_API_KEY)  # ← ဒီလိုပြောင်းပါ

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် သင့်အတွက် အကူအညီပေးနိုင်တဲ့ လက်ထောက်တစ်ယောက်ပါ။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

# ====== handle_message ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        await update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return
    
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        # AI ကိုခေါ်တဲ့ပုံစံအသစ်
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_message
        )
        reply = response.text
        if len(reply) > 4000:
            reply = reply[:4000] + "..."
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== run_bot ======
def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN မရှိပါ! Environment Variables ကို စစ်ပါ။")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
