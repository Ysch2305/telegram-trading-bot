import telegram
from telegram.ext import Updater, CommandHandler

from scanner import analyze_stock
from config import TELEGRAM_TOKEN, WATCHLIST


bot = telegram.Bot(token=TELEGRAM_TOKEN)


def start(update, context):

    update.message.reply_text(
        "Trading Bot Aktif\n\n"
        "/scan - scan market\n"
        "/analyze BBCA.JK - analisa saham"
    )


def scan(update, context):

    results = []

    for stock in WATCHLIST:

        result = analyze_stock(stock)

        results.append(result)

    message = "Top Signals\n\n"

    for r in results:

        message += f"{r['symbol']}\n"
        message += f"Price: {r['price']}\n"
        message += f"Score: {r['score']}\n"
        message += f"Signal: {r['signal']}\n\n"

    update.message.reply_text(message)


def analyze(update, context):

    symbol = context.args[0]

    result = analyze_stock(symbol)

    message = f"""
Stock: {result['symbol']}

Price: {result['price']}

RSI: {result['rsi']:.2f}

Score: {result['score']}

Signal: {result['signal']}
"""

    update.message.reply_text(message)


def main():

    updater = Updater(TELEGRAM_TOKEN)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("analyze", analyze))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
