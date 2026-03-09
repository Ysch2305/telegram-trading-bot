def calculate_score(data):
    """
    Menghitung skor trading berdasarkan beberapa indikator:
    EMA trend, RSI, MACD, Volume spike, dan Breakout
    """

    score = 0

    # Ambil data terakhir
    price = data['Close'].iloc[-1]

    ema20 = data['EMA20'].iloc[-1]
    ema50 = data['EMA50'].iloc[-1]
    ema200 = data['EMA200'].iloc[-1]

    rsi = data['RSI'].iloc[-1]

    macd = data['MACD'].iloc[-1]
    signal = data['SIGNAL'].iloc[-1]

    volume_spike = data['VOLUME_SPIKE'].iloc[-1]

    # ==========================
    # 1. Trend EMA
    # ==========================
    if price > ema20 > ema50 > ema200:
        score += 2

    elif price > ema50 > ema200:
        score += 1

    # ==========================
    # 2. RSI (Oversold)
    # ==========================
    if rsi < 30:
        score += 1

    elif rsi < 40:
        score += 0.5

    # ==========================
    # 3. MACD Momentum
    # ==========================
    if macd > signal:
        score += 2

    # ==========================
    # 4. Volume Spike
    # ==========================
    if volume_spike:
        score += 1

    # ==========================
    # 5. Breakout Resistance
    # ==========================
    high20 = data['High'].rolling(20).max().iloc[-1]

    if price > high20:
        score += 2

    return score


def generate_signal(score):
    """
    Mengubah score menjadi signal trading
    """

    if score >= 6:
        return "STRONG BUY"

    elif score >= 4:
        return "BUY"

    elif score >= 2:
        return "HOLD"

    else:
        return "SELL"


def calculate_risk_management(data):
    """
    Menghitung Stop Loss dan Take Profit sederhana
    """

    price = data['Close'].iloc[-1]

    # Stop loss 5%
    stop_loss = price * 0.95

    # Take profit 10%
    take_profit = price * 1.10

    return stop_loss, take_profit
