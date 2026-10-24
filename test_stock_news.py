# -*- coding: utf-8 -*-
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

test_stocks = ['도우인시스', '모니터랩', 'AP위성', '지투지바이오', '디티에스']

for name in test_stocks:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(name)}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            root = ET.fromstring(resp.read())
            items = root.findall('.//item')
            if items:
                print(f"[{name}] -> {items[0].find('title').text}")
            else:
                print(f"[{name}] -> 뉴스 없음")
    except Exception as e:
        print(f"[{name}] -> Error {e}")
