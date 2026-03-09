def calculate_score(data):

    score = 0

    price = data['Close'].iloc[-1]

    ema20 = data['EMA20'].iloc[-1]
    ema50 = data['EMA50'].iloc[-1]
    ema200 = data['EMA200'].iloc[-1]

    rsi = data['RSI'].iloc[-1]

    macd = data['MACD'].iloc[-1]
    signal = data['SIGNAL'].iloc[-1]

    volume_spike = data['VOLUME_SPIKE'].iloc[-1]

    # EMA Trend
    if price > ema20 > ema50 > ema200:
        score += 2

    # RSI
    if rsi < 30:
        score += 1

    # MACD
    if macd > signal:
        score += 2

    # Volume
    if volume_spike:
        score += 1

    # Breakout
    high20 = data['High'].rolling(20).max().iloc[-1]

    if price > high20:
        score += 2

    return score
