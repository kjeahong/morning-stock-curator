# -*- coding: utf-8 -*-
import sys
import requests
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

url = 'https://cafe.naver.com/marketnew'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.content, 'html.parser', from_encoding='cp949')

print("=== 카페 메뉴 목록 ===")
for li in soup.select('#cafe-menu ul li a'):
    text = li.text.strip()
    href = li.get('href', '')
    if text:
        print(f" - {text} ({href})")

print("\n=== 최근 등록된 게시글 ===")
for a in soup.find_all('a', href=True):
    if 'ArticleRead.nhn' in a['href']:
        print(f" • {a.text.strip()} (https://cafe.naver.com{a['href']})")
