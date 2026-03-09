import yfinance as yf
import pandas as pd


def get_stock_data(symbol):

    try:

        data = yf.download(
            symbol,
            period="6mo",
            interval="1d",
            progress=False
        )

        if data is None or data.empty:
            return None

        # pastikan kolom yang diperlukan ada
        required_columns = ["Open", "High", "Low", "Close", "Volume"]

        for col in required_columns:
            if col not in data.columns:
                return None

        data = data.dropna()

        return data

    except Exception as e:

        print(f"ERROR fetching {symbol}: {e}")

        return None
