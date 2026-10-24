# -*- coding: utf-8 -*-
import sys
import requests
import json
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

article_ids = ['2661188', '2661049', '2660898', '2660758']

for aid in article_ids:
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)',
        'Referer': f'https://m.cafe.naver.com/ca-fe/web/cafes/11974608/articles/{aid}'
    }
    url = f'https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/11974608/articles/{aid}?query=&useCafeId=true&requestFrom=A'
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        art = data.get('result', {}).get('article', {})
        subject = art.get('subject', '')
        content_html = art.get('contentHtml', '')
        soup = BeautifulSoup(content_html, 'html.parser')
        print("=" * 60)
        print(f"TITLE: {subject} (ID: {aid})")
        print("=" * 60)
        print(soup.text.strip()[:1500])
        print("\n")
