import io
import datetime
import requests
import pandas as pd
import yfinance as yf

def get_us_midcap_tickers():
    """Dynamically fetches all US listed stocks with market caps between $2B and $15B."""
    print("Fetching full US stock directory from NASDAQ...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    url = "https://old.nasdaq.com/screening/companies-by-name.aspx?letter=0&exchange=myall&render=download"
    
    try:
        # Fetch official exchange list (NASDAQ, NYSE, AMEX)
        resp = requests.get(url, headers=headers, timeout=10)
        df_tickers = pd.read_csv(io.StringIO(resp.text))
        
        # Filter by Market Cap ($2B to $15B)
        # Note: If exchange endpoint is unavailable, we fallback to a broader US stock index list
        df_tickers = df_tickers.dropna(subset=['MarketCap', 'Symbol'])
        df_tickers['MarketCap'] = pd.to_numeric(df_tickers['MarketCap'], errors='coerce')
        
        mid_cap_df = df_tickers[
            (df_tickers['MarketCap'] >= 2_000_000_000) & 
            (df_tickers['MarketCap'] <= 15_000_000_000)
        ]
        
        tickers = mid_cap_df['Symbol'].str.strip().tolist()
        # Clean ticker symbols for yfinance compatibility (e.g., BRK.B -> BRK-B)
        tickers = [t.replace('.', '-') for t in tickers if '^' not in t]
        print(f"Discovered {len(tickers)} mid-cap stocks ($2B - $15B).")
        return tickers
    except Exception as e:
        print(f"Notice: Dynamic NASDAQ fetch failed ({e}). Using S&P MidCap 400 list fallback.")
        # Fallback list: S&P MidCap 400 components via Wikipedia
        wiki_url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
        tables = pd.read_html(wiki_url)
        sp400_df = tables[0]
        tickers = sp400_df['Ticker symbol'].str.replace('.', '-', regex=False).tolist()
        return tickers

def calculate_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 90:
            return None
        
        info = stock.info
        market_cap = info.get("marketCap", 0)
        
        # Verify Market Cap target ($2B to $15B)
        if not (2e9 <= market_cap <= 15e9):
            return None
            
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
        
        # Breakout Score (0 to 3)
        score = (1 if near_breakout == "YES" else 0) + \
                (1 if vol_spike == "YES" else 0) + \
                (1 if higher_150d == "YES" else 0)
        
        # Master Sheet metrics
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
            "Market Cap ($B)": round(market_cap / 1e9, 2),
            "Industry": info.get("industry", "Other"),
            "P/E Ratio": round(info.get("trailingPE", 0), 2),
            "Beta": round(info.get("beta", 0), 2),
            "Last Updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception:
        return None

def main():
    tickers = get_us_midcap_tickers()
    records = []
    
    print(f"Processing calculations for {len(tickers)} mid-cap stocks...")
    for idx, ticker in enumerate(tickers):
        data = calculate_stock_data(ticker)
        if data:
            records.append(data)
        if (idx + 1) % 50 == 0:
            print(f"Processed {idx + 1}/{len(tickers)} tickers...")
            
    df = pd.DataFrame(records)
    df.to_parquet("latest_stocks.parquet")
    print(f"Data update complete! Saved {len(df)} mid-cap records to latest_stocks.parquet.")

if __name__ == "__main__":
    main()
