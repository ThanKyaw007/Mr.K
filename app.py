import os
import threading
from flask import Flask
import requests
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
MODEL = "openai/gpt-3.5-turbo"

# ====== /start Command ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 မင်္ဂလာပါ။\n\n"
        "ကျွန်တော် သင့်အတွက် အကူအညီပေးနိုင်တဲ့ လက်ထောက်တစ်ယောက်ပါ။\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝကျကျ၊ အသေးစိတ်ရှင်းပြပြီး ယဉ်ယဉ်ကျေးကျေး ပြန်ဖြေပေးပါ့မယ်။\n\n"
        "ဥပမာ:\n"
        "• Bitcoin ဆိုတာဘာလဲ\n"
        "• ဒီနေ့ ရာသီဥတုဘယ်လိုလဲ\n"
        "• အင်္ဂလိပ်စာ ဘယ်လိုလေ့လာရမလဲ\n"
        "• Trading ဆိုတာဘာလဲ\n\n"
        "သိချင်တာမေးပါနော်။"
    )

# ====== /help Command ======
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 အသုံးပြုနည်း:\n\n"
        "ဘာမေးခွန်းမဆို မြန်မာလိုပဲ ရိုးရိုးရှင်းရှင်း မေးလိုက်ပါ။\n"
        "ကျွန်တော် သဘာဝကျကျ၊ အသေးစိတ်ရှင်းပြပြီး ယဉ်ယဉ်ကျေးကျေး ပြန်ဖြေပေးပါ့မယ်။\n\n"
        "ဥပမာ:\n"
        "• Bitcoin ဆိုတာဘာလဲ\n"
        "• ဒီနေ့ ရာသီဥတုဘယ်လိုလဲ\n"
        "• အင်္ဂလိပ်စာ ဘယ်လိုလေ့လာရမလဲ\n"
        "• Trading ဆိုတာဘာလဲ"
    )

# ====== စာတိုင်းကို AI က ပြန်ဖြေမယ် ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    # နှုတ်ဆက်စကားတွေအတွက်
    if any(word in user_message.lower() for word in ["ဟိုင်း", "မင်္ဂလာ", "hello", "hi", "မင်္ဂလာပါ"]):
        await update.message.reply_text(
            "မင်္ဂလာပါ။ ကျွန်တော် ဒီမှာရှိပါတယ်။\n"
            "သိချင်တာမေးပါနော်၊ ကျွန်တော် အသေးစိတ်ရှင်းပြပေးပါ့မယ်။"
        )
        return

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
                အဖြေတွေကို မြန်မာလိုပဲ ဖြေပါ။
                ဖြေတဲ့အခါ ယဉ်ယဉ်ကျေးကျေးနဲ့ ရိုရိုသေသေ ဖြေပါ။
                
                မေးခွန်းတွေကို အားပေးတဲ့အနေနဲ့ "သိချင်တာမေးပါနော်" လိုမျိုး ပြောပေးပါ။
                
                မေးခွန်းတွေကို အသေးစိတ်ရှင်းပြပါ။
                ရှင်းပြတဲ့အခါ နားလည်လွယ်အောင် ရှင်းပြပါ။
                ဥပမာတွေနဲ့ တွဲပြီး ရှင်းပြပါ။
                
                Trading အကြောင်းသာမက အခြားမေးခွန်းတွေ (ဥပမာ- ဘာသာစကား၊ ပညာရေး၊ နည်းပညာ၊ နေ့စဉ်ဘဝအကြောင်း) ကိုလည်း ဖြေပေးပါ။
                """},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 800,
            "temperature": 0.7
        }

        response = requests.post(OPENROUTER_URL, headers=headers, json=data)
        response_data = response.json()

        if "choices" in response_data:
            reply = response_data["choices"][0]["message"]["content"].strip()
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text(
                "😅 ကျွန်တော် ပြန်မဖြေနိုင်ဘူး။\n"
                "နောက်မှ ပြန်ကြည့်ပါနော်။"
            )

    except Exception as e:
        await update.message.reply_text(
            f"😅 အားနည်းချက်ရှိလို့ ပြန်မဖြေနိုင်ဘူး။\n"
            f"Error: {str(e)[:100]}"
        )

# ====== run_bot Function ======
def run_bot():
    print("🤖 ဘော့စတင်နေပါပြီ...")

    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handler တွေ
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ ဘော့ အဆင်သင့်ဖြစ်ပါပြီ!")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

# ====== အဓိကအပိုင်း ======
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
