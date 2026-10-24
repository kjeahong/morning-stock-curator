# -*- coding: utf-8 -*-
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

query = "상한가 OR 마감특징주 OR 오늘의상승주 when:1d"
url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        root = ET.fromstring(resp.read())
        for it in root.findall('.//item')[:20]:
            print(it.find('title').text)
except Exception as e:
    print("Error:", e)
