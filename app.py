import os
import threading
import re
import requests
from flask import Flask
from telegram import Update  # ← ဒီလိုင်း ပါရပါမယ်
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext
from telegram.ext import filters
from google import genai

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
GEMINI_API_KEY = "AQ.Ab8RN6K1YM_LneLp_lX5R7YyPa1RgBu9bR_1JzKa-q_WyocMug"  # သင့် Gemini API Key ကို ထည့်ပါ

# ====== Gemini Settings ======
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash"

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== လင့်ခ်နဲ့ ကြော်ငြာတွေကို ဖယ်ရှားတဲ့ Function ======
def clean_text(text):
    # လင့်ခ်အကုန်ဖယ်
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    
    # မလိုအပ်တဲ့ စာကြောင်းတွေကို ဖယ်
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if 't.me' not in line and 'A-TOOLS' not in line and 'VIEW CHANNEL' not in line:
            if line.strip():
                clean_lines.append(line)
    text = '\n'.join(clean_lines)
    
    # နေရာလွတ်တွေကို သန့်ရှင်းအောင်လုပ်
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ====== /start ======
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် **Mr.T** (မစ္စတာသန်း) ပါ။\n\n"
        "📌 အသုံးပြုနည်း:\n"
        "/ban - အသုံးပြုသူကို ပိတ်ဆို့ရန် (Reply နှိပ်ပါ)\n"
        "/warn - အသုံးပြုသူကို သတိပေးရန် (Reply နှိပ်ပါ)\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

# ====== /ban ======
def ban(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး ပိတ်ဆို့ချင်တဲ့သူရဲ့ မက်ဆေ့ချ်ကို Reply နှိပ်ပါ။")
        return
    user_id = update.message.reply_to_message.from_user.id
    try:
        update.message.bot.ban_chat_member(update.effective_chat.id, user_id)
        update.message.reply_text(f"✅ အသုံးပြုသူကို ပိတ်ဆို့ပြီးပါပြီ။")
    except Exception as e:
        update.message.reply_text(f"❌ ပိတ်ဆို့လို့မရပါ။ အကြောင်းရင်း: {e}")

# ====== /warn ======
def warn(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး သတိပေးချင်တဲ့သူရဲ့ မက်ဆေ့ချ်ကို Reply နှိပ်ပါ။")
        return
    user = update.message.reply_to_message.from_user
    update.message.reply_text(f"⚠️ {user.first_name} ကို သတိပေးလိုက်ပါပြီ။")

# ====== ကြိုဆိုခြင်း ======
def welcome(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        update.message.reply_text(f"👋 {member.first_name} ကို ကြိုဆိုပါတယ်!")

# ====== သော့ချက်စကားလုံး ======
def auto_reply(update: Update, context: CallbackContext):
    text = update.message.text
    if text and "မင်္ဂလာပါ" in text:
        update.message.reply_text("မင်္ဂလာပါ! ကျွန်တော် ဒီမှာရှိပါတယ်။")
        return
    if text and "ကျေးဇူး" in text:
        update.message.reply_text("ရပါတယ်။ ကြိုဆိုပါတယ်။")

# ====== AI စကားပြော (Gemini) ======
def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text

    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return

    update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_message
        )
        reply = response.text
        
        # ====== လင့်ခ်နဲ့ မလိုအပ်တဲ့စာသားတွေကို ဖယ်ရှားမယ် ======
        reply = clean_text(reply)
        
        if len(reply) > 4000:
            reply = reply[:4000] + "..."
        
        # အဖြေဗလာဖြစ်နေရင် ပုံမှန်စာသားပြန်ပို့မယ်
        if not reply:
            reply = "ကျွန်တော် နားလည်ပါတယ်။ ဒါပေမယ့် အခုအချိန်မှာ အဖြေရှာမရသေးပါဘူး။"
        
        update.message.reply_text(reply)
        
    except Exception as e:
        update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== run_bot ======
def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN မရှိပါ!")
        return

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ban", ban))
    dp.add_handler(CommandHandler("warn", warn))
    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, welcome))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, auto_reply))
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
