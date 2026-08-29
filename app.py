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
MODEL = "google/gemini-2.5-flash"  # ဒါမှမဟုတ် "openai/gpt-3.5-turbo"

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 **Trading ဆရာကြီး ဘော့** မှ ကြိုဆိုပါတယ်!\n\n"
        "🔹 /price [coin] - Crypto ဈေးနှုန်းကြည့်ရန်\n"
        "   (ဥပမာ: /price BTC, /price ETH)\n"
        "🔹 /analyze [coin] - နည်းပညာပိုင်း ခွဲခြမ်းစိတ်ဖြာရန်\n"
        "🔹 /news - နောက်ဆုံးရ Crypto သတင်းများ\n"
        "🔹 /ask [မေးခွန်း] - AI ကို ဘာမဆိုမေးရန်\n"
        "🔹 /model - လက်ရှိသုံးနေတဲ့ မော်ဒယ်ကိုကြည့်ရန်\n"
        "🔹 /help - အကူအညီ"
    )

# ====== /help ======
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 **အသုံးပြုနည်း:**\n\n"
        "📈 **ဈေးနှုန်းကြည့်ရန်**\n"
        "/price BTC - Bitcoin ဈေးနှုန်း\n"
        "/price ETH - Ethereum ဈေးနှုန်း\n"
        "/price SOL - Solana ဈေးနှုန်း\n\n"
        "🔍 **ခွဲခြမ်းစိတ်ဖြာရန်**\n"
        "/analyze BTC - Bitcoin ကို နည်းပညာပိုင်း ခွဲခြမ်းစိတ်ဖြာမယ်\n\n"
        "📰 **သတင်းများ**\n"
        "/news - နောက်ဆုံးရ Crypto သတင်း ၅ ခု\n\n"
        "🤖 **AI ကိုမေးရန်**\n"
        "/ask [မေးခွန်း] - ဘာမဆို မေးလို့ရတယ်\n"
        "ဥပမာ: /ask Bitcoin အနာဂတ်ဘယ်လိုလဲ\n\n"
        "🧠 **မော်ဒယ်ပြောင်းရန်**\n"
        "/change [model_name] - မော်ဒယ်ပြောင်းမယ်"
    )

# ====== /price (CoinGecko API) ======
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး /price BTC လို့ ရိုက်ထည့်ပါ။")
        return
    
    symbol = context.args[0].upper()
    
    # CoinGecko ID mapping
    coin_ids = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
        "DOT": "polkadot", "DOGE": "dogecoin", "LINK": "chainlink",
        "AVAX": "avalanche-2", "MATIC": "matic-network", "UNI": "uniswap"
    }
    
    coin_id = coin_ids.get(symbol, symbol.lower())
    
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        price = data.get(coin_id, {}).get("usd")
        
        if price:
            await update.message.reply_text(f"💵 **{symbol}** ဈေးနှုန်း: **${price:,.2f}** USD")
        else:
            await update.message.reply_text(f"⚠️ {symbol} ကို ရှာမတွေ့ပါ။ /price BTC လို့ ရိုက်ပါ။")
    except Exception as e:
        await update.message.reply_text(f"😅 ဈေးနှုန်းယူလို့မရဘူး။ Error: {str(e)[:50]}")

# ====== /analyze (AI က ခွဲခြမ်းစိတ်ဖြာမယ်) ======
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး /analyze BTC လို့ ရိုက်ထည့်ပါ။")
        return
    
    coin = context.args[0].upper()
    await update.message.reply_text(f"🔍 {coin} ကို ခွဲခြမ်းစိတ်ဖြာနေပါတယ်...")
    
    try:
        # ဈေးနှုန်းအရင်ယူမယ်
        coin_ids = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano"
        }
        coin_id = coin_ids.get(coin, coin.lower())
        price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        price_response = requests.get(price_url)
        price_data = price_response.json()
        current_price = price_data.get(coin_id, {}).get("usd", "မရှိပါ")
        
        # AI ကို ခွဲခြမ်းစိတ်ဖြာခိုင်းမယ်
        prompt = f"""
        ကျေးဇူးပြုပြီး {coin} cryptocurrency ရဲ့ လက်ရှိဈေးကွက်အခြေအနေကို ခွဲခြမ်းစိတ်ဖြာပေးပါ။
        လက်ရှိဈေးနှုန်း: ${current_price}
        
        အောက်ပါအချက်တွေကို ထည့်သွင်းစဉ်းစားပေးပါ:
        1. ဈေးကွက်အခြေအနေ (မတည်ငြိမ်မှု၊ လမ်းကြောင်း)
        2. နည်းပညာပိုင်း အညွှန်းကိန်းများ (RSI, Moving Average)
        3. ဝယ်သင့်/ရောင်းသင့် အကြံပြုချက်
        4. အနာဂတ်ခန့်မှန်းချက်
        
        မြန်မာလိုနဲ့ ရှင်းရှင်းလင်းလင်း ဖြေပေးပါ။
        """
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
            "temperature": 0.7
        }
        
        response = requests.post(OPENROUTER_URL, headers=headers, json=data)
        response_data = response.json()
        
        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            await update.message.reply_text(f"📊 **{coin} ခွဲခြမ်းစိတ်ဖြာချက်**\n\n{reply}")
        else:
            await update.message.reply_text("😅 ခွဲခြမ်းစိတ်ဖြာလို့မရဘူး။ နောက်မှ ပြန်ကြည့်ပါ။")
            
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== /news (CryptoCompare API) ======
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 သတင်းတွေကို ရှာနေပါတယ်...")
    
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        response = requests.get(url)
        data = response.json()
        
        news_list = data.get("Data", [])[:5]  # သတင်း ၅ ခုပဲယူမယ်
        
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

# ====== /ask (AI ကိုမေးရန်) ======
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
    
    # သာမန်စကားပြောပုံစံ
    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        await update.message.reply_text("မင်္ဂလာပါ! ကျွန်တော် Trading ဆရာကြီး ဘော့ပါ။ ဘာကူညီပေးရမလဲ?")
        return
    
    if "ဈေး" in user_message or "price" in user_message:
        # ဈေးနှုန်းမေးတာဆိုရင်
        words = user_message.split()
        for word in words:
            if word.upper() in ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"]:
                context.args = [word.upper()]
                await price(update, context)
                return
    
    # ကျန်တာတွေကို AI က ဖြေမယ်
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

# ====== အဓိကအပိုင်း ======
def main():
    def run_bot():
    """Telegram ဘော့ကို သီးခြား Thread နဲ့ စတင်မယ်"""
    print("🤖 ဘော့စတင်နေပါပြီ...")
    
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # ====== ခင်ဗျားရဲ့ Handler တွေ အကုန်လုံးကို ဒီမှာ ထည့်ပါ ======
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("price", price))
    telegram_app.add_handler(CommandHandler("analyze", analyze))
    telegram_app.add_handler(CommandHandler("news", news))
    telegram_app.add_handler(CommandHandler("ask", ask_ai))
    telegram_app.add_handler(CommandHandler("model", show_model))
    telegram_app.add_handler(CommandHandler("change", change_model))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # ==========================================================
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # ဘော့ကို နောက်ခံ Thread နဲ့ စတင်မယ်
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    # Flask ဆာဗာကို စတင်မယ် (Render ရဲ့ PORT ကို နားထောင်မယ်)
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)