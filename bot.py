import os
import yfinance as yf
import pandas as pd
import numpy as np

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# =========================
# STOCK LIST
# =========================

stocks = [
"BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK",
"ICBP.JK","INDF.JK","UNVR.JK","ADRO.JK","ANTM.JK",
"MDKA.JK","AMRT.JK","CPIN.JK","GOTO.JK","BRIS.JK",
"PGAS.JK","SMGR.JK","TOWR.JK"
]

# =========================
# RSI FUNCTION
# =========================

def calculate_rsi(data, period=14):

    delta = data["Close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100/(1+rs))

    return rsi

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
Trading Assistant Bot

Commands:

/price BBCA.JK
/analyze BBCA.JK
/scan
/rr entry stoploss target
"""

    await update.message.reply_text(text)

# =========================
# PRICE
# =========================

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):

    ticker = context.args[0]

    data = yf.Ticker(ticker)

    hist = data.history(period="1d")

    price = hist["Close"].iloc[-1]

    await update.message.reply_text(
        f"{ticker}\nPrice : {round(price,2)}"
    )

# =========================
# ANALYZE
# =========================

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):

    ticker = context.args[0]

    df = yf.download(ticker, period="3mo")

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()

    df["RSI"] = calculate_rsi(df)

    last = df.iloc[-1]

    trend = "SIDEWAYS"

    if last["MA20"] > last["MA50"]:
        trend = "BULLISH"

    if last["MA20"] < last["MA50"]:
        trend = "BEARISH"

    text = f"""
Stock : {ticker}

Price : {round(last["Close"],2)}

MA20 : {round(last["MA20"],2)}
MA50 : {round(last["MA50"],2)}

RSI : {round(last["RSI"],2)}

Trend : {trend}
"""

    await update.message.reply_text(text)

# =========================
# SCAN MARKET
# =========================

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    results = []

    for stock in stocks:

        try:

            df = yf.download(stock, period="3mo")

            if len(df) < 50:
                continue

            df["MA20"] = df["Close"].rolling(20).mean()
            df["MA50"] = df["Close"].rolling(50).mean()

            df["RSI"] = calculate_rsi(df)

            last = df.iloc[-1]

            volume_avg = df["Volume"].rolling(20).mean().iloc[-1]

            if (
                last["MA20"] > last["MA50"]
                and 50 < last["RSI"] < 70
                and last["Volume"] > volume_avg*1.5
            ):

                results.append(
                    f"{stock} | Price {round(last['Close'],2)} | RSI {round(last['RSI'],2)}"
                )

        except:
            continue

    if len(results) == 0:

        await update.message.reply_text("No strong stock found today")

    else:

        text = "TOP MOMENTUM STOCK\n\n"

        for r in results[:10]:

            text += r + "\n"

        await update.message.reply_text(text)

# =========================
# RISK REWARD
# =========================

async def rr(update: Update, context: ContextTypes.DEFAULT_TYPE):

    entry = float(context.args[0])
    sl = float(context.args[1])
    tp = float(context.args[2])

    risk = entry - sl
    reward = tp - entry

    ratio = round(reward/risk,2)

    text = f"""
Entry : {entry}
Stoploss : {sl}
Target : {tp}

Risk : {risk}
Reward : {reward}

Risk Reward = 1:{ratio}
"""

    await update.message.reply_text(text)

# =========================
# MAIN
# =========================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("scan", scan))
app.add_handler(CommandHandler("rr", rr))

print("BOT RUNNING...")

app.run_polling()
