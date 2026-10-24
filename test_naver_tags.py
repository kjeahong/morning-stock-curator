# -*- coding: utf-8 -*-
import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
url = 'https://search.naver.com/search.naver?where=news&query=%EC%8A%A4%ED%8E%98%EC%BD%94+%EC%82%AC%ED%95%9D%EA%B0%80&sort=1'
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, 'html.parser')

print("Title:", soup.title.text)
for a in soup.find_all('a'):
    txt = a.text.strip()
    if '스페코' in txt or '상한가' in txt or '방산' in txt:
        if len(txt) > 10:
            print('->', txt)
