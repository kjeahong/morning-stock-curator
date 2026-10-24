# -*- coding: utf-8 -*-
import sys
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

THEME_KEYWORDS = [
    ('방산/안보', ['방산', '사망설', '스페코', '빅텍', '포메탈', '한일단조', '휴니드', '김정은']),
    ('우주항공/위성', ['우주', '위성', '컨텍', 'AP위성', 'LK삼양', '켄코아', '스페이스X', '광통신']),
    ('오세훈/정치', ['오세훈', '진양', '진양산업', '진양화학', '진양폴리', '무죄']),
    ('아이폰/폴더블', ['아이폰', '도우인시스', '파인엠텍', '비에이치', '애플']),
    ('로봇/AI', ['로봇', '협진', '앤로보틱스', '라온피플', '빅웨이브', '에브리봇', '삼성전자']),
    ('원전/전력', ['원전', '전력', '슈퍼커패시터', '비나텍', 'LS에코', '블룸에너지', 'SOFC', '변압기']),
    ('바이오/제약', ['임상', 'FDA', '전립선암', '퓨처켐', '퓨쳐켐', '지투지바이오', '알테오젠', '큐리옥스', '치료제', '신약']),
    ('재건/우크라', ['재건', '종전', '대모', '삼성E&A', '전진건설', '한미글로벌'])
]

def clean_catalyst_title(stock_name, title):
    if ' - ' in title:
        title = title.rsplit(' - ', 1)[0]
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    title = title.strip(' ,·:')
    p = re.compile(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', re.I)
    cleaned = p.sub('', title).strip(' ,·:')
    return cleaned if len(cleaned) >= 5 else title

def fetch_rss_headlines(query):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    results = []
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall('.//item')[:25]:
                t = item.find('title').text or ''
                results.append(t)
    except Exception:
        pass
    return results

print("1. 지수 및 환율 수집 중...")
# 지수 수집
def get_market_header():
    ks_txt, kq_txt, fx_txt = "+0.00%", "+0.00%", "1,325.00원(0.00%)"
    try:
        t_ks = yf.Ticker('^KS11').fast_info
        chg_pct = ((t_ks.last_price - t_ks.previous_close) / t_ks.previous_close) * 100
        sign = '+' if chg_pct > 0 else ''
        ks_txt = f"{sign}{chg_pct:.2f}%"
    except Exception: pass
    
    try:
        t_kq = yf.Ticker('^KQ11').fast_info
        chg_pct = ((t_kq.last_price - t_kq.previous_close) / t_kq.previous_close) * 100
        sign = '+' if chg_pct > 0 else ''
        kq_txt = f"{sign}{chg_pct:.2f}%"
    except Exception: pass

    try:
        t_fx = yf.Ticker('USDKRW=X').fast_info
        chg_pct = ((t_fx.last_price - t_fx.previous_close) / t_fx.previous_close) * 100
        sign = '+' if chg_pct > 0 else ''
        fx_txt = f"{t_fx.last_price:,.2f}원({sign}{chg_pct:.2f}%)"
    except Exception: pass

    return f"[코스피 {ks_txt}, 코스닥 {kq_txt}, 환율 {fx_txt}]"

header_line = get_market_header()
print("헤더:", header_line)

print("2. 상승 종목 수집 중...")
top_stocks = []
for sosok in [0, 1]:
    try:
        url_rise = f'https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=rise&sosok={sosok}'
        r_rise = requests.get(url_rise, headers=headers, timeout=5)
        items = r_rise.json().get('result', {}).get('itemList', [])
        for it in items[:20]:
            name = it.get('nm', '').strip()
            pct = float(it.get('cr', 0.0))
            if pct >= 5.0:
                top_stocks.append({
                    'name': name,
                    'pct': pct,
                    'pct_str': f"+{pct:.2f}%",
                    'is_limit_up': pct >= 29.5
                })
    except Exception: pass

print(f"수집된 급등 종목 수: {len(top_stocks)}개")

print("3. 종목별 실제 상승 재료 검색 중...")
general_news = fetch_rss_headlines("특징주 OR 상한가 OR 주식마감 when:1d")

def find_catalyst_for_stock(stock):
    name = stock['name']
    for t in general_news:
        if name in t:
            return clean_catalyst_title(name, t)
    # Individual targeted search
    ind_news = fetch_rss_headlines(f"{name} when:1d")
    for t in ind_news:
        if name in t or len(ind_news) > 0:
            return clean_catalyst_title(name, ind_news[0])
    return "단기 매수세 유입에 강세"

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(find_catalyst_for_stock, st): st for st in top_stocks[:15]}
    for f in futures:
        st = futures[f]
        st['reason'] = f.result()

print("\n=== 천마뇌검 스타일 주도주시황 생성 결과 ===")
output = [header_line, "\n"]
idx = 1
for st in top_stocks[:12]:
    action = "상한가" if st['is_limit_up'] else f"강세({st['pct_str']})"
    output.append(f"{idx}. {st['name']}은(는) {st['reason']} 소식에 {action}")
    idx += 1

output.append("\n오늘 하루도 고생 많았습니다.")
result_text = "\n".join(output)
print(result_text)
