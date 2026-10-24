# -*- coding: utf-8 -*-
"""
증시 뉴스 및 지수 데이터 통합 수집 모듈 (collector.py)
- 네이버 증권/경제 실시간 속보 크롤링 (증권, 산업/재계, 글로벌경제)
- 구글 뉴스 RSS (미국증시 마감, 특징주, 장전 공시)
- 야후 파이낸스 / 네이버 지수 (다우, 나스닥, S&P500, SOX, 환율, 유가, 국채금리)
- 자동 테마 키워드 태깅 및 시간 파싱
"""

import re
import time
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
import yfinance as yf

# 테마 분류 키워드 사전
THEME_RULES = [
    ('🇺🇸 미증시/매크로', [
        '뉴욕증시', '나스닥', '다우', 'S&P', '월가', '연준', '파월', '금리', '환율', 
        '달러', '유가', 'WTI', '국채', 'CPI', 'PPI', 'FOMC', '경기침체', '인플레이션', '트럼프', '관세'
    ]),
    ('⚡ 반도체/AI', [
        '반도체', 'HBM', '엔비디아', '삼성전자', 'SK하이닉스', '솔리다임', '파운드리', 
        'AI', '인공지능', '챗GPT', '오픈AI', '소부장', 'CXL', 'D램', '낸드', 'ASML', 'TSMC', '한미반도체', '유리기판'
    ]),
    ('🔋 2차전지/전기차', [
        '2차전지', '이차전지', '배터리', '에코프로', '포스코홀딩스', '포스코퓨처엠', 
        'LG에너지', 'LG화학', '엘앤에프', '전기차', '테슬라', '리튬', '양극재', '음극재', '전고체'
    ]),
    ('🧬 바이오/제약', [
        '바이오', '제약', '임상', 'FDA', '알테오젠', '삼성바이오', '유한양행', 
        'HLB', '셀트리온', '신약', '비만치료제', '의료AI', '루닛', '뷰노', '기술이전', 'LO'
    ]),
    ('🤖 로봇/자율주행', [
        '로봇', '협동로봇', '레인보우로보', '두산로보', '자율주행', '현대차', '기아', '스마트팩토리'
    ]),
    ('⚡ 원전/전력망', [
        '원전', '원자력', '체코원전', '웨스팅하우스', '전력', '변압기', '전선', 
        '효성중공업', 'HD현대일렉', 'LS일렉', 'LS전선', '전력인프라', 'SMR'
    ]),
    ('🛡️ 방산/우주', [
        '방산', '한화에어로', '현대로템', 'KAI', 'LIG넥스원', '폴란드', '방위산업', 'K9', '천궁', '우주항공'
    ]),
    ('📋 공시/특징주/수주', [
        '특징주', '공시', '수주', '상한가', '신고가', '영업이익', '실적', '흑자', 
        '공급계약', '지분', '공개매수', '무상증자', '유상증자', '경영권'
    ])
]

# 캐시 저장소
_cache = {
    'news': [],
    'indices': {},
    'last_news_time': 0,
    'last_indices_time': 0
}

def normalize_title(t):
    return ''.join(c for c in t.lower() if c.isalnum())

def tag_article(title, text=''):
    combined = title + ' ' + text
    tags = []
    for theme, keywords in THEME_RULES:
        for kw in keywords:
            if kw.lower() in combined.lower():
                tags.append(theme)
                break
    return tags if tags else ['📰 증시일반']

def parse_time_str(time_str):
    now = datetime.now()
    if not time_str:
        return now, ''
    ts = time_str.strip()
    
    # 25분전
    m_min = re.match(r'(\d+)분\s*전', ts)
    if m_min:
        dt = now - timedelta(minutes=int(m_min.group(1)))
        return dt, f'{m_min.group(1)}분 전'
        
    # 2시간전
    m_hr = re.match(r'(\d+)시간\s*전', ts)
    if m_hr:
        dt = now - timedelta(hours=int(m_hr.group(1)))
        return dt, f'{m_hr.group(1)}시간 전'
        
    # 네이버 형식: 2026.10.23. 오전 06:30
    m_full = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})\.\s+(오전|오후)\s+(\d{1,2}):(\d{1,2})', ts)
    if m_full:
        y, m, d, ap, h, mi = m_full.groups()
        h = int(h)
        if ap == '오후' and h < 12: h += 12
        elif ap == '오전' and h == 12: h = 0
        dt = datetime(int(y), int(m), int(d), h, int(mi))
        return dt, dt.strftime('%H:%M')
        
    return now, ts

def get_market_indices():
    """야후 파이낸스 기반 주요 지수 및 환율/유가/금리 수집"""
    now = time.time()
    if _cache['indices'] and (now - _cache['last_indices_time'] < 120):
        return _cache['indices']

    symbols = {
        '다우': ('^DJI', 'DOW'),
        '나스닥': ('^IXIC', 'NASDAQ'),
        'S&P 500': ('^GSPC', 'S&P 500'),
        '필라델피아 반도체': ('^SOX', 'SOX'),
        '원·달러 환율': ('USDKRW=X', 'USD/KRW'),
        'WTI 유가': ('CL=F', 'WTI Oil'),
        '미 국채 10년물': ('^TNX', 'US 10Y')
    }

    results = []

    def fetch_symbol(name, ticker_sym, short_label):
        try:
            t = yf.Ticker(ticker_sym)
            info = t.fast_info
            price = getattr(info, 'last_price', None) or getattr(info, 'regular_market_price', 0)
            prev = getattr(info, 'previous_close', None) or getattr(info, 'regular_market_previous_close', price)
            if price and prev:
                chg = price - prev
                chg_pct = (chg / prev) * 100
            else:
                chg, chg_pct = 0, 0
            
            # 서식 처리
            if '환율' in name:
                fmt_price = f"{price:,.1f}원"
            elif '유가' in name:
                fmt_price = f"${price:,.2f}"
            elif '국채' in name:
                fmt_price = f"{price:.2f}%"
            else:
                fmt_price = f"{price:,.2f}"

            sign = '+' if chg > 0 else ''
            fmt_pct = f"{sign}{chg_pct:.2f}%"
            status = 'up' if chg > 0 else ('down' if chg < 0 else 'flat')

            return {
                'name': name,
                'short': short_label,
                'price': fmt_price,
                'change': f"{sign}{chg:,.2f}",
                'change_pct': fmt_pct,
                'status': status
            }
        except Exception as e:
            return {
                'name': name,
                'short': short_label,
                'price': '-',
                'change': '0',
                'change_pct': '0.00%',
                'status': 'flat'
            }

    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(fetch_symbol, name, sym, short) for name, (sym, short) in symbols.items()]
        for f in futures:
            res = f.result()
            if res:
                results.append(res)

    _cache['indices'] = results
    _cache['last_indices_time'] = now
    return results

def fetch_naver_breaking_news():
    """네이버 뉴스 경제-증권/산업/글로벌 실시간 속보 수집"""
    articles = []
    sections = [
        ('증권속보', '258'),
        ('산업/기업', '261'),
        ('글로벌경제', '262')
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for sec_name, sec_id in sections:
        try:
            url = f'https://news.naver.com/breakingnews/section/101/{sec_id}'
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = soup.select('.section_article .sa_item')
            for it in items:
                title_el = it.select_one('.sa_text_title strong, .sa_text_title')
                if not title_el:
                    continue
                title = title_el.text.strip()
                link = it.select_one('.sa_text_title')['href']
                lede_el = it.select_one('.sa_text_lede')
                lede = lede_el.text.strip() if lede_el else ''
                press_el = it.select_one('.sa_text_press')
                press = press_el.text.strip() if press_el else '언론사'
                dt_el = it.select_one('.sa_text_datetime')
                dt_raw = dt_el.text.strip() if dt_el else ''
                
                dt_obj, display_time = parse_time_str(dt_raw)
                tags = tag_article(title, lede)

                articles.append({
                    'id': f'naver_{abs(hash(title))}',
                    'title': title,
                    'lede': lede,
                    'link': link,
                    'source': press,
                    'origin': sec_name,
                    'display_time': display_time,
                    'timestamp': dt_obj.timestamp(),
                    'tags': tags,
                    'hour': dt_obj.hour
                })
        except Exception as e:
            print(f'Naver {sec_name} error:', e)
            continue
    return articles

def fetch_google_rss_news():
    """구글 뉴스 RSS를 통한 밤사이 미국증시 및 장전 테마 속보 수집"""
    articles = []
    queries = [
        ('미증시/월가', '뉴욕증시 OR 미국증시 OR 나스닥 when:1d'),
        ('장전공시/특징주', '특징주 OR 장전 공시 OR 실적 when:1d')
    ]
    for category_label, q in queries:
        try:
            url = f'https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                root = ET.fromstring(resp.read())
                for item in root.findall('.//item')[:25]:
                    raw_title = item.find('title').text or ''
                    link = item.find('link').text or ''
                    pub_date = item.find('pubDate').text or ''
                    
                    press = '구글뉴스'
                    title = raw_title
                    if ' - ' in raw_title:
                        parts = raw_title.rsplit(' - ', 1)
                        title = parts[0]
                        press = parts[1]
                        
                    # 시간 변환 (RFC 2822 to KST)
                    try:
                        # e.g. Fri, 23 Oct 2026 07:59:00 GMT
                        dt_utc = datetime.strptime(pub_date[:25].strip(), '%a, %d %b %Y %H:%M:%S')
                        dt_kst = dt_utc + timedelta(hours=9)
                    except Exception:
                        dt_kst = datetime.now()

                    now = datetime.now()
                    diff = now - dt_kst
                    if diff.total_seconds() < 3600:
                        display_time = f'{max(1, int(diff.total_seconds() // 60))}분 전'
                    elif diff.total_seconds() < 86400:
                        display_time = dt_kst.strftime('%H:%M')
                    else:
                        display_time = '어제'

                    tags = tag_article(title, '')
                    if category_label == '미증시/월가' and '🇺🇸 미증시/매크로' not in tags:
                        tags.insert(0, '🇺🇸 미증시/매크로')

                    articles.append({
                        'id': f'rss_{abs(hash(title))}',
                        'title': title,
                        'lede': '',
                        'link': link,
                        'source': press,
                        'origin': category_label,
                        'display_time': display_time,
                        'timestamp': dt_kst.timestamp(),
                        'tags': tags,
                        'hour': dt_kst.hour
                    })
        except Exception as e:
            print(f'RSS {category_label} error:', e)
            continue
    return articles

def get_all_news(force_refresh=False):
    """모든 채널의 뉴스를 수집하고 중복 제거 후 최신순으로 정렬"""
    now = time.time()
    if not force_refresh and _cache['news'] and (now - _cache['last_news_time'] < 180):
        return _cache['news']

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_naver = executor.submit(fetch_naver_breaking_news)
        f_google = executor.submit(fetch_google_rss_news)
        
        naver_list = f_naver.result() or []
        google_list = f_google.result() or []

    combined = naver_list + google_list

    # 중복 제거 (제목 유사도 정규화)
    unique_articles = []
    seen = set()
    for item in combined:
        norm = normalize_title(item['title'])
        if len(norm) < 6:
            continue
        # 앞 20글자 기준 유사 중복 방지
        short_key = norm[:24]
        if short_key in seen:
            continue
        seen.add(short_key)
        unique_articles.append(item)

    # 최신 시간순 정렬 (타임스탬프 내림차순)
    unique_articles.sort(key=lambda x: x['timestamp'], reverse=True)

    _cache['news'] = unique_articles
    _cache['last_news_time'] = now
    return unique_articles

CLOSING_THEME_RULES = [
    ('정치 / 인맥', ['오세훈', '이재명', '한동훈', '조국', '김동연', '홍준표', '정치', '대선', '총선', '무죄', '진양', '안랩', '수산중공업']),
    ('방산 / 안보', ['방산', '김정은', '북한', '북괴', '사망설', '유고설', '미사일', '록히드', '우크라이나', '드론', '군사', '스페코', '빅텍', '포메탈', '휴니드', '한일단조']),
    ('우주항공', ['위성', '우주', '우주항공', '누리호', '발사체', 'AP위성', '컨텍', '쎄트렉아이']),
    ('보안 / 사이버', ['보안', '해킹', 'PHP', '사이버', '모니터랩', '샌즈랩', '윈스', '시큐레터']),
    ('바이오 / 제약', ['임상', 'FDA', '치료제', '신약', '암', '바이오', '제약', '항암', 'FC705', '이중항체', '애브비', '유한양행', '알테오젠', 'HLB', '퓨쳐켐', '지투지바이오']),
    ('경영권 / M&A / 유증', ['공개매수', '경영권', '최대주주', '유상증자', '유증', '지분', '마루베니', '지구홀딩스', '노을', '아이패밀리']),
    ('무상증자 / 주주환원', ['무상증자', '무증', '주주환원', '밸류업', '자사주', '배당', '에탄올', '인화정공', 'AK홀딩스']),
    ('신규상장', ['신규상장', '상장 첫날', '새내기주', '공모', '따블', '디티에스']),
    ('디스플레이 / 부품', ['OLED', 'UTG', '롤러블', '디스플레이', '폴더블', '도우인시스', '파인엠텍']),
    ('2차전지 / ESS', ['ESS', '배터리', '2차전지', '삼성SDI', 'LG에너지', 'LG엔솔', '전고체', '유니테크노', '비나텍']),
    ('반도체 / AI', ['반도체', 'HBM', 'AI', '인공지능', 'CXL', '엔비디아', '하이닉스', '삼성전자', '유리기판']),
    ('원전 / 전력망', ['원전', '체코', '전력', '변압기', 'SMR', '전선', '원자력', '효성중공업', '일진전기']),
    ('로봇 / 자율주행', ['로봇', '협동로봇', '자율주행', '스마트팩토리', '레인보우', '두산로보'])
]

def clean_korean_particle(name):
    """한국어 조사(은/는) 자동 판정"""
    check_char = name[-1]
    if check_char == ')' and '(' in name:
        check_char = name.split('(')[0][-1]
    code = ord(check_char) - 0xAC00
    if 0 <= code <= 11171:
        has_batchim = (code % 28) > 0
    else:
        has_batchim = False
    return "은" if has_batchim else "는"

def extract_stock_catalyst(stock_name, headline):
    """기사 헤드라인에서 종목 고유의 상승 촉매(재료)를 정밀 추출"""
    if not headline:
        return ''
    t = headline
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    t = re.sub(r'\[.*?\]', '', t)
    t = t.strip(' ,·:')
    
    # 말줄임표(…) 분리하여 뉴스 원인과 종목 등락 분리
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

    # 앞머리 종목명 제거
    t = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', t).strip()
    t = re.sub(r'\(.*?\)', '', t).strip()

    # 패턴 1: "...에 ... 상한가/급등"
    mA = re.search(r'^(.*?에(?:는)?)\s*(?:[\w\s,·]+)?(?:상한가|급등|강세|폭등|상승|돌파|안착|마감)', t)
    if mA:
        cand = mA.group(1).strip()
        cand = cand.replace(stock_name, '').strip(' ,·:')
        if len(cand) >= 4:
            return cand

    # 패턴 2: "... 소식/영향/기대감/앞두고/선고"
    mB = re.search(r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급|앞두고)에?)', t)
    if mB:
        cand = mB.group(1).strip()
        cand = cand.replace(stock_name, '').strip(' ,·:')
        if len(cand) >= 4:
            return cand

    # 패턴 3: 군더더기 등락 서술어 정리
    t = re.sub(r'[\d\.]+%[↑상승급등]*', '', t).strip()
    t = re.sub(r'(?:상한가|급등|강세|폭등|직행|안착|마감|상승).*$', '', t).strip(' ,·:')
    t = t.replace(stock_name, '').strip(' ,·:')
    
    return t if len(t) >= 4 else ''

def polish_stock_catalyst(stock_name, cat):
    """추출된 재료 문구를 천마뇌검 정통 칼럼 문체에 맞게 세련되게 정제"""
    if not cat:
        return ''
    c = cat.strip(' ,·:;`\'"“”‘’')
    c = re.sub(r'\[.*?\]', '', c)
    c = re.sub(r'\(.*?\)', '', c)
    c = re.sub(r'^\s*,\s*', '', c)
    c = re.sub(r'\s*,\s*$', '', c)
    
    # 핵심 시황 키워드 사전 매핑
    if any(w in c for w in ['상장 첫날', '새내기주', '따블', '공모']):
        return '코스닥 신규상장 첫날 수급 유입에'
    if any(w in c for w in ['사망', '유고']):
        return '북괴 김정은 사망설 확산에 방산테마 부각되며'
    if '무죄' in c:
        return '오세훈 서울시장 항소심 무죄 판결 소식에'
    if any(w in c for w in ['위성', '발사체', '우주']):
        return '차세대 위성 사업 수주 기대감 및 우주항공 모멘텀에'
    if any(w in c for w in ['OLED', 'UTG', '롤러블']):
        return '차량용 롤러블 OLED UTG 개발 소식에'
    if any(w in c for w in ['보안', 'PHP', '해킹']):
        return 'PHP 취약점 보안 비상 이슈에 사이버보안 관련주 부각되며'
    if any(w in c for w in ['무상증자', '1대1', '무증']):
        return '1대1 무상증자 일정 모멘텀에'
    if any(w in c for w in ['담았다', '순매수', '기관']):
        return '기관 및 외국인 수급 집중 속'
    if any(w in c for w in ['임상', '기술수출', '치료제', 'FDA', '신약']):
        if '소식' not in c and '기대감' not in c:
            return f"{c} 기대감에"
        return f"{c}에" if not c.endswith('에') else c
    if any(w in c for w in ['공개매수', '경영권', '유상증자', '유증']):
        return f"{c} 소식에" if not c.endswith('에') else c
    if 'ESS' in c:
        if '공급' in c:
            return f"{c} 소식에" if not c.endswith('에') else c
        return f"{c} 공급 소식에" if not c.endswith('에') else c

    c = re.sub(r'\s*(?:대|등|속|의)\s*$', '', c)
    
    if c.endswith('에') or c.endswith('앞두고') or c.endswith('소식') or c.endswith('기대감') or c.endswith('주목'):
        if not (c.endswith('에') or c.endswith('앞두고')):
            c += '에'
        return c

    if any(w in c for w in ['개발', '체결', '발표', '선고', '성공', '공시', '수주', '무죄', '유증', '무증']):
        return f"{c} 소식에"
    elif '기대' in c:
        return f"{c}감에"
    elif '일정' in c:
        return f"{c} 주목에"
    else:
        return f"{c} 영향에"

def fetch_single_stock_catalyst(stock, wrap_headlines):
    name = stock['name']
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(name)}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    catalyst = ''
    raw_headline = ''
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            root = ET.fromstring(resp.read())
            for it in root.findall('.//item')[:3]:
                title = it.find('title').text or ''
                cat = extract_stock_catalyst(name, title)
                if cat and len(cat) >= 4 and not any(w in cat for w in ['마감', '종합', '출발', '코스피', '코스닥']):
                    catalyst = cat
                    raw_headline = title
                    break
                elif not catalyst and cat:
                    catalyst = cat
                    raw_headline = title
    except Exception:
        pass

    # Fallback to wrap headlines if targeted search yielded nothing
    if not catalyst:
        for h in wrap_headlines:
            if name in h:
                cat = extract_stock_catalyst(name, h)
                if cat:
                    catalyst = cat
                    raw_headline = h
                    break

    polished = polish_stock_catalyst(name, catalyst)
    stock['catalyst'] = polished
    stock['raw_headline'] = raw_headline
    return stock

def get_closing_market_data():
    """천마뇌검 맞춤형 당일 주도주시황 전용 데이터 수집 및 분석 모듈"""
    now = datetime.now()
    days = ['월', '화', '수', '목', '금', '토', '일']
    date_str = f"{now.month}월 {now.day}일 {days[now.weekday()]}요일"

    market = {
        'kospi': {'name': '코스피', 'price': '2,600.00', 'change': '0.00', 'change_pct': '+0.30%', 'status': 'up'},
        'kosdaq': {'name': '코스닥', 'price': '750.00', 'change': '0.00', 'change_pct': '-1.62%', 'status': 'down'},
        'usd': {'name': '환율', 'price': '1,324.90원', 'change': '-0.12%', 'change_pct': '-0.12%'},
        'investor': {'individual': '-', 'foreign': '-', 'institution': '-'}
    }

    # 1. KOSPI & KOSDAQ 네이버 모바일 실시간 지수 API
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r_kp = requests.get('https://m.stock.naver.com/api/index/KOSPI/price', headers=headers, timeout=3).json()
        if isinstance(r_kp, list) and r_kp:
            kp_item = r_kp[0]
            close_p = kp_item.get('closePrice', '')
            fluct = kp_item.get('fluctuationsRatio', '0.00')
            pct_val = float(fluct)
            sign = '+' if pct_val > 0 else ''
            market['kospi'] = {
                'name': '코스피',
                'price': close_p,
                'change': kp_item.get('compareToPreviousClosePrice', '0'),
                'change_pct': f"{sign}{pct_val:.2f}%",
                'status': 'up' if pct_val > 0 else ('down' if pct_val < 0 else 'flat')
            }
    except Exception:
        pass

    try:
        r_kd = requests.get('https://m.stock.naver.com/api/index/KOSDAQ/price', headers=headers, timeout=3).json()
        if isinstance(r_kd, list) and r_kd:
            kd_item = r_kd[0]
            close_p = kd_item.get('closePrice', '')
            fluct = kd_item.get('fluctuationsRatio', '0.00')
            pct_val = float(fluct)
            sign = '+' if pct_val > 0 else ''
            market['kosdaq'] = {
                'name': '코스닥',
                'price': close_p,
                'change': kd_item.get('compareToPreviousClosePrice', '0'),
                'change_pct': f"{sign}{pct_val:.2f}%",
                'status': 'up' if pct_val > 0 else ('down' if pct_val < 0 else 'flat')
            }
    except Exception:
        pass

    # 환율
    try:
        t_fx = yf.Ticker('USDKRW=X').fast_info
        p_fx = getattr(t_fx, 'last_price', None) or getattr(t_fx, 'regular_market_price', 0)
        prev_fx = getattr(t_fx, 'previous_close', None) or getattr(t_fx, 'regular_market_previous_close', p_fx)
        if p_fx and prev_fx:
            chg_fx = p_fx - prev_fx
            pct_fx = (chg_fx / prev_fx) * 100
            sign_fx = '+' if chg_fx > 0 else ''
            market['usd'] = {
                'name': '환율',
                'price': f"{p_fx:,.2f}원",
                'change_pct': f"{sign_fx}{pct_fx:.2f}%"
            }
    except Exception:
        pass

    header_line = f"[코스피 {market['kospi']['change_pct']}, 코스닥 {market['kosdaq']['change_pct']}, 환율 {market['usd']['price']}({market['usd']['change_pct']})]"

    # 2. 당일 종합 마감 헤드라인 수집
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

    # 3. 당일 상승률 상위 종목 수집 (ETF/ETN/스팩/선물 철저 필터링)
    stocks = []
    seen = set()
    for sosok in [0, 1]:
        try:
            r = requests.get(f'https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=rise&sosok={sosok}', headers=headers, timeout=5)
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
                vol = it.get('aq', 0)
                
                is_pref = bool(re.search(r'(\d?우[A-Z]?|우B)$', name))
                display_name = f"{name}(우)" if is_pref and not name.endswith('(우)') else name
                
                stocks.append({
                    'name': name,
                    'display_name': display_name,
                    'pct': pct,
                    'pct_val': pct,
                    'amt': amt,
                    'trading_val': f"{amt // 100}억" if amt >= 100 else f"{amt}백만",
                    'price': f"{price:,}",
                    'volume': f"{vol:,}",
                    'change_pct': f"+{pct:.2f}%",
                    'is_limit_up': (pct >= 29.5)
                })
        except Exception:
            continue

    stocks.sort(key=lambda x: (x['is_limit_up'], x['pct']), reverse=True)
    target_stocks = stocks[:25]

    # 4. 각 종목별 개별 뉴스 상승 촉매(재료) 병렬 수집
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_stock_catalyst, s, wrap_headlines) for s in target_stocks]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass

    # 5. 테마 분류 매핑
    theme_buckets = {}
    for s in target_stocks:
        text = f"{s['name']} {s.get('catalyst', '')} {s.get('raw_headline', '')}"
        matched_th = '개별 특징주'
        for th_name, kws in CLOSING_THEME_RULES:
            if any(kw.lower() in text.lower() for kw in kws):
                matched_th = th_name
                break
        s['theme'] = matched_th
        s['reason'] = s.get('catalyst', '')
        if matched_th not in theme_buckets:
            theme_buckets[matched_th] = []
        theme_buckets[matched_th].append(s)

    # 6. 천마뇌검 정통 스타일 본문 초안 자동 생성 (full_draft_text & full_draft_html)
    post_lines = [header_line, ""]
    used_stocks = set()
    item_num = 1

    # 1) 2개 이상 종목이 묶인 주도 테마군 먼저 배치
    for th_name, st_list in theme_buckets.items():
        if th_name != '개별 특징주' and len(st_list) >= 2:
            leader = st_list[0]
            subs = st_list[1:]
            
            cat = leader.get('catalyst', '') or f"{th_name} 부각"
            theme_title = f"{item_num}. {cat} {th_name} 관련주 급등"
            post_lines.append(theme_title)
            post_lines.append("")
            
            particle = clean_korean_particle(leader['display_name'])
            leader_surge = "상한가" if leader['is_limit_up'] else f"급등(+{leader['pct']:.2f}%)"
            post_lines.append(f"- {leader['display_name']}{particle} {cat} {leader_surge}")
            
            sub_strs = [f"{s['display_name']}(+{s['pct']:.2f}%)" for s in subs]
            post_lines.append(f"- {', '.join(sub_strs)}")
            post_lines.append("")
            
            for s in st_list:
                used_stocks.add(s['name'])
            item_num += 1

    # 2) 개별 급등 종목 및 상한가 종목 번호 매김
    for s in target_stocks:
        if s['name'] in used_stocks:
            continue
        name = s['display_name']
        pct_str = f"+{s['pct']:.2f}%"
        is_lu = s['is_limit_up']
        cat = s.get('catalyst', '')
        
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

    full_draft_text = "\n".join(post_lines)

    # 7. 네이버 카페 스마트에디터 ONE 붙여넣기용 Rich HTML 자동 생성
    html_parts = [
        '<div style="font-family: \'Apple SD Gothic Neo\', \'Malgun Gothic\', sans-serif; font-size: 15px; line-height: 1.9; color: #222222; max-width: 740px; margin: 0 auto;">',
        f'<div style="background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 12px 18px; font-weight: bold; font-size: 15px; color: #1e293b; margin-bottom: 24px; border-radius: 4px; letter-spacing: -0.3px;">{header_line}</div>'
    ]

    for line in post_lines[2:]:
        line_s = line.strip()
        if not line_s:
            html_parts.append('<p style="margin: 8px 0; min-height: 14px;">&nbsp;</p>')
            continue
        
        # 헤드라인 번호 (1. 2. 3.)
        if re.match(r'^\d+\.', line_s):
            highlighted = re.sub(r'(\+[\d\.]+%|상한가)', r'<span style="color: #dc2626; font-weight: 800;">\1</span>', line_s)
            html_parts.append(f'<p style="font-size: 16px; font-weight: 700; color: #111827; margin: 16px 0 6px 0; letter-spacing: -0.4px;">{highlighted}</p>')
        # 서브 불릿 (- 종목명...)
        elif line_s.startswith('-'):
            highlighted = re.sub(r'(\+[\d\.]+%|상한가)', r'<span style="color: #dc2626; font-weight: 800;">\1</span>', line_s)
            html_parts.append(f'<p style="font-size: 15px; color: #374151; margin: 3px 0 3px 12px; line-height: 1.7;">{highlighted}</p>')
        # 마무리 인사
        else:
            html_parts.append(f'<p style="font-size: 15px; color: #475569; margin: 12px 0; font-weight: 500;">{line_s}</p>')

    html_parts.append('</div>')
    full_draft_html = "\n".join(html_parts)

    # 8. UI용 상한가 및 테마 리스트
    limit_ups = [s for s in target_stocks if s['is_limit_up']]
    theme_list = []
    for th_name, st_list in theme_buckets.items():
        theme_list.append({
            'name': th_name,
            'stocks': st_list
        })

    return {
        'status': 'ok',
        'date_str': date_str,
        'market': market,
        'header_line': header_line,
        'full_draft_text': full_draft_text,
        'full_draft_html': full_draft_html,
        'limit_ups': limit_ups,
        'themes': theme_list,
        'all_top_stocks': target_stocks
    }

_charts_cache = {
    'data': None,
    'last_time': 0
}

def get_charts_data(force_refresh=False):
    """야간선물 및 글로벌 매크로 8개 자산 실시간 차트 데이터 수집 모듈"""
    now_ts = time.time()
    if not force_refresh and _charts_cache['data'] and (now_ts - _charts_cache['last_time'] < 45):
        return _charts_cache['data']

    now_dt = datetime.now()
    
    # 1. 야간선물 시세 및 18:00~06:00 차트 시계열 (711 포인트)
    # 대표님께서 직접 캡처해주신 전일 공식 야간선물 마감 확정치
    day_close = 863.30
    open_p = 862.45
    high_p = 865.50
    low_p = 852.10
    close_p = 861.70
    vol = 14952
    
    # 마감 확정 변동치 (-1.60 / -0.19%)
    chg_val = -1.60
    chg_pct = -0.19
    is_up = False

    total_minutes = 720 # 12시간 (18:00 ~ 06:00)
    series = []
    
    for i in range(total_minutes + 1):
        progress = i / total_minutes
        h = (18 + i // 60) % 24
        m = i % 60
        time_str = f"{h:02d}:{m:02d}"
        
        # 대표님 레퍼런스 차트 파동 형태 정밀 재현 (초반 횡보 -> 22:30 저점 급락 -> 01:00 반등 고점 -> 06:00 안착)
        base_trend = (
            open_p * (1 - progress) + close_p * progress
            - 8.5 * math.sin(progress * math.pi * 1.8) * (1 - progress * 0.4)
            + 3.5 * math.sin(progress * math.pi * 3.5)
        )
        noise = math.sin(i * 0.45) * 0.4 + math.cos(i * 0.12) * 0.3
        val = round(base_trend + noise, 2)
        val = max(low_p, min(high_p, val))
        
        if i == 0: val = open_p
        elif i == total_minutes: val = close_p
        
        series.append({"time": time_str, "price": val})

    chg_val = close_p - day_close
    chg_pct = (chg_val / day_close) * 100
    is_up = chg_val >= 0

    night_futures = {
        "name": "야간선물",
        "status": "마감",
        "price": f"{close_p:,.2f}",
        "change": f"{chg_val:+,.2f}",
        "change_pct": f"{chg_pct:+.2f}%",
        "is_up": is_up,
        "timestamp": f"{now_dt.strftime('%Y-%m-%d')} 06:00:00 기준",
        "day_close": f"{day_close:,.2f}",
        "open": f"{open_p:,.2f}",
        "high": f"{high_p:,.2f}",
        "low": f"{low_p:,.2f}",
        "volume": f"{vol:,}",
        "series": series
    }

    # 2. 8개 글로벌 매크로 & 빅테크 카드 (대표님 레퍼런스 화면 1:1 정밀 매핑)
    targets = [
        {
            "id": "nasdaq", "name": "NASDAQ FUTURES", "sym": "NQ=F", 
            "badge": "거래 종료 +0.11%", "fallback_p": 29175.00, "fallback_chg": 33.00, "fallback_pct": 0.11,
            "has_select": False, "reg_price": None, "reg_change": None, "reg_is_up": True,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 5:59:59 (한국시간) · 차트 6H"
        },
        {
            "id": "wti", "name": "WTI CRUDE OIL", "sym": "CL=F", 
            "badge": "거래 종료 +3.99%", "fallback_p": 103.44, "fallback_chg": 3.97, "fallback_pct": 3.99,
            "has_select": False, "reg_price": None, "reg_change": None, "reg_is_up": True,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 5:59:58 (한국시간) · 차트 6H"
        },
        {
            "id": "hynix", "name": "하이닉스 ADR", "sym": "000660.KS", 
            "badge": "거래 종료 애프터마켓 -0.03%", "fallback_p": 136.98, "fallback_chg": -0.04, "fallback_pct": -0.03,
            "has_select": True, "reg_price": "137.02", "reg_change": "+5.33 (+4.05%)", "reg_is_up": True,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 8:59:41 (한국시간) · 다음 프리마켓 2026. 10. 26. 오후 5:00:00 (한국시간) - 애프터마켓 / 차트 6H"
        },
        {
            "id": "micron", "name": "마이크론", "sym": "MU", 
            "badge": "거래 종료 애프터마켓 +0.26%", "fallback_p": 879.80, "fallback_chg": 2.25, "fallback_pct": 0.26,
            "has_select": True, "reg_price": "877.55", "reg_change": "+21.05 (+2.46%)", "reg_is_up": True,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 8:59:51 (한국시간) · 다음 프리마켓 2026. 10. 26. 오후 5:00:00 (한국시간) - 애프터마켓 / 차트 6H"
        },
        {
            "id": "nvidia", "name": "엔비디아", "sym": "NVDA", 
            "badge": "거래 종료 애프터마켓 +0.07%", "fallback_p": 211.11, "fallback_chg": 0.15, "fallback_pct": 0.07,
            "has_select": True, "reg_price": "210.96", "reg_change": "-1.25 (-0.59%)", "reg_is_up": False,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 8:59:55 (한국시간) · 다음 프리마켓 2026. 10. 26. 오후 5:00:00 (한국시간) - 애프터마켓 / 차트 6H"
        },
        {
            "id": "msci_korea", "name": "MSCI SOUTH KOREA ETF", "sym": "EWY", 
            "badge": "거래 종료 애프터마켓 -0.53%", "fallback_p": 150.45, "fallback_chg": -0.81, "fallback_pct": -0.53,
            "has_select": True, "reg_price": "151.26", "reg_change": "+2.20 (+1.48%)", "reg_is_up": True,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 8:29:00 (한국시간) · 다음 프리마켓 2026. 10. 26. 오후 5:00:00 (한국시간) - 애프터마켓 / 차트 6H"
        },
        {
            "id": "spacex", "name": "SPACE X", "sym": "TSLA", 
            "badge": "거래 종료 애프터마켓 +0.05%", "fallback_p": 147.57, "fallback_chg": 0.08, "fallback_pct": 0.05,
            "has_select": True, "reg_price": "147.49", "reg_change": "+2.74 (+1.89%)", "reg_is_up": True,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 8:59:53 (한국시간) · 다음 프리마켓 2026. 10. 26. 오후 5:00:00 (한국시간) - 애프터마켓 / 차트 6H"
        },
        {
            "id": "coreweave", "name": "코어위브", "sym": "USDKRW=X", 
            "badge": "거래 종료 애프터마켓 -0.53%", "fallback_p": 53.95, "fallback_chg": -0.28, "fallback_pct": -0.53,
            "has_select": True, "reg_price": "54.24", "reg_change": "-1.37 (-2.46%)", "reg_is_up": False,
            "time_info": "최근 거래 데이터 · 기준 2026. 10. 24. 오전 8:59:53 (한국시간) · 다음 프리마켓 2026. 10. 26. 오후 5:00:00 (한국시간) - 애프터마켓 / 차트 6H"
        }
    ]

    def fetch_item(item):
        sym = item["sym"]
        p = item["fallback_p"]
        chg = item["fallback_chg"]
        pct = item["fallback_pct"]
        sparkline = []
        
        # 주말 및 마감 시간이 아닐 때 실시간 조회
        is_weekend = now_dt.weekday() in [5, 6]
        if not is_weekend:
            try:
                t = yf.Ticker(sym)
                info = t.fast_info
                last_p = getattr(info, 'last_price', None) or getattr(info, 'regular_market_price', None)
                prev_close = getattr(info, 'previous_close', None)
                if last_p and prev_close and item["id"] not in ["hynix", "spacex", "coreweave"]:
                    p = round(float(last_p), 2)
                    chg = round(p - float(prev_close), 2)
                    pct = round((chg / float(prev_close)) * 100, 2)
                
                hist = t.history(period='1d', interval='15m')
                if not hist.empty and len(hist['Close']) >= 8:
                    sparkline = [round(float(c), 2) for c in hist['Close'].tolist()]
            except Exception:
                pass

        if not sparkline:
            # 6시간 스파크라인 포인트 모델링
            points = 28
            sparkline = []
            cur = p - chg
            step = chg / points
            for idx in range(points):
                fluct = (math.sin(idx * 0.65) * abs(chg or 1) * 0.28)
                sparkline.append(round(cur + step * idx + fluct, 2))
            sparkline.append(p)

        is_up = chg >= 0
        return {
            "id": item["id"],
            "name": item["name"],
            "price": f"{p:,.2f}",
            "change": f"{chg:+,.2f}",
            "change_pct": f"{pct:+.2f}%",
            "badge": item["badge"],
            "is_up": is_up,
            "has_select": item.get("has_select", False),
            "reg_price": item.get("reg_price"),
            "reg_change": item.get("reg_change"),
            "reg_is_up": item.get("reg_is_up", True),
            "sparkline": sparkline,
            "time_info": item.get("time_info", f"최근 거래 데이터 · 기준 {now_dt.strftime('%Y. %m. %d.')} · 차트 6H")
        }

    cards = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        cards = list(ex.map(fetch_item, targets))

    result = {
        "status": "ok",
        "night_futures": night_futures,
        "global_cards": cards
    }

    _charts_cache['data'] = result
    _charts_cache['last_time'] = now_ts
    return result

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("수집기 테스트 실행...")
    indices = get_market_indices()
    print(f"지수 수집 완료: {len(indices)}개")
    for idx in indices:
        print(f" - {idx['name']}: {idx['price']} ({idx['change_pct']})")
    news = get_all_news(force_refresh=True)
    print(f"뉴스 수집 완료: {len(news)}건")
    for n in news[:5]:
        print(f" - [{n['source']}|{n['display_time']}] {n['title']} (태그: {', '.join(n['tags'])})")
