import logging
from telegram.ext import Updater, CommandHandler

from scanner import analyze_stock
from config import TELEGRAM_TOKEN, WATCHLIST


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def start(update, context):
    message = (
        "Trading Bot Aktif\n\n"
        "Commands:\n"
        "/scan - Scan watchlist saham\n"
        "/analyze KODE - Analisa satu saham\n\n"
        "Contoh:\n"
        "/analyze BBCA.JK"
    )

    update.message.reply_text(message)


def scan(update, context):

    update.message.reply_text("Scanning market...")

    results = []

    for stock in WATCHLIST:

        try:
            result = analyze_stock(stock)
            results.append(result)

        except Exception as e:

            results.append({
                "symbol": stock,
                "price": 0,
                "score": 0,
                "signal": "ERROR",
                "rsi": 0
            })

    message = "Top Signals\n\n"

    for r in results:

        message += (
            f"{r['symbol']}\n"
            f"Price: {r['price']}\n"
            f"Score: {r['score']}\n"
            f"Signal: {r['signal']}\n\n"
        )

    update.message.reply_text(message)


def analyze(update, context):

    if len(context.args) == 0:
        update.message.reply_text(
            "Gunakan format:\n"
            "/analyze BBCA.JK"
        )
        return

    symbol = context.args[0]

    update.message.reply_text(f"Menganalisa {symbol}...")

    try:

        result = analyze_stock(symbol)

        message = (
            f"Stock: {result['symbol']}\n\n"
            f"Price: {result['price']}\n"
            f"RSI: {result['rsi']}\n"
            f"Score: {result['score']}\n"
            f"Signal: {result['signal']}"
        )

        update.message.reply_text(message)

    except Exception as e:

        update.message.reply_text(
            "Terjadi error saat analisa saham."
        )


def test(update, context):
    update.message.reply_text("BOT WORKING")


def main():

    updater = Updater(TELEGRAM_TOKEN)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("analyze", analyze))
    dp.add_handler(CommandHandler("test", test))

    print("Bot started...")

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
