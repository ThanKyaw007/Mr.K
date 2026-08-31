import os
import threading
import re
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from huggingface_hub import InferenceClient

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
HF_TOKEN = "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"

# ====== Hugging Face Settings ======
client = InferenceClient(token=HF_TOKEN)
MODEL = "microsoft/DialoGPT-medium"

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

def clean_text(text):
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် **Mr.T** (မစ္စတာသန်း) ပါ။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text

    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return

    update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        response = client.text_generation(
            model=MODEL,
            prompt=user_message,
            max_new_tokens=300,  # ← ဒါကို ၃၀၀ ထားပါ
            temperature=0.7
        )
        reply = clean_text(response)
        
        if len(reply) > 4000:
            reply = reply[:4000] + "..."
        if not reply:
            reply = "ကျွန်တော် နားလည်ပါတယ်။ ဒါပေမယ့် အခုအချိန်မှာ အဖြေရှာမရသေးပါဘူး။"
        update.message.reply_text(reply)
        
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Invalid token" in error_msg:
            update.message.reply_text("😅 Hugging Face Token မှားနေတယ်။ ကျေးဇူးပြုပြီး ပြန်စစ်ပါ။")
        elif "429" in error_msg:
            update.message.reply_text("😅 တစ်ရက်တာ မေးခွန်းအရေအတွက် ပြည့်သွားပြီ။ နောက်နေ့မှ ပြန်မေးပါ။")
        else:
            update.message.reply_text(f"😅 Error: {str(e)[:200]}")

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
