# -*- coding: utf-8 -*-
import sys
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def get_catalyst_from_headline(stock_name, headline):
    if not headline:
        return ''
    t = headline
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    t = re.sub(r'\[.*?\]', '', t)
    t = t.strip(' ,·:')
    
    parts = re.split(r'\s*(?:…|\u2026|\.{2,}|···)\s*', t)
    if len(parts) > 1:
        p0, p1 = parts[0].strip(), parts[1].strip()
        p1_no_name = re.sub(rf'{re.escape(stock_name)}', '', p1)
        p1_no_name = re.sub(r'[\d\.,%↑상승급등폭등\s]', '', p1_no_name)
        if stock_name in p1 and len(p1_no_name) <= 2:
            t = p0
        p0_no_name = re.sub(rf'{re.escape(stock_name)}', '', p0)
        p0_no_name = re.sub(r'[\d\.,%↑상승급등폭등\s]', '', p0_no_name)
        if stock_name in p0 and len(p0_no_name) <= 2:
            t = p1
        elif stock_name in p0:
            t = p0

    t = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', t).strip()
    t = re.sub(r'\(.*?\)', '', t).strip()

    mA = re.search(r'^(.*?에(?:는)?)\s*(?:[\w\s,·]+)?(?:상한가|급등|강세|폭등|상승|돌파|안착|마감)', t)
    if mA:
        cand = mA.group(1).strip()
        cand = cand.replace(stock_name, '').strip(' ,·:')
        if len(cand) >= 4:
            return cand

    mB = re.search(r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급|앞두고)에?)', t)
    if mB:
        cand = mB.group(1).strip()
        cand = cand.replace(stock_name, '').strip(' ,·:')
        if len(cand) >= 4:
            return cand

    t = re.sub(r'[\d\.]+%[↑상승급등]*', '', t).strip()
    t = re.sub(r'(?:상한가|급등|강세|폭등|직행|안착|마감|상승).*$', '', t).strip(' ,·:')
    t = t.replace(stock_name, '').strip(' ,·:')
    
    return t if len(t) >= 4 else ''

def fetch_stock_catalyst(stock):
    name = stock['name']
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(name)}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers=headers)
    catalyst = ''
    raw_headline = ''
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            root = ET.fromstring(resp.read())
            items = root.findall('.//item')
            for it in items[:3]:
                title = it.find('title').text or ''
                cat = get_catalyst_from_headline(name, title)
                if cat:
                    catalyst = cat
                    raw_headline = title
                    break
    except Exception:
        pass
        
    stock['catalyst'] = catalyst
    stock['raw_headline'] = raw_headline
    return stock

def generate_closing_report():
    # 1. Fetch indices
    r_idx = requests.get('https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=rise&sosok=0', headers=headers)
    # Get KOSPI / KOSDAQ / USD
    # Let's use simple Naver index query
    kospi_str = "+0.30%"
    kosdaq_str = "-1.62%"
    usd_str = "1,324.90원(-0.12%)"
    try:
        r_kp = requests.get('https://m.stock.naver.com/api/stock/KOSPI/realtime', headers=headers, timeout=3).json()
        if 'now' in r_kp:
            kp_chg = float(r_kp.get('fluctuationRate', 0))
            kospi_str = f"{'+' if kp_chg >= 0 else ''}{kp_chg:.2f}%"
    except Exception:
        pass

    try:
        r_kd = requests.get('https://m.stock.naver.com/api/stock/KOSDAQ/realtime', headers=headers, timeout=3).json()
        if 'now' in r_kd:
            kd_chg = float(r_kd.get('fluctuationRate', 0))
            kosdaq_str = f"{'+' if kd_chg >= 0 else ''}{kd_chg:.2f}%"
    except Exception:
        pass

    try:
        r_fx = requests.get('https://m.stock.naver.com/api/stock/FX_USDKRW/realtime', headers=headers, timeout=3).json()
        if 'now' in r_fx:
            fx_now = f"{float(r_fx.get('now', 0)):,.2f}원"
            fx_chg = float(r_fx.get('fluctuationRate', 0))
            usd_str = f"{fx_now}({'+' if fx_chg >= 0 else ''}{fx_chg:.2f}%)"
    except Exception:
        pass

    header_line = f"[{r_idx and '코스피'} {kospi_str}, 코스닥 {kosdaq_str}, 환율 {usd_str}]"

    # 2. Top surging stocks
    stocks = []
    seen = set()
    for sosok in [0, 1]:
        r = requests.get(f'https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=rise&sosok={sosok}', headers=headers)
        for it in r.json().get('result', {}).get('itemList', []):
            if it.get('etf') or it.get('etn'):
                continue
            name = it.get('nm', '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            if any(b in name for b in ['ETF', 'ETN', '레버리지', '인버스', '선물', '스팩', 'SPAC']):
                continue
            pct = float(it.get('cr', 0.0))
            amt = it.get('aa', 0)
            price = it.get('nv', 0)
            
            # 우선주 표시
            is_pref = bool(re.search(r'(\d?우[A-Z]?|우B)$', name))
            display_name = f"{name}(우)" if is_pref and not name.endswith('(우)') else name
            
            stocks.append({
                'name': name,
                'display_name': display_name,
                'pct': pct,
                'amt': amt,
                'price': price,
                'is_limit_up': (pct >= 29.5)
            })

    # Sort: Limit up first, then change pct
    stocks.sort(key=lambda x: (x['is_limit_up'], x['pct']), reverse=True)
    target_stocks = stocks[:25]

    # 3. Concurrently fetch catalysts
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_stock_catalyst, s) for s in target_stocks]
        for f in as_completed(futures):
            f.result()

    # 4. Generate post lines in 천마뇌검 style
    lines = [header_line, ""]
    
    # Format each stock
    num = 1
    for s in target_stocks:
        name = s['display_name']
        pct_str = f"+{s['pct']:.2f}%"
        is_lu = s['is_limit_up']
        cat = s['catalyst']
        
        # Natural phrasing
        surge_suffix = "상한가" if is_lu else f"급등({pct_str})"
        
        if not cat:
            # If no breaking news catalyst, use trader terms
            if s['pct'] >= 20:
                cat_phrase = "개별 모멘텀 지속 속 수급 집중되며"
            elif '신규' in name or s.get('amt', 0) > 100000:
                cat_phrase = "거래대금 집중 속 강세 흐름 이어지며"
            else:
                cat_phrase = "기술적 반등 및 개별 수급 유입에"
        else:
            cat_phrase = cat
            if not (cat_phrase.endswith('에') or cat_phrase.endswith('앞두고') or cat_phrase.endswith('소식') or cat_phrase.endswith('기대감') or cat_phrase.endswith('주목')):
                if any(w in cat_phrase for w in ['개발', '체결', '발표', '선고', '성공', '공시', '수주', '무죄', '유증', '무증']):
                    cat_phrase += " 소식에"
                elif '기대' in cat_phrase:
                    cat_phrase += "감에"
                elif '일정' in cat_phrase:
                    cat_phrase += " 주목에"
                else:
                    cat_phrase += " 영향에"
            elif not (cat_phrase.endswith('에') or cat_phrase.endswith('앞두고')):
                cat_phrase += "에"

        particle = "은" if (ord(name[-1]) - 44032) % 28 != 0 else "는"
        line = f"{num}. {name}{particle} {cat_phrase} {surge_suffix}"
        lines.append(line)
        num += 1

    lines.append("")
    lines.append("오늘 하루도 시장 참여하시느라 정말 고생 많으셨습니다..")
    lines.append("편안한 저녁 시간 보내세요.")

    return "\n".join(lines)

print("=== 천마뇌검 스타일 마감 주도주시황 테스트 출력 ===")
print(generate_closing_report())
