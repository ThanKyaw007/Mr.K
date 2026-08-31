import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

TELEGRAM_BOT_TOKEN = "8617869426:AAHSSyjxzn6Jd_NfOqseGM82ZoCo1EGGbNE"

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK", 200

COIN_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOT": "polkadot", "DOGE": "dogecoin", "LINK": "chainlink",
    "AVAX": "avalanche-2", "MATIC": "matic-network", "UNI": "uniswap"
}

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🚀 Crypto Price Bot\n\n"
        "/price BTC - Bitcoin ဈေးနှုန်း\n"
        "/price ETH - Ethereum ဈေးနှုန်း\n"
        "/list - ရနိုင်တဲ့ Coin စာရင်း\n"
        "/help - အကူအညီ"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📌 အသုံးပြုနည်း\n\n"
        "/price BTC - Bitcoin ဈေးနှုန်း\n"
        "/price ETH - Ethereum ဈေးနှုန်း\n"
        "/price SOL - Solana ဈေးနှုန်း\n"
        "/list - ရနိုင်တဲ့ Coin စာရင်း"
    )

def list_coins(update: Update, context: CallbackContext):
    coin_list = ", ".join(sorted(COIN_IDS.keys()))
    update.message.reply_text(f"📊 ရနိုင်တဲ့ Coin များ:\n\n{coin_list}")

def price(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("⚠️ /price BTC လို့ ရိုက်ပါ။")
        return
    
    symbol = context.args[0].upper()
    if symbol not in COIN_IDS:
        update.message.reply_text(f"⚠️ {symbol} ကို မထောက်ပံ့ပါ။ /list နဲ့ ကြည့်ပါ။")
        return
    
    try:
        coin_id = COIN_IDS[symbol]
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        price = data.get(coin_id, {}).get("usd")
        
        if price:
            update.message.reply_text(f"💵 {symbol}: ${price:,.2f} USD")
        else:
            update.message.reply_text("⚠️ ဈေးနှုန်းရယူလို့မရပါ။")
    except Exception as e:
        update.message.reply_text(f"😅 Error: {str(e)[:50]}")

def echo(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    if any(word in text for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text("မင်္ဂလာပါ! /help ကိုနှိပ်ပြီး ကြည့်ပါ။")
        return
    
    for symbol in COIN_IDS.keys():
        if symbol.lower() in text:
            context.args = [symbol]
            price(update, context)
            return
    
    update.message.reply_text("🤔 နားမလည်ပါ။ /help ကိုနှိပ်ပါ။")

def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("list", list_coins))
    dp.add_handler(CommandHandler("price", price))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
