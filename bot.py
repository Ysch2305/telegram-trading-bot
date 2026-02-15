import os
import yfinance as yf
import pandas as pd
import ta
import requests
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID_USER")  # opsional tapi bisa langsung kirim

watchlist = ["BUMI.JK","BBCA.JK","BUVA.JK","BBRI.JK","BMRI.JK","ANTM.JK"]

def send_msg(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id":chat_id, "text":text})

def analyze_symbol(sym, close_prices):
    # hitung EMA, RSI dst
    close = close_prices
    if len(close) < 20:
        return None
    
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # RSI manual contoh
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta).clip(lower=0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1+rs))
    
    signal = None
    if ema20 > ema50 and rsi.iloc[-1] > 55:
        signal = "BUY"
    elif ema20 < ema50 and rsi.iloc[-1] < 45:
        signal = "SELL"
    else:
        signal = "HOLD"
    return signal

def scan(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    msgs = []
    for sym in watchlist:
        df = yf.download(sym, period="1mo", interval="1d", auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        signal = analyze_symbol(sym, df["Close"])
        msgs.append(f"{sym.replace('.JK','')}: {signal}")
    send_msg(chat_id, "\n".join(msgs))

# telegram commands
def start(update: Update, context: CallbackContext):
    send_msg(update.effective_chat.id, "Bot siap! Gunakan /scan untuk analisis.")

def cmd_scan(update: Update, context: CallbackContext):
    scan(update, context)

updater = Updater(TOKEN)

updater.dispatcher.add_handler(CommandHandler("start", start))
updater.dispatcher.add_handler(CommandHandler("scan", cmd_scan))

updater.start_polling()
updater.idle()