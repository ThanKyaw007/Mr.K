import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

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

# ====== CoinGecko API Settings ======
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# Coin ID mapping
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
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "NEAR": "near",
    "FTM": "fantom",
    "SUI": "sui",
    "APT": "aptos",
    "ARB": "arbitrum"
}

# ====== /start ======
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🚀 **Crypto Price Bot** မှ ကြိုဆိုပါတယ်!\n\n"
        "📈 /price [coin] - Crypto ဈေးနှုန်းကြည့်ရန်\n"
        "   ဥပမာ: /price BTC, /price ETH, /price SOL\n"
        "📊 /list - ရနိုင်တဲ့ Coin စာရင်းကိုကြည့်ရန်\n"
        "🔄 /convert [amount] [from] [to] - ငွေကြေးပြောင်းရန်\n"
        "   ဥပမာ: /convert 1 BTC USD\n"
        "ℹ️ /help - အကူအညီ"
    )

# ====== /help ======
def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📌 **အသုံးပြုနည်း**\n\n"
        "/price BTC - Bitcoin ဈေးနှုန်း\n"
        "/price ETH - Ethereum ဈေးနှုန်း\n"
        "/price SOL - Solana ဈေးနှုန်း\n"
        "/list - ရနိုင်တဲ့ Coin စာရင်း\n"
        "/convert 1 BTC USD - 1 Bitcoin ရဲ့ USD တန်ဖိုး\n\n"
        "ရနိုင်တဲ့ Coin တွေ: BTC, ETH, SOL, BNB, XRP, ADA, DOT, DOGE, LINK, AVAX, MATIC, UNI, ATOM, LTC, BCH, NEAR, FTM, SUI, APT, ARB"
    )

# ====== /list ======
def list_coins(update: Update, context: CallbackContext):
    coin_list = ", ".join(sorted(COIN_IDS.keys()))
    update.message.reply_text(
        f"📊 **ရနိုင်တဲ့ Coin စာရင်း**\n\n"
        f"{coin_list}\n\n"
        "ဈေးနှုန်းကြည့်ရန်: /price BTC"
    )

# ====== /price ======
def price(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text(
            "⚠️ ကျေးဇူးပြုပြီး /price BTC လို့ ရိုက်ထည့်ပါ။\n\n"
            "ရနိုင်တဲ့ Coin တွေ: BTC, ETH, SOL, BNB, XRP, ADA, DOT, DOGE, LINK, AVAX, MATIC, UNI, ATOM, LTC, BCH, NEAR, FTM, SUI, APT, ARB"
        )
        return
    
    symbol = context.args[0].upper()
    
    if symbol not in COIN_IDS:
        update.message.reply_text(f"⚠️ {symbol} ကို မထောက်ပံ့ပါဘူး။ /list နဲ့ စာရင်းကြည့်ပါ။")
        return
    
    coin_id = COIN_IDS[symbol]
    
    try:
        # CoinGecko API ကိုခေါ်မယ်
        params = {
            "ids": coin_id,
            "vs_currencies": "usd"
        }
        response = requests.get(COINGECKO_URL, params=params)
        data = response.json()
        
        price = data.get(coin_id, {}).get("usd")
        
        if price:
            update.message.reply_text(
                f"💵 **{symbol}** ဈေးနှုန်း\n\n"
                f"💰 ${price:,.2f} USD\n"
                f"🕐 {update.message.date.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            update.message.reply_text(f"⚠️ {symbol} ဈေးနှုန်းကို ရယူလို့မရပါ။ နောက်မှ ပြန်ကြည့်ပါ။")
            
    except Exception as e:
        update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== /convert ======
def convert(update: Update, context: CallbackContext):
    if len(context.args) < 3:
        update.message.reply_text(
            "⚠️ ကျေးဇူးပြုပြီး /convert [amount] [from] [to] လို့ ရိုက်ထည့်ပါ။\n\n"
            "ဥပမာ: /convert 1 BTC USD"
        )
        return
    
    try:
        amount = float(context.args[0])
        from_coin = context.args[1].upper()
        to_coin = context.args[2].upper()
        
        if from_coin not in COIN_IDS:
            update.message.reply_text(f"⚠️ {from_coin} ကို မထောက်ပံ့ပါဘူး။")
            return
        
        coin_id = COIN_IDS[from_coin]
        
        params = {
            "ids": coin_id,
            "vs_currencies": to_coin.lower()
        }
        response = requests.get(COINGECKO_URL, params=params)
        data = response.json()
        
        price = data.get(coin_id, {}).get(to_coin.lower())
        
        if price:
            result = amount * price
            update.message.reply_text(
                f"🔄 **ငွေကြေးပြောင်းလဲခြင်း**\n\n"
                f"{amount:,.2f} {from_coin} = {result:,.2f} {to_coin.upper()}\n"
                f"💰 1 {from_coin} = {price:,.2f} {to_coin.upper()}"
            )
        else:
            update.message.reply_text(f"⚠️ {to_coin} ဈေးနှုန်းကို ရယူလို့မရပါ။")
            
    except ValueError:
        update.message.reply_text("⚠️ ကျေးဇူးပြုပြီး နံပါတ်မှန်မှန် ထည့်ပါ။")
    except Exception as e:
        update.message.reply_text(f"😅 Error: {str(e)[:100]}")

# ====== Echo (သာမန်စာတိုများအတွက်) ======
def echo(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    
    if any(word in text for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi"]):
        update.message.reply_text(
            "မင်္ဂလာပါ! ကျွန်တော် **Crypto Price Bot** ပါ။\n\n"
            "/price BTC - Bitcoin ဈေးနှုန်းကြည့်ရန်\n"
            "/help - အကူအညီ"
        )
        return
    
    # Coin symbol ပါရင် ဈေးနှုန်းပြမယ်
    for symbol in COIN_IDS.keys():
        if symbol.lower() in text:
            context.args = [symbol]
            price(update, context)
            return
    
    update.message.reply_text(
        "🤔 ကျွန်တော် နားမလည်ပါဘူး။\n\n"
        "/help ကိုနှိပ်ပြီး အသုံးပြုနည်းကို ကြည့်ပါ။"
    )

# ====== run_bot ======
def run_bot():
    print("🤖 Crypto Price Bot စတင်နေပါပြီ...")
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("list", list_coins))
    dp.add_handler(CommandHandler("price", price))
    dp.add_handler(CommandHandler("convert", convert))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    
    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
