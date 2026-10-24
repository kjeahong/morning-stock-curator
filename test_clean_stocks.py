# -*- coding: utf-8 -*-
import sys
import requests
import json
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0'}

stocks = []
for sosok in [0, 1]:
    r = requests.get(f'https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=rise&sosok={sosok}', headers=headers)
    items = r.json().get('result', {}).get('itemList', [])
    for it in items:
        # ETF / ETN 제외
        if it.get('etf') or it.get('etn'):
            continue
        name = it.get('nm', '').strip()
        if any(bad in name for bad in ['ETF', 'ETN', '레버리지', '인버스', '선물']):
            continue
        pct = float(it.get('cr', 0.0))
        amt = it.get('aa', 0) # 백만원
        stocks.append({
            'name': name,
            'pct': pct,
            'amt': amt,
            'is_limit_up': pct >= 29.5
        })

# Sort by limit up first, then trading amount/pct
stocks.sort(key=lambda x: (x['is_limit_up'], x['amt']), reverse=True)

print("=== 필터링된 진짜 급등 보통주 목록 TOP 15 ===")
for s in stocks[:15]:
    lu = "★상한가" if s['is_limit_up'] else ""
    print(f"- {s['name']} (+{s['pct']}%) 거래대금: {s['amt']//100}억 {lu}")
