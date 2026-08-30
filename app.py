import os
import threading
import re
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
GROQ_API_KEY = "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"  # သင့် Groq API Key ကို ထည့်ပါ

# ====== Groq Settings ======
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# အမြန်ဆုံး မော်ဒယ်
# ပေါ့ပါးပြီး မြန်ဆန်တယ်
# အကောင်းဆုံး ရွေးချယ်မှု (အကြံပြုထားတယ်)
# တတိယ ဒါကို စမ်းကြည့်ပါ (ယေဘုယျသုံးမော်ဒယ်)
MODEL = "mixtral-8x7b-32768" 
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

    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
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
                {"role": "system", "content": "သင်ဟာ ယဉ်ကျေးပြီး အကူအညီပေးတတ်တဲ့ လက်ထောက်တစ်ယောက်ပါ။ မြန်မာလိုပဲ ဖြေပါ။ အဖြေတွေကို သဘာဝကျကျ၊ ရိုးရိုးသားသား ဖြေကြားပါ။"},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }

        response = requests.post(GROQ_URL, headers=headers, json=data)
        response_data = response.json()

        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            
            # ====== လင့်ခ်တွေကို ပြည့်ပြည့်စုံစုံ ဖယ်ရှားမယ် ======
            import re
            reply = re.sub(r'http[s]?://\S+', '', reply)      # http/https လင့်ခ်
            reply = re.sub(r'www\.\S+', '', reply)            # www လင့်ခ်
            reply = re.sub(r'\[.*?\]\(.*?\)', '', reply)      # Markdown လင့်ခ်
            reply = re.sub(r't\.me/\S+', '', reply)           # t.me လင့်ခ်
            reply = re.sub(r'https?://t\.me/\S+', '', reply)  # https://t.me လင့်ခ်
            
            # လင့်ခ်တွေကို ဖယ်လိုက်တဲ့အခါ နေရာလွတ်တွေ ကျန်နေရင် သန့်ရှင်းအောင်လုပ်မယ်
            reply = re.sub(r'\s+', ' ', reply)                # နေရာလွတ်များစွာကို တစ်ခုတည်းဖြစ်အောင်
            reply = reply.strip()                             # အစနဲ့အဆုံးက နေရာလွတ်တွေဖယ်
            
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
