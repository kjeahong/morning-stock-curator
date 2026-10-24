# -*- coding: utf-8 -*-
import sys
import yfinance as yf

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

tickers = ['NQ=F', 'CL=F', 'MU', 'NVDA', 'EWY']
for sym in tickers:
    try:
        t = yf.Ticker(sym)
        hist = t.history(period='1d', interval='15m')
        closes = [round(float(c), 2) for c in hist['Close'].tolist()]
        print(f"[{sym}] points: {len(closes)}, first: {closes[0] if closes else None}, last: {closes[-1] if closes else None}")
    except Exception as e:
        print(f"[{sym}] error: {e}")
