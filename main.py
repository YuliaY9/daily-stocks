import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText

import os

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
RECEIVER = os.getenv("RECEIVER")


with open("ticker.txt", "r") as f:
    tickers = [line.strip().upper() for line in f if line.strip()]


def calculate_atr(data, period=14):
    high = data["High"]
    low = data["Low"]
    close = data["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(period).mean()

    return atr


def get_volume_status(vol_ratio):
    if vol_ratio < 0.8:
        return "LOW"
    if vol_ratio < 1.5:
        return "NORMAL"
    if vol_ratio < 2:
        return "HIGH"
    return "EXTREME"


alerts = []
full_watchlist = []
errors = []


for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="6mo")

        if data.empty or len(data) < 65:
            errors.append(f"{ticker}: not enough data")
            continue

        close = data["Close"]
        open_price = data["Open"]
        volume = data["Volume"]

        price = close.iloc[-1]

        d1 = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100
        d2 = ((close.iloc[-2] - close.iloc[-3]) / close.iloc[-3]) * 100
        d3 = ((close.iloc[-3] - close.iloc[-4]) / close.iloc[-4]) * 100

        change_5d = ((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6]) * 100

        high_20 = close.rolling(20).max().iloc[-1]
        high_60 = close.rolling(60).max().iloc[-1]

        dist_high_20 = ((price - high_20) / high_20) * 100
        dist_high_60 = ((price - high_60) / high_60) * 100

        avg_vol_20 = volume.rolling(20).mean().iloc[-1]
        vol_today = volume.iloc[-1] / avg_vol_20
        vol_yesterday = volume.iloc[-2] / avg_vol_20

        vol_text = get_volume_status(vol_today)

        atr = calculate_atr(data, 14).iloc[-1]
        atr_pct = (atr / price) * 100

        today_green = close.iloc[-1] > open_price.iloc[-1]

        panic_threshold = max(5, atr_pct * 1.5)
        deep_threshold = max(15, atr_pct * 3)

        tags = []

        if d1 <= -panic_threshold and vol_today >= 1.5 and dist_high_60 > -25:
            tags.append("PANIC DIP")

        if (
            d2 <= -panic_threshold
            and vol_yesterday >= 1.5
            and d1 > 0
            and today_green
            and vol_today >= 1.2
            and dist_high_60 > -25
        ):
            tags.append("CAPITULATION REVERSAL")

        if (
            -12 <= dist_high_20 <= -3
            and change_5d < 0
            and d1 > -panic_threshold
            and vol_today < 1.5
        ):
            tags.append("CLEAN PULLBACK")

        if (
            today_green
            and vol_today >= 1.3
            and d1 > 0
            and change_5d < 0
            and -20 <= dist_high_20 <= -3
        ):
            tags.append("BUYERS STEPPING IN")

        if dist_high_60 <= -deep_threshold or (d1 <= -panic_threshold and vol_today >= 2):
            tags.append("DEEP / RISKY")

        line = (
            f"{ticker} | Price: {price:.2f}$ | "
            f"3D: {d3:.1f}%, {d2:.1f}%, {d1:.1f}% | "
            f"5D: {change_5d:.1f}% | "
            f"From high: {dist_high_20:.1f}%/20d, {dist_high_60:.1f}%/60d | "
            f"ATR: {atr_pct:.1f}% | "
            f"Vol: {vol_text} ({vol_today:.1f}x)"
        )

        full_watchlist.append(line)

        if tags:
            alerts.append(f"{' | '.join(tags)}\n{line}")

    except Exception as e:
        errors.append(f"{ticker}: Error - {e}")


message = ""

if alerts:
    message += "ALERTS:\n\n"
    for alert in alerts:
        message += alert + "\n\n"
else:
    message += "No special alerts today.\n\n"

message += "--------------------------\n"
message += "FULL WATCHLIST:\n\n"

for line in full_watchlist:
    message += line + "\n"

if errors:
    message += "\n--------------------------\n"
    message += "ERRORS:\n\n"
    for error in errors:
        message += error + "\n"


msg = MIMEText(message, "plain", "utf-8")
msg["Subject"] = "Daily Stock Pullback Scanner"
msg["From"] = EMAIL
msg["To"] = RECEIVER

try:
    server = smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=10,
        local_hostname="localhost"
    )

    server.login(EMAIL, PASSWORD)
    server.sendmail(EMAIL, RECEIVER, msg.as_string())
    server.quit()

    print("Email sent!")

except Exception as e:
    print("Email failed:", e)