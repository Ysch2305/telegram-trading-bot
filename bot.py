import telegram
from telegram.ext import Updater, CommandHandler
from scanner import scan_market

TOKEN = "ISI_TOKEN_BOT_ANDA"

bot = telegram.Bot(token=TOKEN)

def start(update, context):

    text = """
AI Trading Scanner

Perintah:

/scan  → scan peluang saham
/top → ranking saham terbaik
"""

    update.message.reply_text(text)


def scan(update, context):

    update.message.reply_text("Scanning market...")

    data = scan_market()

    if len(data) == 0:
        update.message.reply_text("Tidak ada peluang hari ini")
        return

    message = "Peluang Saham Hari Ini\n\n"

    for r in data[:10]:

        message += f"""
{r['symbol']}
Price : {r['price']}
Score : {r['score']}
Breakout : {r['breakout']}
Volume Spike : {r['volume_spike']}

"""

    update.message.reply_text(message)


def top(update, context):

    data = scan_market()

    message = "Top Saham Hari Ini\n\n"

    for i,r in enumerate(data[:10]):

        message += f"{i+1}. {r['symbol']} | Score {r['score']}\n"

    update.message.reply_text(message)


updater = Updater(TOKEN, use_context=True)

dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("scan", scan))
dp.add_handler(CommandHandler("top", top))

updater.start_polling()

updater.idle()
