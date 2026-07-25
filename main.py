import pandas as pd
import numpy as np
from binance.client import Client

# Միացում Binance-ի հանրային API-ին
client = Client()

def get_binance_data(symbol="BTCUSDT", interval="1m", limit=100):
    """Ներբեռնում է մոմերի պատմությունը Binance-ից"""
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_vol', 'taker_buy_quote_vol', 'ignore'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def resample_data(df, timeframe):
    """
    Վերափոխում է տվյալները՝ ըստ օգտատེრის ընտրած կարճ (5s, 10s) 
    կամ երկար (1m, 1h) ժամանակահատվածի
    """
    if timeframe in ["5s", "10s"]:
        # Քանի որ բորսաները չունեն 5վ/10վ ֆիքսված մոմեր, մենք մոտարկում ենք 1րոպեանոցից
        rule = "5s" if timeframe == "5s" else "10s"
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)
        
        resampled = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna().reset_index()
        return resampled
    else:
        # Ստանդարտ թայմֆրեյմների համար (օրինակ՝ 1m, 1h)
        return df

def calculate_supertrend(df, period=10, multiplier=3):
    """Հաշվարկում է Supertrend ինդիկատորը"""
    hl2 = (df['high'] + df['low']) / 2
    atr = df['high'].rolling(period).mean() - df['low'].rolling(period).mean()
    lower_basic = hl2 - (multiplier * atr)
    df['supertrend'] = np.where(df['close'] > lower_basic, 1, -1)
    return df['supertrend'].iloc[-1]

def calculate_rsi(df, period=14):
    """Հաշվարկում է RSI ինդիկատորը"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    # Եթե տվյալները շատ քիչ են (օրինակ՝ նոր գեներացված վայրկյանների համար), վերադարձնում ենք չեզոք արժեք
    return rsi.iloc[-1] if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50.0

def calculate_macd(df):
    """Հաշվարկում է MACD ինդիկատորը"""
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

def calculate_bollinger_bands(df, period=20):
    """Հաշվարկում է Bollinger Bands շերտերը"""
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = sma + (std * 2)
    lower_band = sma - (std * 2)
    return upper_band.iloc[-1], lower_band.iloc[-1], df['close'].iloc[-1]

def check_smc_order_block(df):
    """Smart Money Concepts (SMC) հիմնական ստուգում"""
    if len(df) < 10:
        return 1
    body_size = abs(df['close'].iloc[-2] - df['open'].iloc[-2])
    avg_body = abs(df['close'] - df['open']).rolling(10).mean().iloc[-2]
    is_order_block = body_size > (avg_body * 1.5) if not pd.isna(avg_body) else False
    direction = 1 if df['close'].iloc[-2] > df['open'].iloc[-2] else -1
    return direction if is_order_block else 0

def analyze_next_candle(symbol="BTCUSDT", timeframe="1m"):
    """
    Հիմնական ֆունկցիա. ստանում է տվյալներ, կարգավորում ըստ ընտրված թայմֆրեյմի 
    (5s, 10s, 1m, 1h) և տալիս խիստ ազդանշան բոլոր 5 ինդիկատորների համադրությամբ
    """
    # Որոշում ենք հիմնական բազային թայմֆրեյմը ըստ օգտատེრის պահանջի
    binance_interval = "1m"
    if timeframe == "1h":
        binance_interval = "1h"
    
    # Քաշում ենք տվյալները բորսայից
    raw_df = get_binance_data(symbol=symbol, interval=binance_interval, limit=100)
    
    # Եթե ընտրված է վայրկյանային թայմֆրեյմ, վերամշակում ենք
    df = resample_data(raw_df, timeframe)
    
    # Ստուգում ենք, որ բավարար մոմեր կան հաշվարկների համար
    if len(df) < 20:
        return "⏳ Տվյալները հավաքագրման փուլում են, փորձեք մի փոքր ուշ..."

    # Հաշվարկում ենք 5 ինդիկատորների ազդանշանները
    st_signal = calculate_supertrend(df)
    
    rsi_val = calculate_rsi(df)
    rsi_signal = 1 if rsi_val > 50 else -1
    
    macd_val, signal_val = calculate_macd(df)
    macd_signal = 1 if macd_val > signal_val else -1
    
    upper, lower, current_close = calculate_bollinger_bands(df)
    bb_signal = 1 if current_close > (upper + lower) / 2 else -1
    
    smc_signal = check_smc_order_block(df)
    if smc_signal == 0:
        smc_signal = st_signal
        
    # ԽԻՍՏ ՀԱՄԱՁԱՅՆՈՒԹՅԱՆ ՍՏՈՒԳՈՒՄ (Բոլոր 5-ը պետք է լինեն միևնույն ուղղությամբ)
    signals = [st_signal, rsi_signal, macd_signal, bb_signal, smc_signal]
    
    print(f"[{symbol} - {timeframe}] RSI: {rsi_val:.2f}, MACD: {macd_val:.4f}")
    
    if all(s == 1 for s in signals):
        return f"🟢 ԳՆԵԼ ({timeframe}) - Հաջորդ մոմը կլինի ԿԱՆԱՉ 📈"
    elif all(s == -1 for s in signals):
        return f"🔴 ՎԱՃԱՌԵԼ ({timeframe}) - Հաջորդ մոմը կլինի ԿԱՐՄԻՐ 📉"
    else:
        return f"⏳ ՍՊԱՍԵԼ ({timeframe}) - Ինդիկատորների անհամաձայնություն (Չեզոք)"

# Օրինակ՝ ստուգելու համար 5 վայրկյանանոց կամ 1 ժամանոց ազդանշանը
if __name__ == "__main__":
    print(analyze_next_candle("BTCUSDT", "5s"))
    print(analyze_next_candle("BTCUSDT", "1h"))
