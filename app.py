import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====== API Keys ======
TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"

# ====== Flask ======
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

# ====== CoinGecko API ======
COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOT": "polkadot",
    "DOGE": "dogecoin",
    "LINK": "chainlink",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "UNI": "uniswap"
}

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Crypto Price Bot**\n\n"
        "/price BTC - Bitcoin ဈေးနှုန်း\n"
        "/price ETH - Ethereum ဈေးနှုန်း\n"
        "/price SOL - Solana ဈေးနှုန်း\n"
        "/list - ရနိုင်တဲ့ Coin စာရင်း\n"
        "/help - အကူအညီ"
    )

# ====== /help ======
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 **အသုံးပြုနည်း**\n\n"
        "/price BTC - Bitcoin ဈေးနှုန်း\n"
        "/price ETH - Ethereum ဈေးနှုန်း\n"
        "/price SOL - Solana ဈေးနှုန်း\n"
        "/list - ရနိုင်တဲ့ Coin စာရင်း"
    )

# ====== /list ======
async def list_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin_list = ", ".join(sorted(COIN_IDS.keys()))
    await update.message.reply_text(f"📊 **ရနိုင်တဲ့ Coin များ**\n\n{coin_list}")

# ====== /price ======
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ /price BTC လို့ ရိုက်ပါ။")
        return
    
    symbol = context.args[0].upper()
    if symbol not in COIN_IDS:
        await update.message.reply_text(f"⚠️ {symbol} ကို မထောက်ပံ့ပါ။ /list နဲ့ ကြည့်ပါ။")
        return
    
    try:
        coin_id = COIN_IDS[symbol]
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        price = data.get(coin_id, {}).get("usd")
        
        if price:
            await update.message.reply_text(
                f"💵 **{symbol}** ဈေးနှုန်း\n\n"
                f"💰 ${price:,.2f} USD"
            )
        else:
            await update.message.reply_text("⚠️ ဈေးနှုန်းရယူလို့မရပါ။")
    except Exception as e:
        await update.message.reply_text(f"😅 Error: {str(e)[:50]}")

# ====== Echo ======
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    
    if any(word in text for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        await update.message.reply_text("မင်္ဂလာပါ! /help ကိုနှိပ်ပြီး ကြည့်ပါ။")
        return
    
    for symbol in COIN_IDS.keys():
        if symbol.lower() in text:
            context.args = [symbol]
            await price(update, context)
            return
    
    await update.message.reply_text("🤔 နားမလည်ပါ။ /help ကိုနှိပ်ပါ။")

# ====== run_bot ======
def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_coins))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
