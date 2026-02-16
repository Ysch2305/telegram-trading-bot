import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging

# 1. Setup Logging agar bisa memantau aktivitas bot di Railway Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# 2. Ambil Token dari environment variable Railway
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# 3. Daftar saham awal (Watchlist Default)
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    """Menganalisis tren, tenaga beli, dan mengambil harga terakhir."""
    if len(df) < 50:
        return "DATA KURANG", 0, "Butuh data lebih banyak untuk analisis."
    
    # Mengambil harga terakhir (Real-time saat bursa buka, atau Close terakhir jika tutup)
    current_price = df["Close"].iloc[-1]
    
    close = df["Close"]
    # Indikator Tren: EMA 20 dan EMA 50
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # Indikator Tenaga Beli: RSI 14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Logika Penentuan Sinyal dan Penjelasan Deskriptif
    if ema20 > ema50 and rsi > 55:
        status = "BUY 🟢"
        reason = "Tren menguat (Bullish) & tenaga beli sangat besar."
    elif ema20 < ema50 and rsi < 45:
        status = "SELL 🔴"
        reason = "Tren melemah (Bearish) & harga cenderung turun."
    else:
        # Penjelasan tambahan untuk kondisi bimbang (Hold)
        if ema20 > ema50:
            status = "HOLD 🟡"
            reason = "Tren naik tapi tenaga beli mulai jenuh/lemah."
        else:
            status = "HOLD 🟡"
            reason = "Pasar sedang bimbang atau bergerak menyamping (Sideways)."
            
    return status, current_price, reason

def start(update: Update, context: CallbackContext):
    """Pesan sambutan saat user mengetik /start."""
    update.message.reply_text(
        "👋 <b>Bot SwingWatchBit Aktif!</b>\n\n"
        "Anda bisa mematikan laptop dan bot akan tetap bekerja.\n\n"
        "<b>Perintah:</b>\n"
        "/scan - Cek harga & sinyal saham (Real-time)\n"
        "/add [KODE] - Tambah saham (contoh: /add ASII.JK)\n"
        "/list - Lihat daftar saham yang dipantau",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    """Mengambil data pasar dan mengirimkan hasil analisis ke user."""
    update.message.reply_text("🔎 Sedang mengambil data real-time, mohon tunggu...")
    results = []
    
    for sym in watchlist:
        try:
            # Download data 3 bulan terakhir (Daily)
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            
            if df.empty:
                continue
            
            # Membersihkan format data MultiIndex jika ada
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            status, last_price, reason = analyze_symbol(sym, df)
            clean_sym = sym.replace('.JK','')
            
            # Format pesan: Nama Saham | Harga | Sinyal | Alasan
            results.append(
                f"<b>{clean_sym}</b> | Rp{last_price:,.0f}\n"
                f"Sinyal: {status}\n"
                f"└ <i>{reason}</i>"
            )
        except Exception as e:
            logging.error(f"Error pada {sym}: {e}")
            results.append(f"❌ {sym}: Gagal dianalisis.")

    if results:
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')
    else:
        update.message.reply_text("Watchlist kosong. Gunakan /add untuk menambah saham.")

def add_stock(update: Update, context: CallbackContext):
    """Menambah saham baru ke dalam daftar sementara."""
    if not context.args:
        update.message.reply_text("Gunakan format: /add KODE.JK\nContoh: /add TLKM.JK")
        return
    
    code = context.args[0].upper()
    if ".JK" not in code:
        code += ".JK"
    
    if code not in watchlist:
        watchlist.append(code)
        update.message.reply_text(f"✅ <b>{code}</b> berhasil ditambahkan!")
    else:
        update.message.reply_text(f"ℹ️ {code} sudah ada di daftar.")

def list_watchlist(update: Update, context: CallbackContext):
    """Menampilkan semua saham yang ada di watchlist saat ini."""
    msg = "📋 <b>Daftar Pantauan Anda:</b>\n\n" + "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    if not TOKEN:
        print("ERROR: Variabel TELEGRAM_BOT_TOKEN tidak ditemukan!")
    else:
        updater = Updater(TOKEN)
        dp = updater.dispatcher

        # Mendaftarkan semua perintah (Handlers)
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("scan", scan))
        dp.add_handler(CommandHandler("add", add_stock))
        dp.add_handler(CommandHandler("list", list_watchlist))

        print("Bot Berjalan di Railway...")
        # drop_pending_updates=True untuk mencegah bot 'balas dendam' chat lama saat baru nyala
        updater.start_polling(drop_pending_updates=True)
        updater.idle()
