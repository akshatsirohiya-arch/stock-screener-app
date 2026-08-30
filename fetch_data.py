import io
import re
import time
import datetime
import requests
import pandas as pd
import yfinance as yf

def clean_and_filter_tickers(raw_tickers):
    """Cleans ticker symbols and keeps common stocks & foreign ADRs while dropping derivatives/preferreds."""
    clean_tickers = []
    
    for t in raw_tickers:
        ticker = str(t).strip().upper()
        
        # 1. Skip Warrants (-W, -WT), Units (-U, -UN), Rights (-R)
        if re.search(r'[-.](W|WT|U|UN|R|WS)$', ticker):
            continue
            
        # 2. Skip Preferred Shares ($ or -PR or .PR)
        if '$' in ticker or '-PR' in ticker or '.PR' in ticker:
            continue
            
        # 3. Format Class Shares & ADRs for Yahoo Finance (e.g., BRK.B -> BRK-B)
        ticker = ticker.replace('.', '-')
        
        # Keep valid alphanumeric tickers (includes standard stocks, dual classes & foreign ADRs)
        if ticker.replace('-', '').isalnum():
            clean_tickers.append(ticker)
            
    return list(set(clean_tickers))

def fetch_full_us_ticker_universe():
    """Fetches full US stock directory directly from SEC EDGAR."""
    print("Fetching complete US stock directory from SEC EDGAR...")
    headers = {
        'User-Agent': 'StockScreenerApp admin@example.com'
    }
    sec_url = "https://files.sec.gov/submissions/company_tickers.json"
    
    try:
        resp = requests.get(sec_url, headers=headers, timeout=15)
        resp.raise_for_status()
        sec_data = resp.json()
        
        df_sec = pd.DataFrame.from_dict(sec_data, orient='index')
        raw_tickers = df_sec['ticker'].tolist()
        
        valid_tickers = clean_and_filter_tickers(raw_tickers)
        print(f"Retrieved {len(valid_tickers)} clean tickers for universe screening.")
        return valid_tickers
        
    except Exception as e:
        print(f"Primary SEC fetch failed ({e}). Falling back to default list...")
        return ["TWLO", "ILMN", "FTI", "ATI", "OKTA", "NVT", "CRS", "ENTG", "RGLD", "WWD", "ROKU"]

def process_batch(ticker_batch):
    """Fetches data and screens for Extended Mid-Caps and ADRs ($1B - $25B)."""
    records = []
    tickers_str = " ".join(ticker_batch)
    
    try:
        data = yf.Tickers(tickers_str)
        
        for ticker_symbol in ticker_batch:
            try:
                stock_obj = data.tickers.get(ticker_symbol)
                if not stock_obj:
                    continue
                
                info = stock_obj.info
                market_cap = info.get("marketCap", 0)
                
                # EXTENDED MID-CAP & ADR FILTER: $1 Billion to $25 Billion
                if not (1e9 <= market_cap <= 25e9):
                    continue
                
                # Fetch 1-year history
                hist = stock_obj.history(period="1y")
                if hist.empty or len(hist) < 90:
                    continue
                
                price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price
                
                # 90-Day High / Low Metrics
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
                
                # Breakout Composite Score (0 to 3)
                score = (1 if near_breakout == "YES" else 0) + \
                        (1 if vol_spike == "YES" else 0) + \
                        (1 if higher_150d == "YES" else 0)
                
                # 52-Week High & Day Return
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
        print(f"Batch processing error: {e}")
        
    return records

def main():
    all_tickers = fetch_full_us_ticker_universe()
    batch_size = 50
    all_midcap_records = []
    
    print(f"Scanning market universe across {len(all_tickers)} tickers for Extended Mid-Caps & ADRs ($1B-$25B)...")
    
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
        records = process_batch(batch)
        all_midcap_records.extend(records)
        
        if (i // batch_size + 1) % 10 == 0 or (i + batch_size) >= len(all_tickers):
            print(f"Scanned {min(i + batch_size, len(all_tickers))}/{len(all_tickers)} tickers | Verified Mid-Caps/ADRs: {len(all_midcap_records)}")
        
        time.sleep(0.5)
        
    df = pd.DataFrame(all_midcap_records)
    if not df.empty:
        df.to_parquet("latest_stocks.parquet")
        print(f"\n✅ EXTENDED SCAN COMPLETE: {len(df)} verified mid-cap & ADR stocks ($1B-$25B) saved to latest_stocks.parquet.")
    else:
        print("❌ Error: No valid mid-cap records found.")

if __name__ == "__main__":
    main()
