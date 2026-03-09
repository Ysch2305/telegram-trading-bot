import pandas as pd

def ema(data, period):
    return data.ewm(span=period, adjust=False).mean()


def rsi(data, period=14):
    delta = data.diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def macd(data):

    ema12 = ema(data, 12)
    ema26 = ema(data, 26)

    macd_line = ema12 - ema26
    signal = ema(macd_line, 9)

    histogram = macd_line - signal

    return macd_line, signal, histogram


def volume_spike(volume):

    avg_volume = volume.rolling(20).mean()

    return volume > (avg_volume * 1.5)
