import yfinance as yf
import pandas as pd


def get_stock_data(symbol):

    try:

        ticker = yf.Ticker(symbol)

        data = ticker.history(
            period="6mo",
            interval="1d",
            auto_adjust=False
        )

        if data is None or len(data) == 0:
            print(f"No data returned for {symbol}")
            return None

        # Pastikan kolom yang diperlukan ada
        required_columns = ["Open", "High", "Low", "Close", "Volume"]

        for col in required_columns:
            if col not in data.columns:
                print(f"Missing column {col} for {symbol}")
                return None

        data = data.dropna()

        return data

    except Exception as e:

        print(f"ERROR fetching {symbol}: {e}")

        return None
