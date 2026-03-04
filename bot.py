import os
import telebot
import yfinance as yf
import pandas as pd
import numpy as np
from threading import Thread
from flask import Flask

# --- SERVER ---
app = Flask('')
@app.route('/')
def home(): return "TERMINAL WMI ONLINE"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- BOT ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

def get_institutional_analysis(ticker):
    ticker = ticker.upper()
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    
    if df.empty or len(df) < 50:
        return None
    
    # Hitung Manual EMA, RSI, ATR
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    
    # Ambil nilai terakhir dan sebelumnya dengan aman (.item() untuk menghindari Series error)
    curr_close = df['Close'].iloc[-1].item()
    curr_ema20 = df['EMA20'].iloc[-1].item()
    curr_ema50 = df['EMA50'].iloc[-1].item()
    curr_rsi = df['RSI'].iloc[-1].item()
    curr_atr = df['ATR'].iloc[-1].item()
    
    prev_ema20 = df['EMA20'].iloc[-2].item()
    prev_ema50 = df['EMA50'].iloc[-2].item()
    
    # Keputusan WMI (Menggunakan variabel tunggal, bukan Series)
    status = "WAIT / SIDEWAYS"
    if curr_ema20 > curr_ema50 and prev_ema20 <= prev_ema50:
        status = "🚀 BUY (GOLDEN CROSS)"
    elif curr_ema20 > curr_ema50 and curr_rsi < 60:
        status = "✅ BULLISH (HOLD)"
    elif curr_rsi > 75:
        status = "⚠️ TAKE PROFIT (OVERBOUGHT)"
    elif curr_ema20 < curr_ema50:
        status = "🔻 BEARISH (STAY OUT)"
        
    return {
        "price": curr_close,
        "rsi": curr_rsi,
        "status": status,
        "sl": curr_close - (2 * curr_atr)
    }

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🏦 *Sistem WMI Siap.*\nGunakan: `/cek BBCA.JK`", parse_mode="Markdown")

@bot.message_handler(commands=['cek'])
def check(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Masukkan kode saham. Contoh: `/cek TLKM.JK`", parse_mode="Markdown")
            return
            
        ticker = args[1].upper()
        if ".JK" not in ticker:
            bot.reply_to(message, "⚠️ Saham Indonesia wajib pakai `.JK`. Contoh: `ASII.JK`")
            return

        bot.send_message(message.chat.id, f"🔍 Menganalisa {ticker}...")
        res = get_institutional_analysis(ticker)
        
        if res:
            msg = (f"📊 *HASIL ANALISA: {ticker}*\n"
                   f"━━━━━━━━━━━━━━━━━━━\n"
                   f"💰 Harga: Rp{res['price']:,.0f}\n"
                   f"🚦 Sinyal: *{res['status']}*\n"
                   f"📈 RSI: {res['rsi']:.2f}\n"
                   f"🛡️ Stop Loss: Rp{res['sl']:,.0f}\n"
                   f"━━━━━━━━━━━━━━━━━━━")
            bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        else:
            bot.reply_to(message, f"❌ Data untuk {ticker} tidak cukup.")
            
    except Exception as e:
        bot.reply_to(message, f"🚨 Terjadi kesalahan sistem: `{str(e)}`", parse_mode="Markdown")

if __name__ == "__main__":
    Thread(target=run_server).start()
    bot.polling(non_stop=True)

