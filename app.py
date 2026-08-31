import os
import threading
import asyncio
import json
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHzomx_Uikd_S69UxCGAp4avOWUx6ytqVM"
GROQ_API_KEY = "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"

# ====== Groq Settings ======
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

# ====== Memory Settings ======
MAX_HISTORY = 10
conversations = {}

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== နာမည်တွေကို သိအောင်လုပ်မယ် ======
BOT_NAMES = ["မစ္စတာတီ", "မစ္စတာသန်း", "ကိုသန်း", "mr t", "mr.t", "mrt"]

def get_bot_name(text):
    for name in BOT_NAMES:
        if name.lower() in text.lower():
            return name
    return None

def clean_text(text):
    import re
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"🙏 မင်္ဂလာပါ {user_name}။ ကျွန်တော် **မစ္စတာသန်း** (Mr.T) ပါ။\n\n"
        "ကျွန်တော်က ဉာဏ်ကောင်းတယ်၊ ရယ်စရာကြိုက်တယ်၊ မြန်မာလိုလည်း ကောင်းကောင်းပြောတယ်။\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝအတိုင်း ပြန်ဖြေပေးပါ့မယ်။\n\n"
        "📌 /help - အကူအညီ\n"
        "📌 /clear - စကားဝိုင်းမှတ်တမ်းရှင်းရန်"
    )

# ====== /help ======
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 **အသုံးပြုနည်း**\n\n"
        "ကျွန်တော်ကို ဒီလိုခေါ်လို့ရတယ်:\n"
        "- မစ္စတာတီ\n"
        "- မစ္စတာသန်း\n"
        "- ကိုသန်း\n\n"
        "📌 **Command များ**\n"
        "/start - ဘော့ကိုစတင်ရန်\n"
        "/help - အကူအညီ\n"
        "/clear - စကားဝိုင်းမှတ်တမ်းရှင်းရန်\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ မေးလိုက်ပါ။"
    )

# ====== /clear ======
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in conversations:
        conversations[user_id] = []
    await update.message.reply_text("🧹 စကားဝိုင်းမှတ်တမ်းကို ရှင်းလိုက်ပါပြီ။")

# ====== AI စကားပြော ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    user_name = update.effective_user.first_name

    bot_name = get_bot_name(user_message)
    
    if user_id not in conversations:
        conversations[user_id] = []

    system_prompt = (
        "သင်ဟာ **မစ္စတာသန်း** (Mr.T) ပါ။ "
        "သင်ဟာ ဉာဏ်ကောင်းတယ်၊ ရယ်စရာကြိုက်တယ်၊ မြန်မာလိုကောင်းကောင်းပြောတယ်။ "
        "သုံးစွဲသူက သင့်ကို မစ္စတာတီ၊ မစ္စတာသန်း၊ ကိုသန်း ဆိုပြီး ခေါ်နိုင်တယ်။ "
        "အဖြေတွေကို မြန်မာလိုပဲ ဖြေပါ။ ရယ်စရာလေးတွေလည်း ထည့်ပါ။ "
        "မေးခွန်းတွေကို သဘာဝကျကျ၊ ရိုးရိုးသားသား ဖြေကြားပါ။ "
        "သင့်ကိုယ်သင် ရည်ညွှန်းတဲ့အခါ 'ကျွန်တော်' ဆိုတဲ့ စကားလုံးကိုပဲ သုံးပါ။"
    )

    conversations[user_id].append({"role": "user", "content": user_message})
    
    if len(conversations[user_id]) > MAX_HISTORY * 2:
        conversations[user_id] = conversations[user_id][-MAX_HISTORY * 2:]

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversations[user_id])

    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.85
        }

        response = requests.post(GROQ_URL, headers=headers, json=data)
        response_data = response.json()

        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            reply = clean_text(reply)
            
            conversations[user_id].append({"role": "assistant", "content": reply})
            
            if bot_name:
                import random
                joke_responses = [
                    f"အေး... {bot_name} ပြောတာကို နားထောင်ပါ။ {reply}",
                    f"{bot_name} ပြောတယ်... {reply}",
                    f"ဟုတ်ကဲ့... {bot_name} က {reply}",
                ]
                reply = random.choice(joke_responses)
            
            if len(reply) > 4000:
                reply = reply[:4000] + "..."
            await update.message.reply_text(reply)
        else:
            error_msg = response_data.get("error", {}).get("message", "Unknown error")
            await update.message.reply_text(f"😅 {error_msg}")

    except Exception as e:
        await update.message.reply_text(f"😅 အားနည်းချက်ရှိလို့ ပြန်မဖြေနိုင်ဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")

# ====== run_bot ======
def run_bot():
    print("🤖 မစ္စတာသန်း (Mr.T) ဘော့စတင်နေပါပြီ...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")  # ← ဒီစာကြောင်း မရောက်သေးဘူး
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.run_polling(allowed_updates=Update.ALL_TYPES))
