import io
import json
import time
import datetime
import requests
import pandas as pd
import yfinance as yf

def fetch_full_us_ticker_universe():
    """
    Fetches the complete directory of US-listed stock tickers directly from SEC EDGAR.
    Covers NYSE, NASDAQ, and AMEX without relying on static index subsets.
    """
    print("Fetching complete US stock directory from SEC EDGAR...")
    headers = {
        'User-Agent': 'StockScreenerApp user@example.com'  # SEC requires a user-agent header
    }
    sec_url = "https://files.sec.gov/submissions/company_tickers.json"
    
    try:
        resp = requests.get(sec_url, headers=headers, timeout=15)
        resp.raise_for_status()
        sec_data = resp.json()
        
        # Convert SEC JSON to DataFrame
        df_sec = pd.DataFrame.from_dict(sec_data, orient='index')
        
        # Extract tickers & clean for yfinance compatibility (replace '.' with '-')
        raw_tickers = df_sec['ticker'].astype(str).str.strip().tolist()
        clean_tickers = [
            t.replace('.', '-') for t in raw_tickers 
            if t.isalpha() or '-' in t or '.' in t
        ]
        
        # Remove common warrants/units/preferred share suffixes
        filtered_tickers = list(set([
            t for t in clean_tickers 
            if not any(t.endswith(suffix) for suffix in ['W', 'WS', 'U', 'R', 'P'])
        ]))
        
        print(f"Successfully retrieved {len(filtered_tickers)} total US listed entities.")
        return filtered_tickers
        
    except Exception as e:
        print(f"Primary SEC fetch failed: {e}. Falling back to NASDAQ directory...")
        nasdaq_url = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqtraded.txt"
        resp = requests.get(nasdaq_url, headers=headers, timeout=15)
        df_nasdaq = pd.read_csv(io.StringIO(resp.text), sep='|')
        df_nasdaq = df_nasdaq[df_nasdaq['Test Issue'] == 'N']
        tickers = df_nasdaq['Symbol'].astype(str).str.replace('.', '-', regex=False).tolist()
        return tickers

def process_batch(ticker_batch):
    """Fetches history and info for a batch of tickers and calculates technical metrics."""
    records = []
    
    # Download 1-year history in bulk for the batch to maximize performance
    try:
        tickers_str = " ".join(ticker_batch)
        data = yf.Tickers(tickers_str)
        
        for ticker_symbol in ticker_batch:
            try:
                stock_obj = data.tickers.get(ticker_symbol)
                if not stock_obj:
                    continue
                
                # Retrieve info & market cap
                info = stock_obj.info
                market_cap = info.get("marketCap", 0)
                
                # STRICT MID-CAP FILTER: $2 Billion to $15 Billion
                if not (2e9 <= market_cap <= 15e9):
                    continue
                
                # Price history check
                hist = stock_obj.history(period="1y")
                if hist.empty or len(hist) < 90:
                    continue
                
                price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price
                
                # 90-Day High / Low Metrics (Data Sheet)
                last_90 = hist.tail(90)
                high_90 = last_90['High'].max()
                low_90 = last_90['Low'].min()
                range_pct = (high_90 - low_90) / low_90 if low_90 else 0
                dist_from_high = (high_90 - price) / high_90 if high_90 else 0
                near_breakout = "YES" if dist_from_high <= 0.05 else "NO"
                
                # Volume & Moving Average Metrics
                curr_vol = hist['Volume'].iloc[-1]
                avg_vol = hist['Volume'].tail(20).mean()
                vol_spike = "YES" if (avg_vol > 0 and curr_vol > 1.3 * avg_vol) else "NO"
                
                ma_150 = hist['Close'].tail(150).mean() if len(hist) >= 150 else price
                higher_150d = "YES" if price > ma_150 else "NO"
                
                # Composite Breakout Score (0 to 3)
                score = (1 if near_breakout == "YES" else 0) + \
                        (1 if vol_spike == "YES" else 0) + \
                        (1 if higher_150d == "YES" else 0)
                
                # 52-Week High / Low & Master Sheet Metrics
                high_52 = hist['High'].max()
                is_90_pct_high = "Yes" if (high_52 and price >= 0.90 * high_52) else "No"
                day_return = (price - prev_close) / prev_close if prev_close else 0
                
                records.append({
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
                    "P/E Ratio": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else None,
                    "Beta": round(info.get("beta", 0), 2) if info.get("beta") else None,
                    "Last Updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
                })
            except Exception:
                continue
                
    except Exception as e:
        print(f"Error processing batch: {e}")
        
    return records

def main():
    all_tickers = fetch_full_us_ticker_universe()
    batch_size = 50
    all_midcap_records = []
    
    print(f"Starting universe scan across {len(all_tickers)} US securities in batches of {batch_size}...")
    
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
        records = process_batch(batch)
        all_midcap_records.extend(records)
        
        if (i // batch_size + 1) % 10 == 0 or (i + batch_size) >= len(all_tickers):
            print(f"Scanned {min(i + batch_size, len(all_tickers))}/{len(all_tickers)} tickers | Identified Mid-Caps ($2B-$15B): {len(all_midcap_records)}")
        
        # Friendly rate limiting for Yahoo Finance
        time.sleep(0.5)
        
    df = pd.DataFrame(all_midcap_records)
    if not df.empty:
        df.to_parquet("latest_stocks.parquet")
        print(f"\n✅ FULL SCAN COMPLETE: {len(df)} verified US Mid-Cap ($2B-$15B) stocks saved to latest_stocks.parquet.")
    else:
        print("❌ Error: No valid mid-cap records found.")

if __name__ == "__main__":
    main()
