import os
import telebot
import yfinance as yf
import pandas_ta as ta
from threading import Thread
from flask import Flask

# --- FLASK SERVER (Agar Railway tidak mematikan bot) ---
app = Flask('')

@app.route('/')
def home():
    return "WMI Bot is Alive!"

def run():
    # Railway menggunakan port yang dinamis, kita harus menangkapnya
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- LOGIKA BOT TELEGRAM ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)

# ... (Gunakan fungsi hitung_sinyal dan handler cek dari kode sebelumnya) ...

@bot.message_handler(commands=['cek'])
def check_stock(message):
    # (Sama seperti kode sebelumnya)
    pass

if __name__ == "__main__":
    # Jalankan Flask di thread terpisah
    t = Thread(target=run)
    t.start()
    
    print("Bot WMI sedang berjalan...")
    bot.polling(non_stop=True) # non_stop=True agar bot tidak mudah mati jika koneksi drop
