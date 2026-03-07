import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "MASUKKAN_TOKEN_BOT_ANDA"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Stock Scanner Bot Aktif\n\nCommand:\n/price BBCA.JK"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        ticker = context.args[0]

        data = yf.Ticker(ticker)

        hist = data.history(period="1d")

        price = hist["Close"].iloc[-1]

        await update.message.reply_text(
            f"{ticker}\nPrice : {price}"
        )

    except:

        await update.message.reply_text(
            "Gunakan format: /price BBCA.JK"
        )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))

app.run_polling()
