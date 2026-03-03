import os
import telebot
import yfinance as yf
import pandas as pd
import numpy as np
from threading import Thread
from flask import Flask

# --- INSTITUTIONAL HEALTH CHECK SERVER ---
app = Flask('')
@app.route('/')
def home(): return "WMI TRADING TERMINAL: ONLINE"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- BOT CONFIGURATION ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# --- CORE ANALYTICS ENGINE (PROPRIETARY FORMULA) ---
def get_institutional_analysis(ticker):
    # Mengambil data historis 1 tahun untuk akurasi tren
    df = yf.download(ticker, period="1y", interval="1d")
    if df.empty or len(df) < 50: return None
    
    # Perhitungan EMA (Exponential Moving Average) Manual
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # Perhitungan RSI (Relative Strength Index) Manual
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Perhitungan ATR (Average True Range) untuk Risk Management
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # DECISION LOGIC
    signal = "NEUTRAL / SIDEWAYS"
    action = "WAIT"
    
    # Sinyal Beli: Golden Cross + RSI < 65 (Belum Jenuh Beli)
    if curr['EMA20'] > curr['EMA50'] and prev['EMA20'] <= prev['EMA50']:
        signal = "🚀 STRONG BUY (GOLDEN CROSS)"
        action = "ENTRY"
    elif curr['EMA20'] > curr['EMA50'] and curr['RSI'] < 60:
        signal = "✅ BULLISH TREND (MAINTAIN)"
        action = "HOLD"
    elif curr['RSI'] > 75:
        signal = "⚠️ OVERBOUGHT (DANGER ZONE)"
        action = "TAKE PROFIT"
    elif curr['EMA20'] < curr['EMA50']:
        signal = "🔻 BEARISH TREND"
        action = "STAY OUT"

    return {
        "price": curr['Close'],
        "rsi": curr['RSI'],
        "signal": signal,
        "action": action,
        "sl": curr['Close'] - (2 * curr['ATR']) # Stop Loss Institusi
    }

# --- TELEGRAM HANDLERS ---
@bot.message_handler(commands=['start'])
def start_terminal(message):
    welcome = (
        "🏦 *WMI TRADING TERMINAL ACTIVE*\n"
        "Sistem siap mengeksekusi perintah analisis.\n\n"
        "Gunakan: `/cek [TICKER].JK`"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=['cek'])
def check_ticker(message):
    try:
        ticker = message.text.split()[1].upper()
        if not ticker.endswith('.JK'):
            bot.reply_to(message, "⚠️ Gunakan akhiran .JK (Contoh: BBRI.JK)")
            return

        bot.send_message(message.chat.id, f"🔍 Menganalisa data pasar untuk {ticker}...")
        res = get_institutional_analysis(ticker)
        
        if res:
            response = (
                f"📊 *ANALISIS EMITEN: {ticker}*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💰 *Harga Saat Ini:* Rp{res['price']:.0f}\n"
                f"📈 *RSI (Momentum):* {res['rsi']:.2f}\n"
                f"🚦 *Sinyal:* {res['signal']}\n"
                f"🎯 *Rekomendasi:* `{res['action']}`\n"
                f"🛡️ *Batas Risiko (SL):* Rp{res['sl']:.0f}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _Selalu gunakan manajemen risiko 2% modal._"
            )
            bot.send_message(message.chat.id, response, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Gagal menarik data. Pastikan ticker terdaftar di Bursa.")
    except Exception:
        bot.reply_to(message, "⚠️ Format salah. Contoh: `/cek BBCA.JK`")

if __name__ == "__main__":
    Thread(target=run_server).start()
    print("Sistem WMI Berjalan...")
    bot.polling(non_stop=True)
