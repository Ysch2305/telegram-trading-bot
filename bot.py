import os
import telebot
import yfinance as yf
import pandas_ta as ta
from threading import Thread
from flask import Flask

# --- FLASK SERVER ---
app = Flask('')
@app.route('/')
def home(): return "WMI Bot is Alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- BOT LOGIC ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)

def hitung_sinyal(ticker):
    df = yf.download(ticker, period="1y", interval="1d")
    if df.empty: return None
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    status = "WAIT"
    detail = "Trend belum terkonfirmasi."
    if curr['EMA20'] > curr['EMA50'] and prev['EMA20'] <= prev['EMA50']:
        status = "🚀 BUY (Golden Cross)"
        detail = "Awal trend naik."
    elif curr['EMA20'] > curr['EMA50'] and curr['RSI'] < 65:
        status = "✅ HOLD"
        detail = "Trend naik sehat."
    elif curr['RSI'] > 75:
        status = "⚠️ TP"
        detail = "Sudah jenuh beli."

    return {"price": curr['Close'], "status": status, "detail": detail, "sl": curr['Close'] - (2 * curr['ATR'])}

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🏦 WMI Terminal Active. Ketik `/cek BBCA.JK`")

@bot.message_handler(commands=['cek'])
def check_stock(message):
    try:
        ticker = message.text.split()[1].upper()
        res = hitung_sinyal(ticker)
        msg = f"📊 *{ticker}*\nPrice: {res['price']:.0f}\nSignal: {res['status']}\nSL: {res['sl']:.0f}"
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "Gunakan format: /cek BBCA.JK")

if __name__ == "__main__":
    Thread(target=run).start()
    bot.polling(non_stop=True)
