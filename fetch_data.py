import datetime
import pandas as pd
import yfinance as yf

# Expand this list to include all your target stocks or index components
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC"]

def calculate_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="1y")
        if hist.empty:
            return None
        
        info = stock.info
        price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price
        
        # 90-Day calculations (Data Sheet)
        last_90 = hist.tail(90)
        high_90 = last_90['High'].max()
        low_90 = last_90['Low'].min()
        range_pct = (high_90 - low_90) / low_90 if low_90 else 0
        dist_from_high = (high_90 - price) / high_90 if high_90 else 0
        near_breakout = "YES" if dist_from_high <= 0.05 else "NO"
        
        # Volume & Moving Averages
        curr_vol = hist['Volume'].iloc[-1]
        avg_vol = hist['Volume'].tail(20).mean()
        vol_spike = "YES" if curr_vol > 1.3 * avg_vol else "NO"
        
        ma_150 = hist['Close'].tail(150).mean() if len(hist) >= 150 else price
        higher_150d = "YES" if price > ma_150 else "NO"
        
        # Composite Breakout Score
        score = (1 if near_breakout == "YES" else 0) + \
                (1 if vol_spike == "YES" else 0) + \
                (1 if higher_150d == "YES" else 0)
        
        # Master Sheet Metrics
        high_52 = hist['High'].max()
        is_90_pct_high = "Yes" if price >= 0.90 * high_52 else "No"
        day_return = (price - prev_close) / prev_close
        
        return {
            "Ticker": ticker_symbol,
            "Price": round(price, 2),
            "Day Return (%)": round(day_return * 100, 2),
            "Breakout Score": score,
            "Near Breakout": near_breakout,
            "Volume Spike": vol_spike,
            "Higher than 150D": higher_150d,
            "90% of 52W High": is_90_pct_high,
            "90D High": round(high_90, 2),
            "90D Low": round(low_90, 2),
            "Dist from High (%)": round(dist_from_high * 100, 2),
            "Range %": round(range_pct * 100, 2),
            "Market Cap ($B)": round(info.get("marketCap", 0) / 1e9, 2),
            "Industry": info.get("industry", "Other"),
            "P/E Ratio": round(info.get("trailingPE", 0), 2),
            "Beta": round(info.get("beta", 0), 2),
            "Last Updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception:
        return None

def main():
    records = []
    for ticker in TICKERS:
        data = calculate_stock_data(ticker)
        if data:
            records.append(data)
            
    df = pd.DataFrame(records)
    df.to_parquet("latest_stocks.parquet")
    print(f"Data updated successfully: {len(df)} records written.")

if __name__ == "__main__":
    main()
