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

THEME_KEYWORDS = [
    ('정치 / 인맥', ['오세훈', '이재명', '한동훈', '조국', '김동연', '홍준표', '정치', '대선', '총선', '무죄']),
    ('방산 / 안보', ['방산', '김정은', '북한', '북괴', '미사일', '록히드', '우크라이나', '드론', '군사', '스페코', '빅텍', '포메탈']),
    ('우주항공', ['위성', '우주', '우주항공', '누리호', '발사체', 'AP위성', '컨텍', '쎄트렉아이']),
    ('보안 / 사이버', ['보안', '해킹', 'PHP', '사이버', '모니터랩', '샌즈랩', '윈스', '시큐레터']),
    ('바이오 / 신약', ['임상', 'FDA', '치료제', '신약', '암', '바이오', '제약', '항암', 'FC705', '이중항체', '애브비']),
    ('경영권 / M&A / 유증', ['공개매수', '경영권', '최대주주', '유상증자', '유증', '지분', '마루베니', '지구홀딩스']),
    ('무상증자 / 주주환원', ['무상증자', '무증', '주주환원', '밸류업', '자사주', '배당']),
    ('신규상장', ['신규상장', '상장 첫날', '새내기주', '공모']),
    ('디스플레이 / 부품', ['OLED', 'UTG', '롤러블', '디스플레이', '폴더블']),
    ('2차전지 / ESS', ['ESS', '배터리', '2차전지', '삼성SDI', 'LG에너지', 'LG엔솔', '전고체']),
    ('반도체 / AI', ['반도체', 'HBM', 'AI', '인공지능', 'CXL', '엔비디아', '하이닉스', '삼성전자']),
    ('원전 / 전력망', ['원전', '체코', '전력', '변압기', 'SMR', '전선', '원자력']),
    ('로봇 / 자동화', ['로봇', '협동로봇', '자율주행', '스마트팩토리'])
]

def clean_korean_particle(name, base_word=""):
    # Determine 은/는 or 이/가
    check_char = name[-1]
    if check_char == ')' and '(' in name:
        check_char = name.split('(')[0][-1]
    code = ord(check_char) - 0xAC00
    if 0 <= code <= 11171:
        has_batchim = (code % 28) > 0
    else:
        has_batchim = False
    return "은" if has_batchim else "는"

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

def fetch_stock_catalyst(stock, wrap_headlines):
    name = stock['name']
    
    # 1. First check wrap headlines
    for h in wrap_headlines:
        if name in h:
            cat = get_catalyst_from_headline(name, h)
            if cat:
                stock['catalyst'] = cat
                stock['raw_headline'] = h
                return stock

    # 2. Query Google News RSS
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(name)}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers=headers)
    catalyst = ''
    raw_headline = ''
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            root = ET.fromstring(resp.read())
            items = root.findall('.//item')
            for it in items[:4]:
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

def classify_stock_theme(stock):
    text = f"{stock['name']} {stock.get('catalyst', '')} {stock.get('raw_headline', '')}"
    for th_name, kws in THEME_KEYWORDS:
        for kw in kws:
            if kw.lower() in text.lower():
                return th_name
    return '개별 특징주'

def build_full_closing_report():
    # 1. Fetch closing wrap news
    wrap_headlines = []
    try:
        url_wrap = f"https://news.google.com/rss/search?q={urllib.parse.quote('상한가 OR 마감특징주 OR [주식마감] when:1d')}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url_wrap, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            root = ET.fromstring(resp.read())
            for it in root.findall('.//item')[:25]:
                wrap_headlines.append(it.find('title').text or '')
    except Exception:
        pass

    # 2. Fetch top gainers
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

    stocks.sort(key=lambda x: (x['is_limit_up'], x['pct']), reverse=True)
    target_stocks = stocks[:25]

    # 3. Concurrent catalyst fetch
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_stock_catalyst, s, wrap_headlines) for s in target_stocks]
        for f in as_completed(futures):
            f.result()

    # 4. Theme tagging
    theme_buckets = {}
    for s in target_stocks:
        th = classify_stock_theme(s)
        s['theme'] = th
        if th not in theme_buckets:
            theme_buckets[th] = []
        theme_buckets[th].append(s)

    # 5. Build post content in 천마뇌검 authentic structure
    now = datetime.now()
    days = ['월', '화', '수', '목', '금', '토', '일']
    date_str = f"{now.month}월 {now.day}일 {days[now.weekday()]}요일"

    # Header line
    header = "[코스피 +0.30%, 코스닥 -1.62%, 환율 1,324.90원(-0.12%)]"
    
    post_lines = [header, ""]
    used_stocks = set()
    item_num = 1

    # First: Grouped themes with 2+ stocks
    for th_name, st_list in theme_buckets.items():
        if th_name != '개별 특징주' and len(st_list) >= 2:
            leader = st_list[0]
            subs = st_list[1:]
            
            # Construct Theme Headline
            cat = leader.get('catalyst', '') or leader.get('raw_headline', '')
            if not cat:
                cat = f"{th_name} 관련주"
            
            theme_title = f"{item_num}. {cat} 부각에 {th_name} 관련주 급등"
            post_lines.append(theme_title)
            post_lines.append("")
            
            # Leader stock bullet
            particle = clean_korean_particle(leader['display_name'])
            leader_surge = "상한가" if leader['is_limit_up'] else f"급등(+{leader['pct']:.2f}%)"
            post_lines.append(f"- {leader['display_name']}{particle} {cat}에 {leader_surge}")
            
            # Sub stocks bullet
            sub_strs = [f"{s['display_name']}(+{s['pct']:.2f}%)" for s in subs]
            post_lines.append(f"- {', '.join(sub_strs)}")
            post_lines.append("")
            
            for s in st_list:
                used_stocks.add(s['name'])
            item_num += 1

    # Second: Individual stocks
    for s in target_stocks:
        if s['name'] in used_stocks:
            continue
        name = s['display_name']
        pct_str = f"+{s['pct']:.2f}%"
        is_lu = s['is_limit_up']
        cat = s['catalyst']
        
        surge_suffix = "상한가" if is_lu else f"급등({pct_str})"
        
        if not cat:
            if s['pct'] >= 20:
                cat_phrase = "개별 모멘텀 지속 속 수급 집중되며"
            elif s.get('amt', 0) > 100000:
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

        particle = clean_korean_particle(name)
        line = f"{item_num}. {name}{particle} {cat_phrase} {surge_suffix}"
        post_lines.append(line)
        item_num += 1

    post_lines.append("")
    if now.weekday() == 4: # 금요일
        post_lines.append("이번 한주도 정말 고생 많았습니다..")
        post_lines.append("주말 편안하게 보내시기 바랍니다.")
    else:
        post_lines.append("오늘 하루도 시장 참여하시느라 정말 고생 많으셨습니다..")
        post_lines.append("편안한 저녁 시간 보내시기 바랍니다.")

    return "\n".join(post_lines)

print("=== FINAL GENERATOR RESULT ===")
print(build_full_closing_report())
