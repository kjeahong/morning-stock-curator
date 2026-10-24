# -*- coding: utf-8 -*-
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

queries = ['스페코 OR 컨텍 OR 진양산업 OR 노을 OR 퓨처켐 when:1d']

for q in queries:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        root = ET.fromstring(resp.read())
        for item in root.findall('.//item')[:15]:
            print('•', item.find('title').text)
