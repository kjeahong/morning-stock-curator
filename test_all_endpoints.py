# -*- coding: utf-8 -*-
import sys
import requests

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

base = 'http://127.0.0.1:5000'

# 1. Index
r0 = requests.get(base + '/')
print("[1] GET / -> Status:", r0.status_code, "Length:", len(r0.text), "Has closingView:", 'id="closingView"' in r0.text)

# 2. Indices
r1 = requests.get(base + '/api/indices')
print("[2] GET /api/indices -> Status:", r1.status_code, "Items:", len(r1.json()))

# 3. News
r2 = requests.get(base + '/api/news')
print("[3] GET /api/news -> Status:", r2.status_code, "News count:", len(r2.json().get('news', [])))

# 4. Closing
r3 = requests.get(base + '/api/closing')
c_data = r3.json()
print("[4] GET /api/closing -> Status:", r3.status_code, "Header:", c_data.get('header_line'))
print("   Limit-ups:", [s['name'] for s in c_data.get('limit_ups', [])])
print("   Themes:", [t['name'] for t in c_data.get('themes', [])])
print("   Draft length:", len(c_data.get('full_draft_text', '')))
print("   HTML length:", len(c_data.get('full_draft_html', '')))
