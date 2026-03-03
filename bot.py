import os
import telebot
import yfinance as yf
import pandas_ta as ta

# Mengambil token dari Environment Variable Railway
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)

def hitung_sinyal(ticker):
    # Ambil data 1 tahun terakhir
    df = yf.download(ticker, period="1y", interval="1d")
    if df.empty: return None
    
    # Indikator teknikal (Standar Institusi)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Logika Keputusan WMI
    status = "WAIT"
    detail = "Trend belum terkonfirmasi."
    
    if curr['EMA20'] > curr['EMA50'] and prev['EMA20'] <= prev['EMA50']:
        status = "🚀 BUY (Golden Cross)"
        detail = "EMA20 memotong EMA50 ke atas. Awal trend naik."
    elif curr['EMA20'] > curr['EMA50'] and curr['RSI'] < 65:
        status = "✅ HOLD / ACCUMULATE"
        detail = "Trend naik sehat, RSI belum jenuh beli."
    elif curr['RSI'] > 75:
        status = "⚠️ TAKE PROFIT"
        detail = "Harga sudah terlalu tinggi (Overbought)."

    return {
        "price": curr['Close'],
        "status": status,
        "detail": detail,
        "sl": curr['Close'] - (2 * curr['ATR']) # Stop Loss berbasis volatilitas
    }

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🏦 *WMI Terminal Active*\nKetik `/cek [KODE SAHAM].JK` untuk analisa.")

@bot.message_handler(commands=['cek'])
def check_stock(message):
    try:
        ticker = message.text.split()[1].upper()
        bot.send_message(message.chat.id, f"🔍 Menganalisa {ticker}...")
        
        res = hitung_sinyal(ticker)
        msg = (f"📊 *Hasil Analisa: {ticker}*\n"
               f"--------------------------\n"
               f"💰 Harga: Rp{res['price']:.0f}\n"
               f"🚦 Sinyal: *{res['status']}*\n"
               f"📝 Alasan: {res['detail']}\n"
               f"🛡️ Stop Loss: Rp{res['sl']:.0f}")
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Gagal. Contoh: `/cek BBCA.JK` atau `/cek TLKM.JK`")

print("Bot WMI sedang berjalan...")
bot.polling()
