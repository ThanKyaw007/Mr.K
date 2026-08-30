import os
import threading
import re
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
HF_TOKEN = "hf_..."  # သင့် Hugging Face Token ကို ထည့်ပါ

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
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if 't.me' not in line and 'A-TOOLS' not in line and 'VIEW CHANNEL' not in line:
            if line.strip():
                clean_lines.append(line)
    text = '\n'.join(clean_lines)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် **Mr.T** (မစ္စတာသန်း) ပါ။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        await update.message.reply_text("မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။ သိချင်တာမေးပါနော်။")
        return

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        response = client.text_generation(
            model=MODEL,
            prompt=user_message,
            max_new_tokens=100,
            temperature=0.7
        )
        reply = clean_text(response)
        
        if len(reply) > 4000:
            reply = reply[:4000] + "..."
        if not reply:
            reply = "ကျွန်တော် နားလည်ပါတယ်။ ဒါပေမယ့် အခုအချိန်မှာ အဖြေရှာမရသေးပါဘူး။"
        await update.message.reply_text(reply)
        
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    
    # asyncio နဲ့ run မယ်
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.run_polling(allowed_updates=Update.ALL_TYPES))

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
