# -*- coding: utf-8 -*-
import sys
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def clean_catalyst_title(stock_name, title):
    # Remove media suffix
    if ' - ' in title:
        title = title.rsplit(' - ', 1)[0]
    # Remove tags like [특징주], [주식마감], [공시해부]
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    title = title.strip(' ,·:')
    
    # If title starts with stock name
    p = re.compile(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', re.I)
    cleaned = p.sub('', title).strip(' ,·:')
    
    # Check if stock name appears inside
    # e.g. "오세훈 2심 무죄에 진양산업·화학 상한가"
    return cleaned if len(cleaned) >= 6 else title

print("Catalyst clean test:")
print(clean_catalyst_title('스페코', '김정은 사망설 확산에 스페코 상한가…방산주 매수세 집중 - 더팩트'))
print(clean_catalyst_title('퓨쳐켐', '퓨쳐켐, 전립선암 치료제 \'FC705\' 미국 임상 2a상서 항암 효과 확인 - 히트뉴스'))
print(clean_catalyst_title('노을', '[특징주] 노을, 지구홀딩스에 27.5억 유증…최대주주 바뀐다 - 녹색경제신문'))
print(clean_catalyst_title('진양산업', '오세훈 시장 항소심 무죄 선고에 진양산업 상한가 - 이데일리'))
