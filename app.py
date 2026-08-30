import os
import threading
import re
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
HF_TOKEN = "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"  # သင့် Hugging Face Token ကို ထည့်ပါ

# ====== Hugging Face Settings ======
hf_client = InferenceClient(token=HF_TOKEN)
HF_MODEL = "microsoft/DialoGPT-medium"  # ဒီမော်ဒယ်ကို ပြောင်းလို့ရပါတယ်

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
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if 't.me' not in line and 'A-TOOLS' not in line and 'VIEW CHANNEL' not in line:
            if line.strip():
                clean_lines.append(line)
    text = '\n'.join(clean_lines)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် **Mr.T** (မစ္စတာသန်း) ပါ။\n\n"
        "📌 အသုံးပြုနည်း:\n"
        "/ban - အသုံးပြုသူကို ပိတ်ဆို့ရန် (Reply နှိပ်ပါ)\n"
        "/warn - အသုံးပြုသူကို သတိပေးရန် (Reply နှိပ်ပါ)\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

# ====== /ban ======
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး ပိတ်ဆို့ချင်တဲ့သူရဲ့ မက်ဆေ့ချ်ကို Reply နှိပ်ပါ။")
        return
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.message.bot.ban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text(f"✅ အသုံးပြုသူကို ပိတ်ဆို့ပြီးပါပြီ။")
    except Exception as e:
        await update.message.reply_text(f"❌ ပိတ်ဆို့လို့မရပါ။ အကြောင်းရင်း: {e}")

# ====== /warn ======
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး သတိပေးချင်တဲ့သူရဲ့ မက်ဆေ့ချ်ကို Reply နှိပ်ပါ။")
        return
    user = update.message.reply_to_message.from_user
    await update.message.reply_text(f"⚠️ {user.first_name} ကို သတိပေးလိုက်ပါပြီ။")

# ====== ကြိုဆိုခြင်း ======
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(f"👋 {member.first_name} ကို ကြိုဆိုပါတယ်!")

# ====== သော့ချက်စကားလုံး ======
async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text and "မင်္ဂလာပါ" in text:
        await update.message.reply_text("မင်္ဂလာပါ! ကျွန်တော် ဒီမှာရှိပါတယ်။")
        return
    if text and "ကျေးဇူး" in text:
        await update.message.reply_text("ရပါတယ်။ ကြိုဆိုပါတယ်။")

# ====== AI စကားပြော (Hugging Face) ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        await update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        response = hf_client.text_generation(
            model=HF_MODEL,
            prompt=user_message,
            max_new_tokens=200,
            temperature=0.7
        )
        reply = response
        reply = clean_text(reply)
        
        if len(reply) > 4000:
            reply = reply[:4000] + "..."
        if not reply:
            reply = "ကျွန်တော် နားလည်ပါတယ်။ ဒါပေမယ့် အခုအချိန်မှာ အဖြေရှာမရသေးပါဘူး။"
        await update.message.reply_text(reply)
        
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== run_bot ======
def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
