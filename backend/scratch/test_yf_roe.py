import yfinance as yf

ticker = yf.Ticker("TVSSCS.NS")
info = ticker.info or {}
print("returnOnEquity:", info.get("returnOnEquity"))
print("returnOnAssets:", info.get("returnOnAssets"))
print("grossMargins:", info.get("grossMargins"))
print("operatingMargins:", info.get("operatingMargins"))
print("profitMargins:", info.get("profitMargins"))
