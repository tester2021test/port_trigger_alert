import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import pytz
import os

# ================== TELEGRAM CONFIG ==================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("❌ Telegram secrets missing")

IST = pytz.timezone("Asia/Kolkata")
CSV_FILE = "trade_journal.csv"

# ================== PORTFOLIO ==================
PORTFOLIO = {
    "DIVOPPBEES.NS": {"name": "Nippon India ETF Dividend Opportunities", "type": "ETF",
                      "levels": [(78, 79, 25), (74, 75, 35)]},
    "HEALTHY.NS": {"name": "BSL Nifty HealthCare ETF", "type": "ETF",
                   "levels": [(13.8, 14.0, 100), (12.8, 13.2, 150)]},
    "MAHKTECH.NS": {"name": "Mahktech", "type": "STOCK",
                     "levels": [(25.5, 26.0, 150), (23.0, 24.0, 200)]},
    "IRCTC.NS": {"name": "IRCTC", "type": "STOCK",
                 "levels": [(560, 580, 8), (500, 520, 10)]},
    "TATAGOLD.NS": {"name": "Tata Gold ETF", "type": "ETF",
                    "levels": [(14.5, 14.6, 300), (13.8, 14.0, 400), (12.8, 13.2, 500)]},
    "EVINDIA.NS": {"name": "EVINDIA ETF", "type": "ETF",
                   "levels": [(28.0, 28.5, 100), (26.0, 26.5, 150), (23.5, 24.0, 200)]},
    "GAIL.NS": {"name": "GAIL", "type": "STOCK",
                "levels": [(150, 152, 50), (138, 142, 70), (125, 130, 80)]},
    "IOB.NS": {"name": "Indian Overseas Bank", "type": "STOCK",
               "levels": [(32, 33, 40), (28, 29, 60), (24, 25, 50)]},
    "TMPV.NS": {"name": "Tata Motors Passenger Vehicles Ltd", "type": "STOCK",
                "levels": [(330, 335, 6), (300, 310, 10), (270, 280, 10)]},
    "GROWWRLTY.NS": {"name": "Groww Nifty Realty ETF", "type": "ETF",
                     "levels": [(8.0, 8.2, 70), (7.2, 7.4, 100), (6.2, 6.5, 100)]},
    "CESC.NS": {"name": "CESC", "type": "STOCK",
                "levels": [(132, 135, 15), (120, 125, 20), (105, 110, 15)]}
}

# ================== INDICATORS ==================
def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))

def fetch_indicators(symbol):
    df = yf.download(
        symbol,
        period="3mo",
        interval="1d",
        progress=False,
        threads=False
    )

    if df.empty or len(df) < 50:
        return None

    # 🔐 Fix for MultiIndex columns (GitHub Actions bug)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["DMA20"] = df["Close"].rolling(20).mean()
    df["DMA50"] = df["Close"].rolling(50).mean()
    df["RSI"] = calculate_rsi(df["Close"])

    last = df.tail(1)

    try:
        price = float(last["Close"].iloc[0])
        dma20 = float(last["DMA20"].iloc[0])
        dma50 = float(last["DMA50"].iloc[0])
        rsi = float(last["RSI"].iloc[0])
    except (TypeError, ValueError):
        return None

    if pd.isna(price) or pd.isna(dma20) or pd.isna(dma50) or pd.isna(rsi):
        return None

    if price > dma20 > dma50:
        trend = "Bullish"
    elif price < dma20 < dma50:
        trend = "Bearish"
    else:
        trend = "Sideways"

    return price, dma20, dma50, rsi, trend

# ================== CSV JOURNAL ==================
def log_to_csv(symbol, name, level, price, qty, trend, rsi, dma20, dma50):
    now = datetime.now(IST)
    row = {
        "Date": now.strftime("%Y-%m-%d"),
        "Time": now.strftime("%H:%M:%S"),
        "Symbol": symbol,
        "Stock Name": name,
        "Level": level,
        "Price": round(price, 2),
        "Quantity": qty,
        "Trend": trend,
        "RSI": round(rsi, 2),
        "20 DMA": round(dma20, 2),
        "50 DMA": round(dma50, 2)
    }

    df = pd.DataFrame([row])
    header = not os.path.exists(CSV_FILE)
    df.to_csv(CSV_FILE, mode="a", header=header, index=False)

# ================== TELEGRAM ==================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        },
        timeout=10
    )

# ================== MAIN ==================
def main():
    print("📡 Portfolio Trigger Alert – Run Started")

    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    for symbol, data in PORTFOLIO.items():
        result = fetch_indicators(symbol)

        if result is None:
            print(f"[{now}] {symbol} ⚠️ Data unavailable")
            continue

        price, dma20, dma50, rsi, trend = result
        status = "WAIT"

        for idx, (low, high, qty) in enumerate(data["levels"], start=1):
            if low <= price <= high:
                status = f"AVERAGE ZONE L{idx}"

                send_telegram(
                    f"🚨 *AVERAGE OUT ALERT*\n\n"
                    f"*Stock:* {data['name']}\n"
                    f"*Symbol:* {symbol}\n"
                    f"*Price:* ₹{price:.2f}\n"
                    f"*Level:* {idx}\n"
                    f"*Qty:* {qty}\n\n"
                    f"*Trend:* {trend}\n"
                    f"*RSI:* {rsi:.1f}\n"
                    f"*20 DMA:* ₹{dma20:.2f}\n"
                    f"*50 DMA:* ₹{dma50:.2f}"
                )

                log_to_csv(
                    symbol, data["name"], idx,
                    price, qty, trend, rsi, dma20, dma50
                )
                break

        print(
            f"[{now}] {symbol} | ₹{price:.2f} | "
            f"Trend: {trend} | RSI: {rsi:.1f} | Status: {status}"
        )

    print("✅ Run completed successfully")

if __name__ == "__main__":
    main()
