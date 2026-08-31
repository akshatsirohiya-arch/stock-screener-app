import io
import re
import time
import datetime
import requests
import pandas as pd
import yfinance as yf

def clean_and_filter_tickers(raw_tickers):
    """Cleans raw ticker symbols while explicitly preserving foreign ADRs and common equities."""
    clean_tickers = []
    
    for t in raw_tickers:
        ticker = str(t).strip().upper()
        
        # 1. Exclude Warrants (-W, -WT), Units (-U, -UN), Rights (-R)
        if re.search(r'[-.](W|WT|U|UN|R|WS)$', ticker):
            continue
            
        # 2. Exclude Preferred Stock ($ or -PR or .PR)
        if '$' in ticker or '-PR' in ticker or '.PR' in ticker:
            continue
            
        # 3. Reformat Class Shares & ADRs for Yahoo Finance (e.g., BRK.B -> BRK-B)
        ticker = ticker.replace('.', '-')
        
        # Preserve standard tickers, dual classes, and international ADRs
        if ticker.replace('-', '').isalnum():
            clean_tickers.append(ticker)
            
    return list(set(clean_tickers))

def fetch_full_us_ticker_universe():
    """Combines SEC EDGAR + NASDAQ Trader Directory to fetch common stocks and ADRs."""
    tickers = set()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }

    # Source 1: SEC EDGAR Submissions Directory
    try:
        sec_url = "https://files.sec.gov/submissions/company_tickers.json"
        resp = requests.get(sec_url, headers={'User-Agent': 'StockScreenerApp admin@example.com'}, timeout=15)
        if resp.status_code == 200:
            df_sec = pd.DataFrame.from_dict(resp.json(), orient='index')
            tickers.update(df_sec['ticker'].tolist())
    except Exception as e:
        print(f"SEC EDGAR fetch notice: {e}")

    # Source 2: NASDAQ Trader Master Exchange Directory
    try:
        nasdaq_url = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqtraded.txt"
        resp = requests.get(nasdaq_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            df_nasdaq = pd.read_csv(io.StringIO(resp.text), sep='|')
            df_nasdaq = df_nasdaq[df_nasdaq['Test Issue'] == 'N']
            tickers.update(df_nasdaq['Symbol'].dropna().tolist())
    except Exception as e:
        print(f"NASDAQ directory fetch notice: {e}")

    valid_tickers = clean_and_filter_tickers(list(tickers))
    print(f"Master universe contains {len(valid_tickers)} clean equities & ADRs.")
    return valid_tickers

def process_batch(ticker_batch):
    """Fetches market metrics using fast_info fallback to prevent dropping ADRs and mid-caps."""
    records = []
    
    # Download 1 year of price data for the entire batch in a single call
    try:
        hist_df = yf.download(
            tickers=ticker_batch, 
            period="1y", 
            group_by="ticker", 
            auto_adjust=True, 
            progress=False, 
            threads=True
        )
    except Exception as e:
        print(f"Batch download error: {e}")
        return records

    for ticker_symbol in ticker_batch:
        try:
            # Extract ticker history dataframe
            if len(ticker_batch) == 1:
                hist = hist_df
            else:
                if ticker_symbol not in hist_df.columns.levels[0]:
                    continue
                hist = hist_df[ticker_symbol].dropna(how="all")

            if hist.empty or len(hist) < 90:
                continue

            stock_obj = yf.Ticker(ticker_symbol)
            
            # Robust Market Cap Retrieval (fast_info fallback -> info fallback)
            market_cap = 0
            try:
                market_cap = stock_obj.fast_info.get("marketCap", 0)
            except Exception:
                pass
                
            if not market_cap or market_cap == 0:
                try:
                    market_cap = stock_obj.info.get("marketCap", 0)
                except Exception:
                    pass

            # Extended Mid-Cap & ADR Range: $1B to $25B
            if not (1e9 <= market_cap <= 25e9):
                continue

            price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price

            # 90-Day High / Low Metrics
            last_90 = hist.tail(90)
            high_90 = last_90['High'].max()
            low_90 = last_90['Low'].min()
            range_pct = (high_90 - low_90) / low_90 if low_90 else 0
            dist_from_high = (high_90 - price) / high_90 if high_90 else 0

            # Breakout Conditions
            near_breakout = "YES" if dist_from_high <= 0.05 else "NO"
            tight_range = "YES" if range_pct <= 0.25 else "NO"  # Tight 90D spread <= 25%

            # Volume & Moving Average Metrics
            curr_vol = hist['Volume'].iloc[-1]
            avg_vol = hist['Volume'].tail(20).mean()
            vol_spike = "YES" if (avg_vol > 0 and curr_vol > 1.3 * avg_vol) else "NO"

            ma_150 = hist['Close'].tail(150).mean() if len(hist) >= 150 else price
            higher_150d = "YES" if price > ma_150 else "NO"

            # Composite Breakout Score (0 to 4 Points)
            score = (1 if near_breakout == "YES" else 0) + \
                    (1 if vol_spike == "YES" else 0) + \
                    (1 if higher_150d == "YES" else 0) + \
                    (1 if tight_range == "YES" else 0)

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
                "Tight Range": tight_range,
                "Volume Spike": vol_spike,
                "Higher than 150D": higher_150d,
                "90% of 52W High": is_90_pct_high,
                "90D High": round(high_90, 2),
                "90D Low": round(low_90, 2),
                "Dist from High (%)": round(dist_from_high * 100, 2),
                "Range %": round(range_pct * 100, 2),
                "Market Cap ($B)": round(market_cap / 1e9, 2),
                "Last Updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
            })
        except Exception:
            continue

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
            print(f"Scanned {min(i + batch_size, len(all_tickers))}/{len(all_tickers)} tickers | Identified Mid-Caps & ADRs: {len(all_midcap_records)}")

        time.sleep(0.2)

    df = pd.DataFrame(all_midcap_records)
    if not df.empty:
        df.to_parquet("latest_stocks.parquet")
        print(f"\n✅ SCAN COMPLETE: {len(df)} verified mid-caps & ADRs ($1B-$25B) saved to latest_stocks.parquet.")
    else:
        print("❌ Error: No valid mid-cap records found.")

if __name__ == "__main__":
    main()
