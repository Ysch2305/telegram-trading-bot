import os
import telebot
import yfinance as yf
import pandas_ta as ta
import pandas as pd

# Konfigurasi Environment (Input di Railway Settings)
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Database sederhana (Dalam praktek nyata gunakan PostgreSQL di Railway)
portfolio = {} 
MODAL_USER = 100000000 # Contoh: 100 Juta

def get_signal(ticker):
    df = yf.download(ticker, period="1y", interval="1d")
    if df.empty: return None
    
    # Indikator Standar Institusi
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Logika WMI: Buy hanya jika Golden Cross & RSI belum jenuh
    signal = "WAIT"
    reason = "Market tidak memberikan konfirmasi tren."
    
    if curr['EMA20'] > curr['EMA50'] and prev['EMA20'] <= prev['EMA50']:
        signal = "STRONG BUY"
        reason = "Terjadi Golden Cross EMA20/50. Awal siklus Bullish."
    elif curr['EMA20'] > curr['EMA50'] and curr['RSI'] < 60:
        signal = "HOLD / ADD UP"
        reason = "Tren naik terjaga, RSI masih memiliki ruang kenaikan."
    elif curr['RSI'] > 75:
        signal = "TAKE PROFIT"
        reason = "Harga sudah jenuh beli (Overbought), risiko koreksi besar."
        
    return {
        "price": curr['Close'],
        "signal": signal,
        "reason": reason,
        "atr": curr['ATR']
    }

@bot.message_id_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🏦 *WMI Trading System Active*\nGunakan `/analisa BBCA.JK` untuk mulai.")

@bot.message_handler(commands=['analisa'])
def analyze(message):
    try:
        ticker = message.text.split()[1].upper()
        data = get_signal(ticker)
        
        # Risk Management (SL = 2x ATR di bawah harga beli)
        stop_loss = data['price'] - (2 * data['atr'])
        
        response = (
            f"📊 *Analisis Saham: {ticker}*\n"
            f"----------------------------\n"
            f"💰 Harga Saat Ini: Rp{data['price']:.0f}\n"
            f"🚦 Sinyal: *{data['signal']}*\n"
            f"📝 Alasan: {data['reason']}\n\n"
            f"🛡️ *Risk Management:*\n"
            f"Stop Loss: Rp{stop_loss:.0f}\n"
            f"Max Buy: {int((MODAL_USER*0.1)/data['price'])} Lot (10% Modal)"
        )
        bot.send_message(message.chat.id, response, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "Format salah. Gunakan: `/analisa [TICKER].JK`")

bot.polling()
