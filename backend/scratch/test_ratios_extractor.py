import yfinance as yf
import json

def test_ticker(symbol):
    t = yf.Ticker(symbol)
    info = t.info or {}
    inc = t.income_stmt
    
    roe = info.get("returnOnEquity")
    net_margin = info.get("profitMargins")
    gross_margin = info.get("grossMargins")
    operating_margin = info.get("operatingMargins")
    rev_growth = info.get("revenueGrowth")
    earnings_growth = info.get("earningsGrowth")
    
    print(f"--- {symbol} ---")
    print("returnOnEquity:", roe)
    print("profitMargins:", net_margin)
    print("grossMargins:", gross_margin)
    print("operatingMargins:", operating_margin)
    print("revenueGrowth:", rev_growth)
    print("earningsGrowth:", earnings_growth)

    if inc is not None and not inc.empty and len(inc.columns) >= 2:
        print("Income statement columns:", list(inc.columns))
        idx_lower = {str(i).lower(): i for i in inc.index}
        rev_key = next((k for k in idx_lower if "total revenue" in k), None)
        if rev_key:
            revs = inc.loc[idx_lower[rev_key]]
            r0, r1 = revs.iloc[0], revs.iloc[1]
            if r1 and r1 != 0:
                calc_rev_growth = (r0 - r1) / abs(r1)
                print(f"Calculated YoY Revenue Growth from Income Statement: {calc_rev_growth:.4f}")
    print()

if __name__ == "__main__":
    test_ticker("TVSSCS.NS")
    test_ticker("VRLLOG.NS")
    test_ticker("MSFT")
