import os
import telebot
import yfinance as yf
import pandas as pd
import numpy as np
from threading import Thread
from flask import Flask

# --- SERVER UNTUK RAILWAY ---
app = Flask('')
@app.route('/')
def home(): return "Sistem WMI Aktif Tanpa Library Eksternal"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- LOGIKA BOT ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

def hitung_sinyal_manual(ticker):
    df = yf.download(ticker, period="1y", interval="1d")
    if df.empty or len(df) < 50: return None
    
    # RUMUS MANUAL (Pengganti pandas_ta)
    # EMA
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    status = "WAIT"
    if curr['EMA20'] > curr['EMA50'] and prev['EMA20'] <= prev['EMA50']:
        status = "🚀 BUY (GOLDEN CROSS)"
    elif curr['EMA20'] > curr['EMA50'] and curr['RSI'] < 60:
        status = "✅ HOLD"
    elif curr['RSI'] > 75:
        status = "⚠️ TAKE PROFIT"
        
    return {
        "price": curr['Close'],
        "status": status,
        "sl": curr['Close'] - (2 * curr['ATR'])
    }

@bot.message_handler(commands=['cek'])
def check_stock(message):
    try:
        ticker = message.text.split()[1].upper()
        res = hitung_sinyal_manual(ticker)
        if res is None:
            bot.reply_to(message, "Data tidak cukup atau ticker salah.")
            return
            
        msg = (f"📊 *Analisis {ticker}*\n"
               f"Harga: Rp{res['price']:.0f}\n"
               f"Status: *{res['status']}*\n"
               f"Stop Loss: Rp{res['sl']:.0f}")
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Gunakan format: /cek BBCA.JK")

if __name__ == "__main__":
    Thread(target=run).start()
    bot.polling(non_stop=True)

