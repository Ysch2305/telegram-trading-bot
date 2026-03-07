import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ========================
# PRICE COMMAND
# ========================

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /price BBCA.JK")
        return

    ticker = context.args[0]

    data = yf.Ticker(ticker)

    hist = data.history(period="1d")

    if hist.empty:
        await update.message.reply_text("Stock not found")
        return

    price = hist["Close"].iloc[-1]

    await update.message.reply_text(
        f"{ticker}\nPrice: {round(price,2)}"
    )

# ========================
# ANALYZE COMMAND
# ========================

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /analyze BBCA.JK")
        return

    ticker = context.args[0]

    data = yf.download(ticker, period="3mo")

    if data.empty:
        await update.message.reply_text("Stock data not found")
        return

    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()

    last = data.iloc[-1]

    trend = "SIDEWAYS"

    if last["MA20"] > last["MA50"]:
        trend = "BULLISH"
    elif last["MA20"] < last["MA50"]:
        trend = "BEARISH"

    text = f"""
Stock: {ticker}

Price: {round(last["Close"],2)}

MA20: {round(last["MA20"],2)}
MA50: {round(last["MA50"],2)}

Trend: {trend}
"""

    await update.message.reply_text(text)

# ========================
# RISK REWARD
# ========================

async def rr(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /rr entry stoploss target")
        return

    entry = float(context.args[0])
    sl = float(context.args[1])
    tp = float(context.args[2])

    risk = entry - sl
    reward = tp - entry

    ratio = round(reward / risk, 2)

    text = f"""
Entry: {entry}
Stoploss: {sl}
Target: {tp}

Risk: {risk}
Reward: {reward}

Risk Reward = 1:{ratio}
"""

    await update.message.reply_text(text)

# ========================
# START
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
Trading Assistant Bot

Commands:

/price BBCA.JK
/analyze BBCA.JK
/rr entry stoploss target
"""

    await update.message.reply_text(text)

# ========================
# MAIN
# ========================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("rr", rr))

print("BOT RUNNING...")

app.run_polling()
