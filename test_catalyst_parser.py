# -*- coding: utf-8 -*-
import sys
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def fetch_rss_items(query, limit=20):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers=headers)
    items = []
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            root = ET.fromstring(resp.read())
            for it in root.findall('.//item')[:limit]:
                title = it.find('title').text or ''
                items.append(title)
    except Exception:
        pass
    return items

def extract_catalyst_phrase(stock_name, raw_title):
    t = raw_title
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'\(.*?\)', '', t)
    t = t.strip(' ,·:')

    # Look for "소식에", "영향에", "기대감에", "부각에", "따라", "발표에", "체결에"
    patterns = [
        r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급)에?)\s*(?:급등|상한가|강세|폭등|상승)',
        r'(.*?)\s*(?:상한가|급등|강세|폭등|상승)',
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            phrase = m.group(1).strip(' ,·:')
            # remove stock name from phrase if present
            phrase = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', phrase).strip()
            phrase = phrase.replace(stock_name, '').strip(' ,·:')
            if len(phrase) >= 5:
                return phrase
                
    # fallback: clean stock name out
    p = re.compile(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', re.I)
    cleaned = p.sub('', t).strip(' ,·:')
    cleaned = cleaned.replace(stock_name, '').strip(' ,·:')
    return cleaned if len(cleaned) >= 5 else t

print("Test phrase extraction:")
print("1.", extract_catalyst_phrase("도우인시스", "도우인시스, 차량용 롤러블 OLED UTG 개발한다 - 디일렉"))
print("2.", extract_catalyst_phrase("모니터랩", "PHP 보안 비상에 관련주 강세···모니터랩 25%↑ - 뉴스웨이"))
print("3.", extract_catalyst_phrase("AP위성", "AP위성 18.71% 상승…차세대 위성 사업 수주 기대 - 잡포스트"))
print("4.", extract_catalyst_phrase("아이패밀리에스씨", "[특징주] 아이패밀리에스씨, 日 기업 공개매수에 상한가 - 연합뉴스"))
print("5.", extract_catalyst_phrase("노을", "[특징주] 노을, 지구홀딩스 최대주주 변경 앞두고 상한가 - 바이오타임즈"))
print("6.", extract_catalyst_phrase("스페코", "김정은 사망설 확산에 스페코 상한가…방산주 매수세 집중 - 더팩트"))
