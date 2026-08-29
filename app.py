import os
import threading
from flask import Flask
import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"
OPENROUTER_API_KEY = "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"

# ====== Flask ဝဘ်ဆာဗာ (Render အတွက်) ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== OpenRouter Settings ======
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-3.5-turbo"  # ဒီမော်ဒယ်က အလုပ်လုပ်ပါတယ် (Gemini က မရတော့ဘူး)

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။ ကျွန်တော် သင့်အတွက် အကူအညီပေးနိုင်တဲ့ လက်ထောက်တစ်ယောက်ပါ။\n\n"
        "🔹 /price [coin] - Crypto ဈေးနှုန်းကြည့်ရန်\n"
        "   (ဥပမာ: /price BTC, /price ETH)\n"
        "🔹 /analyze [coin] - နည်းပညာပိုင်း ခွဲခြမ်းစိတ်ဖြာရန်\n"
        "🔹 /news - နောက်ဆုံးရ Crypto သတင်းများ\n"
        "🔹 /ask [မေးခွန်း] - ဘာမဆိုမေးရန်\n"
        "🔹 /model - လက်ရှိသုံးနေတဲ့ မော်ဒယ်ကိုကြည့်ရန်\n"
        "🔹 /help - အကူအညီ"
    )
async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🙏 ကျေးဇူးပြုပြီး /ask [မေးခွန်း] လို့ ရိုက်ထည့်ပါ။")
        return
    
    user_question = " ".join(context.args)
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": """
                သင်ဟာ ယဉ်ကျေးပြီး အကူအညီပေးတတ်တဲ့ လက်ထောက်တစ်ယောက်ပါ။
                မေးခွန်းတွေကို သဘာဝကျကျ၊ ရိုးရိုးသားသား ဖြေကြားပါ။
                ကိုယ့်ကိုယ်ကို ဆရာကြီး၊ ပါရဂူ စသဖြင့် မခေါ်ပါနဲ့။
                အဖြေတွေကို မြန်မာလိုပဲ ဖြေပါ။
                ဖြေတဲ့အခါ ယဉ်ယဉ်ကျေးကျေးနဲ့ ရိုရိုသေသေ ဖြေပါ။
                မေးခွန်းတွေကို အားပေးတဲ့အနေနဲ့ "သိချင်တာမေးပါနော်" လိုမျိုး ပြောပေးပါ။
                Trading အကြောင်းသာမက အခြားမေးခွန်းတွေ (ဥပမာ- ဘာသာစကား၊ ပညာရေး၊ နည်းပညာ၊ နေ့စဉ်ဘဝအကြောင်း) ကိုလည်း ဖြေပေးပါ။
                """},
                {"role": "user", "content": user_question}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        
        response = requests.post(OPENROUTER_URL, headers=headers, json=data)
        response_data = response.json()
        
        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😅 ပြန်မဖြေနိုင်ဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")
            
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")
# ====== /news ======
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 သတင်းတွေကို ရှာနေပါတယ်...")
    
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        response = requests.get(url)
        data = response.json()
        
        news_list = data.get("Data", [])[:5]
        
        if not news_list:
            await update.message.reply_text("😅 သတင်းမရှိပါဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")
            return
        
        message = "📰 **နောက်ဆုံးရ Crypto သတင်းများ**\n\n"
        for i, news_item in enumerate(news_list, 1):
            title = news_item.get("title", "ခေါင်းစဉ်မရှိပါ")
            source = news_item.get("source", "အရင်းအမြစ်မရှိပါ")
            message += f"{i}. **{title}**\n   📌 {source}\n\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        await update.message.reply_text(f"😅 သတင်းယူလို့မရဘူး။ Error: {str(e)[:50]}")

# ====== /ask ======
async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး /ask [မေးခွန်း] လို့ ရိုက်ထည့်ပါ။")
        return
    
    user_question = " ".join(context.args)
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL,
            "messages": [{"role": "user", "content": user_question}],
            "max_tokens": 500,
            "temperature": 0.8
        }
        
        response = requests.post(OPENROUTER_URL, headers=headers, json=data)
        response_data = response.json()
        
        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😅 ပြန်မဖြေနိုင်ဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")
            
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== /model ======
async def show_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🧠 လက်ရှိသုံးနေတဲ့ မော်ဒယ်: `{MODEL}`")

# ====== /change ======
async def change_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MODEL
    if not context.args:
        await update.message.reply_text(
            "⚠️ မော်ဒယ်နာမည်ကို ထည့်ပါ။\n"
            "ဥပမာ: `/change openai/gpt-3.5-turbo`"
        )
        return
    
    MODEL = context.args[0]
    await update.message.reply_text(f"✅ မော်ဒယ်ကို `{MODEL}` သို့ ပြောင်းလိုက်ပါပြီ။")

# ====== သာမန်စာတိုတွေကို AI က ဖြေမယ် ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        await update.message.reply_text("မင်္ဂလာပါ! ကျွန်တော် Trading ဆရာကြီး ဘော့ပါ။ ဘာကူညီပေးရမလဲ?")
        return
    
    if "ဈေး" in user_message or "price" in user_message:
        words = user_message.split()
        for word in words:
            if word.upper() in ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"]:
                context.args = [word.upper()]
                await price(update, context)
                return
    
    await update.message.reply_text("🤔 စဉ်းစားနေပါတယ်...")
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL,
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": 500,
            "temperature": 0.8
        }
        
        response = requests.post(OPENROUTER_URL, headers=headers, json=data)
        response_data = response.json()
        
        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😅 ပြန်မဖြေနိုင်ဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")
            
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== run_bot Function (အပြင်မှာ တိုက်ရိုက်သတ်မှတ်ထားတယ်) ======
def run_bot():
    """Telegram ဘော့ကို သီးခြား Thread နဲ့ စတင်မယ်"""
    print("🤖 ဘော့စတင်နေပါပြီ...")
    
    # TELEGRAM_BOT_TOKEN ကို သုံးပါ
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handler တွေ
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("price", price))
    telegram_app.add_handler(CommandHandler("analyze", analyze))
    telegram_app.add_handler(CommandHandler("news", news))
    telegram_app.add_handler(CommandHandler("ask", ask_ai))
    telegram_app.add_handler(CommandHandler("model", show_model))
    telegram_app.add_handler(CommandHandler("change", change_model))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    # ဘော့ကို နောက်ခံ Thread နဲ့ စတင်မယ်
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    # Flask ဆာဗာကို စတင်မယ်
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
