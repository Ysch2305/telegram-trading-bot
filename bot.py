import os
import telebot
import yfinance as yf
import pandas as pd
import numpy as np
from threading import Thread
from flask import Flask

# --- WEB SERVER UNTUK RAILWAY ---
app = Flask('')
@app.route('/')
def home(): return "Sistem WMI Aktif"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- KONFIGURASI BOT ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# FUNGSI ANALISA (RUMUS MANUAL AGAR TIDAK ERROR)
def hitung_sinyal(ticker):
    df = yf.download(ticker, period="1y", interval="1d")
    if df.empty or len(df) < 50: return None
    
    # Indikator EMA
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # Indikator RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    # Indikator ATR
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    
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

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🏦 *WMI Trading System Active*\n\nKetik `/cek BBCA.JK` untuk analisa saham.")

@bot.message_handler(commands=['cek'])
def check_stock(message):
    try:
        ticker = message.text.split()[1].upper()
        bot.send_message(message.chat.id, f"🔍 Menganalisa {ticker}...")
        res = hitung_sinyal(ticker)
        
        if res:
            msg = (f"📊 *Analisis {ticker}*\n"
                   f"--------------------------\n"
                   f"💰 Harga: Rp{res['price']:.0f}\n"
                   f"🚦 Sinyal: *{res['status']}*\n"
                   f"🛡️ Stop Loss: Rp{res['sl']:.0f}")
            bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        else:
            bot.reply_to(message, "Data tidak ditemukan. Pastikan ticker benar (contoh: ASII.JK)")
    except:
        bot.reply_to(message, "Format salah. Contoh: `/cek TLKM.JK`")

if __name__ == "__main__":
    Thread(target=run).start()
    print("Bot WMI berjalan...")
    bot.polling(non_stop=True)
