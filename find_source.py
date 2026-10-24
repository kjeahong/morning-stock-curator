# -*- coding: utf-8 -*-
import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Search for today's exact theme review
query = '스페코 방산테마 상한가'
url = f'https://search.naver.com/search.naver?where=news&query={query}&sort=1'
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, 'html.parser')
print("=== 네이버 뉴스 검색 결과 ===")
for a in soup.select('a.news_tit')[:5]:
    print('•', a.text.strip(), '-->', a.get('href'))

# Let's also check press: 인포스탁 or 연합인포맥스
url2 = 'https://search.naver.com/search.naver?where=news&query=%EC%9D%B8%ED%8F%AC%EC%8A%A4%ED%83%81+%ED%85%8C%EB%A7%88&sort=1'
r2 = requests.get(url2, headers=headers)
soup2 = BeautifulSoup(r2.text, 'html.parser')
print("\n=== 인포스탁 테마 검색 결과 ===")
for a in soup2.select('a.news_tit')[:5]:
    print('•', a.text.strip())
