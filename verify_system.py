# -*- coding: utf-8 -*-
import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 1. Check template on disk
with open('c:/Users/Administrator/Desktop/Overhang/templates/index.html', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
print("Template parsed successfully!")
print("Found #closingView:", bool(soup.select_one('#closingView')))
print("Found #closingFullDraft:", bool(soup.select_one('#closingFullDraft')))
print("Found #closingStocksContainer:", bool(soup.select_one('#closingStocksContainer')))
print("Found #closingMarketBox:", bool(soup.select_one('#closingMarketBox')))

# 2. Check server endpoint
try:
    r = requests.get('http://127.0.0.1:5000/api/closing', timeout=15)
    print("Server /api/closing status code:", r.status_code)
    data = r.json()
    print("API status:", data.get('status'))
    print("Header line:", data.get('header_line'))
    print("Limit ups count:", len(data.get('limit_ups', [])))
    print("Themes count:", len(data.get('themes', [])))
    print("All top stocks count:", len(data.get('all_top_stocks', [])))
    print("\n--- SAMPLE DRAFT (First 400 chars) ---")
    print(data.get('full_draft_text', '')[:400])
except Exception as e:
    print("Server query error:", e)
