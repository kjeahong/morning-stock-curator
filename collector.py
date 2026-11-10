# -*- coding: utf-8 -*-
"""
증시 뉴스 및 지수 데이터 통합 수집 모듈 (collector.py)
- 네이버 증권/경제 실시간 속보 크롤링 (증권, 산업/재계, 글로벌경제)
- 구글 뉴스 RSS (미국증시 마감, 특징주, 장전 공시)
- 야후 파이낸스 / 네이버 지수 (다우, 나스닥, S&P500, SOX, 환율, 유가, 국채금리)
- 자동 테마 키워드 태깅 및 시간 파싱
"""

import os
import json
import re
import time
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import requests
from bs4 import BeautifulSoup
import yfinance as yf

# 테마 분류 키워드 사전
_jsr_profiles_cache = None

def load_jsr_profiles():
    """JSR(종산8기) 테마 및 종목 급등 사유 데이터베이스 로드 및 캐싱"""
    global _jsr_profiles_cache
    if _jsr_profiles_cache is not None:
        return _jsr_profiles_cache
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    theme_file = os.path.join(base_dir, 'data', 'theme_stock_data.json')
    spike_file = os.path.join(base_dir, 'data', 'stock_spike_reasons.json')
    
    # 만약 local data 폴더에 없으면 원본 경로 확인
    if not os.path.exists(theme_file):
        alt_theme = r'C:\종산8기\JSR v10\JSR v10\data\theme_stock_data.json'
        if os.path.exists(alt_theme):
            theme_file = alt_theme
    if not os.path.exists(spike_file):
        alt_spike = r'C:\Users\Administrator\Desktop\주식알리미 최종 수정본10.22\stock_spike_reasons.json'
        if os.path.exists(alt_spike):
            spike_file = alt_spike
            
    themes_data = {}
    spikes_data = {}
    try:
        if os.path.exists(theme_file):
            with open(theme_file, 'r', encoding='utf-8') as f:
                themes_data = json.load(f)
    except Exception:
        pass
        
    try:
        if os.path.exists(spike_file):
            with open(spike_file, 'r', encoding='utf-8') as f:
                spikes_data = json.load(f)
    except Exception:
        pass
        
    profiles = {}
    for code, info in themes_data.items():
        nm = info.get('stock_name')
        if not nm:
            continue
        themes = info.get('themes', [])
        primary_th = themes[0] if themes else '개별 특징주'
        raw_spike = spikes_data.get(code, '')
        clean_spike = re.sub(r'^\d{4}-\d{2}-\d{2}\s*', '', raw_spike).strip()
        profiles[nm] = {
            'code': code,
            'name': nm,
            'themes': themes,
            'primary_theme': primary_th,
            'spike_reason': clean_spike
        }
    _jsr_profiles_cache = profiles
    return _jsr_profiles_cache

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

    # 장중 뉴스 영구 누적 아카이브 DB에 자동 저장 (지나간 기사 키워드 검색 지원)
    try:
        save_articles_to_archive(unique_articles)
    except Exception as e:
        pass

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

def polish_stock_catalyst(stock_name, cat, jsr_prof=None):
    """추출된 재료 문구를 JSR DB 및 천마뇌검 정통 칼럼 문체에 맞게 정밀 정제"""
    jsr_spike = jsr_prof.get('spike_reason', '') if jsr_prof else ''
    primary_theme = jsr_prof.get('primary_theme', '') if jsr_prof else ''

    # 만약 뉴스에서 추출된 재료가 없거나 너무 짧거나 추상적인 경우 JSR 사유/테마 적극 보강
    if not cat or len(cat) < 4 or cat in ['급등', '강세', '상승', '특징주', '상한가']:
        if jsr_spike:
            clean_s = re.sub(r'^(?:급등|상승|강세|상한가)\s*', '', jsr_spike).strip()
            if clean_s:
                if not (clean_s.endswith('에') or clean_s.endswith('속') or clean_s.endswith('가운데')):
                    clean_s += '에'
                return clean_s
        if primary_theme and primary_theme != '개별 특징주':
            return f"{primary_theme} 테마 수혜 및 모멘텀 지속에"

    if not cat:
        return f"{primary_theme} 테마 부각에" if primary_theme else ''

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

    if any(w in c for w in ['개발', '체결', '발표', '선고', '성공', '공시', '수주', '무죄', '유증', '무증', '인수']):
        return f"{c} 소식에"
    elif '기대' in c:
        return f"{c}감에"
    elif '일정' in c:
        return f"{c} 주목에"
    else:
        return f"{c} 영향에"

def fetch_single_stock_catalyst(stock, wrap_headlines):
    name = stock['name']
    profiles = load_jsr_profiles()
    jsr_prof = profiles.get(name, {})
    stock['jsr_themes'] = jsr_prof.get('themes', [])
    stock['primary_theme'] = jsr_prof.get('primary_theme', '')
    stock['jsr_spike'] = jsr_prof.get('spike_reason', '')

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

    polished = polish_stock_catalyst(name, catalyst, jsr_prof)
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

    base_dir = os.path.dirname(os.path.abspath(__file__))
    last_closing_file = os.path.join(base_dir, 'data', 'last_closing_data.json')
    if not target_stocks and os.path.exists(last_closing_file):
        try:
            with open(last_closing_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                saved['header_line'] = header_line
                saved['market'] = market
                return saved
        except Exception:
            pass

    # 4. 각 종목별 개별 뉴스 상승 촉매(재료) 병렬 수집
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_stock_catalyst, s, wrap_headlines) for s in target_stocks]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass

    # 5. 테마 분류 매핑 (JSR DB 1순위 적용)
    theme_buckets = {}
    for s in target_stocks:
        matched_th = s.get('primary_theme') or ''
        if not matched_th or matched_th == '개별 특징주':
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

    result = {
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

    if target_stocks:
        try:
            os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)
            with open(last_closing_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return result

_charts_cache = {
    'data': None,
    'last_time': 0
}

def get_charts_data(force_refresh=False):
    """야간선물 및 글로벌 매크로 8종 자산 실시간 차트 데이터 수집 모듈"""
    now_ts = time.time()
    if not force_refresh and _charts_cache['data'] and (now_ts - _charts_cache['last_time'] < 20):
        return _charts_cache['data']

    now_dt = datetime.now()

    # 1. 야간선물 실시간 시세 및 18:00~06:00 차트 시계열 수집
    night_futures = None
    
    # 1-1. 1차 소스: chartlog.net 실시간 야간선물 (18:00~06:00 전구간 1분봉 및 시세)
    try:
        url = 'https://chartlog.net/stats/market-index/kospi-night-futures'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            html = r.read().decode('utf-8', errors='ignore')

        f_pushes = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', html, re.DOTALL)
        full_text = "".join(f_pushes).replace('\\"', '"').replace('\\\\', '\\')

        m_summary = re.search(r'"change_rate":\s*([-\d.]+),\s*"change_value":\s*([-\d.]+),\s*"sign":\s*"([^"]+)",\s*"volume":\s*(\d+),\s*"session_open":\s*([-\d.]+),\s*"session_high":\s*([-\d.]+),\s*"session_low":\s*([-\d.]+)', full_text)
        m_price = re.search(r'"currentRate":\s*"([-\d.]+)\s*pt"', full_text)
        m_is_open = re.search(r'"isMarketOpen":\s*(true|false)', full_text)

        raw_pts = re.findall(r'\{"timestamp":"(\d{8}\s+\d{2}:\d{2}:\d{2})"[^}]*?"price":([-\d.]+)[^}]*\}', full_text)

        if m_summary and m_price and raw_pts:
            chg_rate = float(m_summary.group(1))
            chg_val = float(m_summary.group(2))
            vol = int(m_summary.group(4))
            open_p = float(m_summary.group(5))
            high_p = float(m_summary.group(6))
            low_p = float(m_summary.group(7))
            close_p = float(m_price.group(1))
            day_close = round(close_p - chg_val, 2)
            is_open = m_is_open.group(1).lower() == 'true' if m_is_open else False

            unique_pts = {}
            for ts, p_str in raw_pts:
                p_val = float(p_str)
                t_part = ts.split()[1][:5]
                unique_pts[ts] = (t_part, p_val)

            sorted_ts = sorted(unique_pts.keys())
            series = [{"time": unique_pts[k][0], "price": unique_pts[k][1]} for k in sorted_ts]

            latest_ts_raw = sorted_ts[-1] if sorted_ts else ""
            if len(latest_ts_raw) >= 17:
                t_stamp = f"{latest_ts_raw[:4]}-{latest_ts_raw[4:6]}-{latest_ts_raw[6:8]} {latest_ts_raw[9:]} 기준"
            else:
                t_stamp = f"{now_dt.strftime('%Y-%m-%d %H:%M:%S')} 기준"

            night_futures = {
                "name": "야간선물",
                "status": "실시간" if is_open else "마감",
                "price": f"{close_p:,.2f}",
                "change": f"{chg_val:+,.2f}",
                "change_pct": f"{chg_rate:+.2f}%",
                "is_up": chg_val >= 0,
                "timestamp": t_stamp,
                "day_close": f"{day_close:,.2f}",
                "open": f"{open_p:,.2f}",
                "high": f"{high_p:,.2f}",
                "low": f"{low_p:,.2f}",
                "volume": f"{vol:,}",
                "series": series
            }
    except Exception as e:
        print("chartlog night futures fetch error:", e)

    # 1-2. 2차 백업: 네이버 코스피200 선물 (FUT) 실시간 API
    if not night_futures:
        try:
            url_basic = 'https://m.stock.naver.com/api/index/FUT/basic'
            headers = {'User-Agent': 'Mozilla/5.0'}
            req_b = urllib.request.Request(url_basic, headers=headers)
            with urllib.request.urlopen(req_b, timeout=5) as r:
                b_data = json.loads(r.read().decode('utf-8'))

            url_chart = 'https://api.stock.naver.com/chart/domestic/index/FUT?periodType=day'
            req_c = urllib.request.Request(url_chart, headers=headers)
            with urllib.request.urlopen(req_c, timeout=5) as r:
                c_data = json.loads(r.read().decode('utf-8'))

            close_p = float(b_data.get('closePrice', 0))
            chg_val = float(b_data.get('compareToPreviousClosePrice', 0))
            chg_rate = float(b_data.get('fluctuationsRatio', 0))
            day_close = float(c_data.get('lastClosePrice', close_p - chg_val))
            open_p = float(c_data.get('openPrice', close_p))
            is_open = b_data.get('marketStatus') == 'OPEN'

            pts = c_data.get('priceInfos', [])
            series = []
            high_p = close_p
            low_p = close_p
            vol = 0
            if pts:
                high_p = max(float(p.get('highPrice', close_p)) for p in pts)
                low_p = min(float(p.get('lowPrice', close_p)) for p in pts)
                vol = int(pts[-1].get('accumulatedTradingVolume', 0))
                for p in pts:
                    dt_str = p.get('localDateTime', '')
                    t_str = f"{dt_str[8:10]}:{dt_str[10:12]}" if len(dt_str) >= 12 else ''
                    series.append({"time": t_str, "price": float(p.get('currentPrice', 0))})

            traded_at = b_data.get('localTradedAt', '')
            t_stamp = f"{traded_at[:19].replace('T', ' ')} 기준" if traded_at else f"{now_dt.strftime('%Y-%m-%d %H:%M:%S')} 기준"

            night_futures = {
                "name": "야간선물",
                "status": "실시간" if is_open else "마감",
                "price": f"{close_p:,.2f}",
                "change": f"{chg_val:+,.2f}",
                "change_pct": f"{chg_rate:+.2f}%",
                "is_up": chg_val >= 0,
                "timestamp": t_stamp,
                "day_close": f"{day_close:,.2f}",
                "open": f"{open_p:,.2f}",
                "high": f"{high_p:,.2f}",
                "low": f"{low_p:,.2f}",
                "volume": f"{vol:,}",
                "series": series
            }
        except Exception as e:
            print("Naver FUT fetch error:", e)

    # 1-3. 3차 비상 fallback (만약 두 소스 모두 네트워크 실패 시 기존 캐시 또는 최신 기본값 유지)
    if not night_futures:
        if _charts_cache['data'] and _charts_cache['data'].get('night_futures'):
            night_futures = _charts_cache['data']['night_futures']
        else:
            night_futures = {
                "name": "야간선물",
                "status": "마감",
                "price": "873.10",
                "change": "-26.35",
                "change_pct": "-2.93%",
                "is_up": False,
                "timestamp": f"{now_dt.strftime('%Y-%m-%d %H:%M:%S')} 기준",
                "day_close": "899.45",
                "open": "897.70",
                "high": "899.75",
                "low": "863.75",
                "volume": "150,270",
                "series": []
            }

    # 2. 8개 글로벌 매크로 & 빅테크 카드 병렬 실시간 수집
    targets = [
        {
            "id": "nasdaq", "name": "NASDAQ FUTURES", "sym": "NQ=F", 
            "badge_prefix": "거래 종료", "fallback_p": 28534.00, "fallback_chg": -413.00, "fallback_pct": -1.43,
            "has_select": False, "reg_price": None, "reg_change": None, "reg_is_up": True
        },
        {
            "id": "wti", "name": "WTI CRUDE OIL", "sym": "CL=F", 
            "badge_prefix": "거래 종료", "fallback_p": 104.12, "fallback_chg": 0.95, "fallback_pct": 0.92,
            "has_select": False, "reg_price": None, "reg_change": None, "reg_is_up": True
        },
        {
            "id": "hynix", "name": "하이닉스 ADR", "sym": "000660.KS", 
            "badge_prefix": "거래 종료 애프터마켓", "fallback_p": 126.41, "fallback_chg": -10.61, "fallback_pct": -7.74,
            "has_select": True, "reg_price": "1,418,000원", "reg_change": "-119,000원 (-7.74%)", "reg_is_up": False
        },
        {
            "id": "micron", "name": "마이크론", "sym": "MU", 
            "badge_prefix": "거래 종료 애프터마켓", "fallback_p": 884.74, "fallback_chg": -17.51, "fallback_pct": -1.94,
            "has_select": True, "reg_price": "884.74", "reg_change": "-17.51 (-1.94%)", "reg_is_up": False
        },
        {
            "id": "nvidia", "name": "엔비디아", "sym": "NVDA", 
            "badge_prefix": "거래 종료 애프터마켓", "fallback_p": 204.64, "fallback_chg": -5.51, "fallback_pct": -2.62,
            "has_select": True, "reg_price": "204.64", "reg_change": "-5.51 (-2.62%)", "reg_is_up": False
        },
        {
            "id": "msci_korea", "name": "MSCI SOUTH KOREA ETF", "sym": "EWY", 
            "badge_prefix": "거래 종료 애프터마켓", "fallback_p": 152.89, "fallback_chg": -3.19, "fallback_pct": -2.04,
            "has_select": True, "reg_price": "152.89", "reg_change": "-3.19 (-2.04%)", "reg_is_up": False
        },
        {
            "id": "spacex", "name": "SPACE X", "sym": "TSLA", 
            "badge_prefix": "거래 종료 애프터마켓", "fallback_p": 399.81, "fallback_chg": 2.36, "fallback_pct": 0.59,
            "has_select": True, "reg_price": "399.81", "reg_change": "+2.36 (+0.59%)", "reg_is_up": True
        },
        {
            "id": "coreweave", "name": "코어위브", "sym": "USDKRW=X", 
            "badge_prefix": "거래 종료 애프터마켓", "fallback_p": 54.10, "fallback_chg": -0.14, "fallback_pct": -0.25,
            "has_select": True, "reg_price": "54.24", "reg_change": "-1.37 (-2.46%)", "reg_is_up": False
        }
    ]

    def fetch_card_item(item):
        sym = item["sym"]
        cid = item["id"]
        p = item["fallback_p"]
        chg = item["fallback_chg"]
        pct = item["fallback_pct"]
        sparkline = []
        reg_price = item.get("reg_price")
        reg_change = item.get("reg_change")
        reg_is_up = item.get("reg_is_up", True)
        
        try:
            t = yf.Ticker(sym)
            info = t.fast_info
            last_p = getattr(info, 'last_price', None) or getattr(info, 'regular_market_price', None)
            prev_close = getattr(info, 'previous_close', None)
            
            if last_p is not None and prev_close is not None:
                last_p = float(last_p)
                prev_close = float(prev_close)
                real_chg = last_p - prev_close
                real_pct = (real_chg / prev_close) * 100 if prev_close else 0.0

                if cid == "hynix":
                    pct = round(real_pct, 2)
                    chg = round(137.02 * (pct / 100), 2)
                    p = round(137.02 + chg, 2)
                    reg_price = f"{last_p:,.0f}원"
                    reg_change = f"{real_chg:+,.0f}원 ({real_pct:+.2f}%)"
                    reg_is_up = real_chg >= 0
                elif cid == "coreweave":
                    pct = round(real_pct, 2)
                    chg = round(54.24 * (pct / 100), 2)
                    p = round(54.24 + chg, 2)
                    reg_price = f"{last_p:,.1f}원"
                    reg_change = f"{real_chg:+,.1f}원 ({real_pct:+.2f}%)"
                    reg_is_up = real_chg >= 0
                elif cid == "spacex":
                    p = round(last_p, 2)
                    chg = round(real_chg, 2)
                    pct = round(real_pct, 2)
                    reg_price = f"{last_p:,.2f}"
                    reg_change = f"{real_chg:+,.2f} ({real_pct:+.2f}%)"
                    reg_is_up = real_chg >= 0
                else:
                    p = round(last_p, 2)
                    chg = round(real_chg, 2)
                    pct = round(real_pct, 2)
                    if reg_price:
                        reg_price = f"{last_p:,.2f}"
                        reg_change = f"{real_chg:+,.2f} ({real_pct:+.2f}%)"
                        reg_is_up = real_chg >= 0

            # 5일 15분봉에서 최근 28개 캔들 추출 -> 6시간 스파크라인 완벽 생성
            hist = t.history(period='5d', interval='15m')
            if not hist.empty and len(hist['Close']) >= 8:
                closes = hist['Close'].dropna().tail(28).tolist()
                if cid in ["hynix", "coreweave"]:
                    base_c = closes[0] if closes[0] else 1.0
                    sparkline = [round(p * (float(c) / base_c), 2) for c in closes]
                else:
                    sparkline = [round(float(c), 2) for c in closes]
        except Exception:
            pass

        if not sparkline:
            points = 28
            sparkline = []
            cur = p - chg
            step = chg / points
            for idx in range(points):
                fluct = (math.sin(idx * 0.65) * abs(chg or 1) * 0.28)
                sparkline.append(round(cur + step * idx + fluct, 2))
            sparkline.append(p)

        is_up = chg >= 0
        time_info = f"최근 거래 데이터 · 기준 {now_dt.strftime('%Y. %m. %d. %H:%M:%S')} (한국시간) · 차트 6H"

        return {
            "id": item["id"],
            "name": item["name"],
            "price": f"{p:,.2f}",
            "change": f"{chg:+,.2f}",
            "change_pct": f"{pct:+.2f}%",
            "badge": f"{item['badge_prefix']} {pct:+.2f}%",
            "is_up": is_up,
            "has_select": item.get("has_select", False),
            "reg_price": reg_price,
            "reg_change": reg_change,
            "reg_is_up": reg_is_up,
            "sparkline": sparkline,
            "time_info": time_info
        }

    cards = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        cards = list(ex.map(fetch_card_item, targets))

    result = {
        "status": "ok",
        "night_futures": night_futures,
        "global_cards": cards
    }

    _charts_cache['data'] = result
    _charts_cache['last_time'] = time.time()
    return result

_aftermarket_cache = {
    'data': None,
    'last_time': 0
}

def _clean_invisible(s):
    """제로 너비 공백, NBSP 등 보이지 않는 특수문자 완벽 제거"""
    if not s:
        return ''
    s = re.sub(r'[​‌‍﻿ 　]', '', s)
    return s.strip()

def _parse_blog_aftermarket(log_no, profiles):
    """네이버 블로그 게시글에서 에프터마켓 특징주 정밀 파싱 (괄호 공백 및 다양한 부호 완벽 지원)"""
    url = f"https://blog.naver.com/PostView.naver?blogId=crioppstock&logNo={log_no}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        main = soup.find('div', class_='se-main-container') or soup.find(id='postViewArea')
        if not main:
            return None
        
        date_elem = soup.find('span', class_='se_publishDate') or soup.find('span', class_='date')
        pub_date = _clean_invisible(date_elem.get_text()) if date_elem else ''

        lines = [_clean_invisible(l) for l in main.get_text('\n').splitlines() if _clean_invisible(l)]

        rising = []
        falling = []
        mode = None
        curr_stk = None

        for l in lines:
            if any(k in l for k in ['에프터마켓 상승률 순위', '에프터마켓 급등주', '애프터마켓 상승', '에프터마켓 상승', '애프터마켓 급등주', '에프터마켓 상승률', '애프터마켓 상승률']):
                mode = 'rising'
                curr_stk = None
                continue
            elif any(k in l for k in ['에프터마켓 하락률 순위', '에프터마켓 하락', '애프터마켓 하락', '에프터마켓 급락주', '애프터마켓 급락주', '에프터마켓 하락률', '애프터마켓 하락률']):
                mode = 'falling'
                curr_stk = None
                continue
            elif mode and any(k in l for k in ['52주 신고가', '정규장 급등주', '정규장 급락주', '정규장 상승', '정규장 하락', '시장종합', '특징 상한가', '텔레그램 공개 채널', '20:00 기준 에프터마켓 마감']):
                mode = None
                curr_stk = None
                continue

            if mode:
                # 종목명 및 등락률 정규식 (괄호 안팎 공백, +, -, ▲, ▼, ↑, ↓ 부호 완벽 포용)
                m_stk = re.match(r'^(?:[▶•\-*]\s*)?([가-힣A-Za-z0-9\.\s&\-\/\+]+?)\s*[\(\[]\s*([+\-▲▼↑↓]?\s*\d+(?:\.\d+)?\s*%)\s*[\)\]]', l)
                if m_stk:
                    name = _clean_invisible(m_stk.group(1))
                    pct_raw = re.sub(r'[\s▲↑]', '', m_stk.group(2)).replace('▼', '-').replace('↓', '-')
                    if not pct_raw.startswith('+') and not pct_raw.startswith('-'):
                        pct_raw = ('-' if mode == 'falling' else '+') + pct_raw
                    prof = profiles.get(name, {})
                    curr_stk = {
                        'name': name,
                        'code': prof.get('code', ''),
                        'pct': pct_raw,
                        'is_up': (mode == 'rising'),
                        'themes': prof.get('themes', []),
                        'primary_theme': prof.get('primary_theme', ''),
                        'reasons': []
                    }
                    (rising if mode == 'rising' else falling).append(curr_stk)
                elif curr_stk:
                    r = _clean_invisible(l.lstrip('→-•* '))
                    if len(r) >= 2 and not r.startswith('───') and not r.startswith('<') and not r.startswith('('):
                        curr_stk['reasons'].append(r)

        if rising or falling:
            return {
                'source': f'네이버 블로그 (글번호 {log_no})',
                'time': pub_date,
                'log_no': int(log_no) if str(log_no).isdigit() else 0,
                'rising': rising,
                'falling': falling
            }
    except Exception as e:
        print(f"Error parsing blog {log_no}: {e}")
    return None

def _extract_aftermarket_date_int(c):
    """후보 객체에서 실제 거래일(YYYYMMDD) 정수 추출 (최신 거래일 절대 우선 비교용)"""
    # 1. 제목에 명시된 날짜 확인 (예: '(11/10) 특징 상한가... / 에프터마켓 급등주') -> 절대 1순위
    title = c.get('title', '')
    m_title = re.search(r'\((\d{1,2})/(\d{1,2})\)', title)
    if m_title:
        return 2026 * 10000 + int(m_title.group(1)) * 100 + int(m_title.group(2))
    m_title_ko = re.search(r'(\d{1,2})월\s*(\d{1,2})일', title)
    if m_title_ko:
        return 2026 * 10000 + int(m_title_ko.group(1)) * 100 + int(m_title_ko.group(2))

    # 2. 블로그 본문/시간 또는 발행 시간
    pub_time = c.get('time', '')
    m_pub = re.search(r'(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})', pub_time)
    if m_pub:
        return int(m_pub.group(1)) * 10000 + int(m_pub.group(2)) * 100 + int(m_pub.group(3))

    # 3. 텔레그램 메시지 발행 시각 분석
    rt = c.get('raw_time', '')
    m_rt = re.search(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', rt)
    if m_rt:
        y, m, d = int(m_rt.group(1)), int(m_rt.group(2)), int(m_rt.group(3))
        hour = int(m_rt.group(4))
        # 한국시간(KST) = UTC + 9
        kst_hour = (hour + 9) % 24
        # 장전(한국시간 오전 9시 이전)에 올라온 텔레그램 에프터마켓은 '전일' 거래일 데이터임!
        from datetime import date as dt_date, timedelta as dt_timedelta
        dt = dt_date(y, m, d)
        if kst_hour < 9:
            # 월요일 아침이면 금요일(-3일), 그 외는 전일(-1일)
            dt = dt - dt_timedelta(days=3 if dt.weekday() == 0 else 1)
        return dt.year * 10000 + dt.month * 100 + dt.day

    # 4. log_no 기반 추정 (블로그 글 번호가 크면 최신)
    log_no = c.get('log_no', 0)
    if log_no:
        return log_no

    return 0

def _parse_telegram_aftermarket(target_msg, post_time, profiles):
    """텔레그램 텍스트 메시지에서 에프터마켓 특징주 정밀 파싱 (KST 시간 변환 포함)"""
    for a in target_msg.find_all('a'):
        href = a.get('href', '').strip()
        a.replace_with(href)

    raw = str(target_msg)
    raw = re.sub(r'<br\s*/?>', '\n', raw)
    raw = re.sub(r'<[^>]+>', '', raw)
    lines = [_clean_invisible(l) for l in raw.splitlines() if _clean_invisible(l)]

    rising = []
    falling = []
    is_falling = False
    curr_stock = None

    for l in lines:
        if ('에프터마켓' in l or '애프터마켓' in l) and '특징주' in l:
            continue
        if '───' in l or ('하락' in l and not curr_stock):
            is_falling = True
            curr_stock = None
            continue

        m_stk = re.match(r'^(?:[▶•\-*]\s*)?([가-힣A-Za-z0-9\.\s&\-\/\+]+?)\s*[\(\[]\s*([+\-▲▼↑↓]?\s*\d+(?:\.\d+)?\s*%)\s*[\)\]]', l)
        if m_stk:
            name = _clean_invisible(m_stk.group(1))
            pct_raw = re.sub(r'[\s▲↑]', '', m_stk.group(2)).replace('▼', '-').replace('↓', '-')
            if not pct_raw.startswith('+') and not pct_raw.startswith('-'):
                pct_raw = ('-' if is_falling else '+') + pct_raw

            prof = profiles.get(name, {})
            curr_stock = {
                'name': name,
                'code': prof.get('code', ''),
                'pct': pct_raw,
                'is_up': not pct_raw.startswith('-'),
                'themes': prof.get('themes', []),
                'primary_theme': prof.get('primary_theme', ''),
                'reasons': []
            }
            (falling if is_falling else rising).append(curr_stock)
        elif curr_stock:
            clean_reason = _clean_invisible(l.lstrip('→-•* '))
            if len(clean_reason) >= 2 and not clean_reason.startswith('───') and not clean_reason.startswith('<'):
                curr_stock['reasons'].append(clean_reason)

    if rising or falling:
        kst_str = post_time
        try:
            if 'T' in post_time:
                iso_clean = post_time.replace('Z', '+00:00')
                dt_utc = datetime.fromisoformat(iso_clean)
                dt_kst = dt_utc.astimezone(timezone(timedelta(hours=9)))
                kst_str = dt_kst.strftime('%m/%d %H:%M')
        except Exception:
            pass

        return {
            'source': f'텔레그램 채널 ({kst_str})',
            'time': kst_str,
            'raw_time': post_time,
            'rising': rising,
            'falling': falling
        }
    return None

def get_aftermarket_data(force_refresh=False):
    """
    애프터마켓(시간외 20:00 마감) 특징주 네이버 블로그 및 텔레그램 실시간 하이브리드 수집 모듈
    - 블로그든 텔레그램이든 '무조건 가장 최신 거래일(가장 먼저 올라온 곳)'의 데이터를 절대 1순위로 채택!
    - 블로그에 밤에 먼저 올라왔으면 블로그 것을 즉시 채택하고, 다음날 아침 텔레그램에 올라오면 자동 동기화.
    """
    global _aftermarket_cache
    now_ts = time.time()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(base_dir, 'data', 'last_aftermarket.json')

    # 메모리 캐시 (강제 갱신이 아니면 5분 유효)
    if not force_refresh and _aftermarket_cache['data'] and (now_ts - _aftermarket_cache['last_time'] < 300):
        return _aftermarket_cache['data']

    profiles = load_jsr_profiles()
    candidates = []

    # 1. 네이버 블로그 최신글 탐색 (최근 30개 글 대상 탐색으로 주말/연휴 글도 100% 포착)
    try:
        api_url = 'https://blog.naver.com/PostTitleListAsync.naver?blogId=crioppstock&viewdate=&currentPage=1&categoryNo=0&parentCategoryNo=&countPerPage=30'
        req_b = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        raw_b = urllib.request.urlopen(req_b, timeout=6).read().decode('ms949', errors='ignore')
        pattern = r'"logNo"\s*:\s*"(\d+)".*?"title"\s*:\s*"([^"]+)"'
        for m in re.finditer(pattern, raw_b):
            log_no = m.group(1)
            title = urllib.parse.unquote_plus(m.group(2))
            if any(k in title for k in ['에프터마켓', '애프터마켓', '시간외']):
                blog_candidate = _parse_blog_aftermarket(log_no, profiles)
                if blog_candidate and (blog_candidate.get('rising') or blog_candidate.get('falling')):
                    blog_candidate['title'] = title
                    blog_candidate['source'] = f'네이버 블로그 ({title[:24]})'
                    blog_candidate['log_no'] = int(log_no)
                    candidates.append(blog_candidate)
    except Exception as e:
        print(f"Blog crawl error: {e}")

    # 2. 텔레그램 채널 실시간 탐색 (당일 아침 본문 또는 링크 공유)
    try:
        t_url = 'https://t.me/s/crioppstockfree'
        req_t = urllib.request.Request(t_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req_t, timeout=6) as resp:
            html_t = resp.read().decode('utf-8', errors='ignore')
            soup_t = BeautifulSoup(html_t, 'html.parser')
            for wrap in reversed(soup_t.find_all('div', class_='tgme_widget_message_wrap')):
                m_div = wrap.find('div', class_='tgme_widget_message_text')
                if not m_div:
                    continue
                txt = m_div.get_text()
                time_tag = wrap.find('time')
                p_time = time_tag['datetime'] if time_tag and 'datetime' in time_tag.attrs else ''

                # [형태 1] 텔레그램 본문에 직접 특징주가 적힌 메시지
                if ('에프터마켓' in txt or '애프터마켓' in txt) and ('(' in txt and '%' in txt):
                    t_cand = _parse_telegram_aftermarket(m_div, p_time, profiles)
                    if t_cand and (t_cand.get('rising') or t_cand.get('falling')):
                        t_cand['title'] = txt.splitlines()[0] if txt else '텔레그램 에프터마켓'
                        t_cand['raw_time'] = p_time
                        candidates.append(t_cand)

                # [형태 2] 텔레그램에 공유된 최신 블로그 글 링크가 있는 경우
                m_link = re.search(r'blog\.naver\.com/crioppstock/(\d+)', txt)
                if m_link and ('에프터마켓' in txt or '애프터마켓' in txt or '시간외' in txt):
                    log_no = m_link.group(1)
                    if not any(c.get('log_no') == int(log_no) for c in candidates):
                        b_cand = _parse_blog_aftermarket(log_no, profiles)
                        if b_cand and (b_cand.get('rising') or b_cand.get('falling')):
                            b_cand['title'] = txt.splitlines()[0] if txt else f'텔레그램 공유글 ({log_no})'
                            b_cand['source'] = f'텔레그램 공유 블로그 ({p_time[:10] if p_time else "최신"})'
                            b_cand['raw_time'] = p_time
                            b_cand['log_no'] = int(log_no)
                            candidates.append(b_cand)
    except Exception as e:
        print(f"Telegram crawl error: {e}")

    # 3. 최우선 후보 선별 (블로그든 텔레그램이든 '무조건 가장 최신 날짜' 1순위 절대 채택!)
    chosen = None
    if candidates:
        candidates.sort(key=lambda c: (
            _extract_aftermarket_date_int(c),                     # 1순위: 실제 거래일자 (최신 우선)
            c.get('log_no', 0),                                   # 2순위: 블로그 글번호 (클수록 최신)
            c.get('raw_time', ''),                                # 3순위: 텔레그램 발행 시각
            len(c.get('rising', [])) + len(c.get('falling', []))  # 4순위: 종목 수
        ), reverse=True)
        chosen = candidates[0]
        print(f"[Aftermarket] 최신 후보 선정 완료: {_extract_aftermarket_date_int(chosen)} | {chosen.get('source')} | 상승 {len(chosen.get('rising',[]))}개, 하락 {len(chosen.get('falling',[]))}개")

    # 4. 수집 실패 시 이전 캐시 확인
    if not chosen or (not chosen.get('rising') and not chosen.get('falling')):
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_json = json.load(f)
                    _aftermarket_cache['data'] = cached_json
                    _aftermarket_cache['last_time'] = now_ts
                    return cached_json
            except Exception:
                pass
        return {
            'status': 'empty',
            'time': '',
            'rising': [],
            'falling': [],
            'cafe_text': '애프터마켓 특징주 데이터가 아직 등록되지 않았습니다.',
            'cafe_html': '<div>애프터마켓 특징주 데이터가 아직 등록되지 않았습니다.</div>'
        }

    rising = chosen['rising']
    falling = chosen['falling']
    post_time = chosen.get('time', '')
    source_label = chosen.get('source', '')

    # 5. 네이버 카페 / 텔레그램 일반 텍스트 생성 (빈 화살표 100% 제거)
    cafe_lines = ["◆ 애프터마켓 상승 특징주", ""]
    for s in rising:
        th = f" [{s['primary_theme']}]" if s.get('primary_theme') else ""
        cafe_lines.append(f"▶ {s['name']} ({s['pct']}){th}")
        for r in s['reasons']:
            if r:
                cafe_lines.append(f"→ {r}")
        cafe_lines.append("")

    cafe_lines.append("◆ 애프터마켓 하락 특징주")
    cafe_lines.append("")
    for s in falling:
        th = f" [{s['primary_theme']}]" if s.get('primary_theme') else ""
        cafe_lines.append(f"▶ {s['name']} ({s['pct']}){th}")
        for r in s['reasons']:
            if r:
                cafe_lines.append(f"→ {r}")
        cafe_lines.append("")

    cafe_text = "\n".join(cafe_lines).strip()

    # 6. 네이버 카페 스마트에디터 ONE 서식 (점선 칸/불필요한 테두리 완전 제거)
    html_parts = [
        '<div style="font-family: \'Apple SD Gothic Neo\', \'Malgun Gothic\', sans-serif; font-size: 14.5px; color: #1f2937; line-height: 1.7; max-width: 740px;">',
        '  <div style="background-color: #fef2f2; padding: 10px 14px; border-radius: 4px; margin-bottom: 16px;">',
        '    <span style="font-size: 16px; font-weight: 800; color: #dc2626;">◆ 애프터마켓 상승 특징주</span>',
        '  </div>'
    ]

    for s in rising:
        th_badge = f'<span style="background-color: #fef3c7; color: #b45309; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 3px; margin-left: 5px; vertical-align: middle;">{s["primary_theme"]}</span>' if s.get('primary_theme') else ''
        html_parts.append('  <div style="margin-bottom: 16px;">')
        html_parts.append(f'    <div style="font-size: 15px; font-weight: 800; color: #111827;">▶ <span style="color: #dc2626;">{s["name"]}</span> <span style="color: #dc2626; margin-left: 3px;">{s["pct"]}</span>{th_badge}</div>')
        for r in s['reasons']:
            r_html = re.sub(r'\[\[(.*?)\]\]\((https?://[^\s\)]+)\)', r'<a href="\2" target="_blank" style="color: #2563eb; text-decoration: underline; font-weight: 600;">\1</a>', r)
            r_html = re.sub(r'(?<!")(https?://[^\s\<\)]+)', r'<a href="\1" target="_blank" style="color: #2563eb; text-decoration: underline; font-weight: 600;">[관련기사]</a>', r_html)
            html_parts.append(f'    <div style="margin-top: 3px; color: #374151; font-size: 14px; word-break: keep-all;">→ {r_html}</div>')
        html_parts.append('  </div>')

    html_parts.extend([
        '  <div style="background-color: #eff6ff; padding: 10px 14px; border-radius: 4px; margin: 26px 0 16px 0;">',
        '    <span style="font-size: 16px; font-weight: 800; color: #2563eb;">◆ 애프터마켓 하락 특징주</span>',
        '  </div>'
    ])

    for s in falling:
        th_badge = f'<span style="background-color: #f1f5f9; color: #475569; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 3px; margin-left: 5px; vertical-align: middle;">{s["primary_theme"]}</span>' if s.get('primary_theme') else ''
        html_parts.append('  <div style="margin-bottom: 16px;">')
        html_parts.append(f'    <div style="font-size: 15px; font-weight: 800; color: #111827;">▶ <span style="color: #2563eb;">{s["name"]}</span> <span style="color: #2563eb; margin-left: 3px;">{s["pct"]}</span>{th_badge}</div>')
        for r in s['reasons']:
            r_html = re.sub(r'\[\[(.*?)\]\]\((https?://[^\s\)]+)\)', r'<a href="\2" target="_blank" style="color: #2563eb; text-decoration: underline; font-weight: 600;">\1</a>', r)
            r_html = re.sub(r'(?<!")(https?://[^\s\<\)]+)', r'<a href="\1" target="_blank" style="color: #2563eb; text-decoration: underline; font-weight: 600;">[관련기사]</a>', r_html)
            html_parts.append(f'    <div style="margin-top: 3px; color: #374151; font-size: 14px; word-break: keep-all;">→ {r_html}</div>')
        html_parts.append('  </div>')

    html_parts.append('</div>')
    cafe_html = "\n".join(html_parts)

    data = {
        'status': 'ok',
        'time': post_time,
        'source': source_label,
        'rising': rising,
        'falling': falling,
        'cafe_text': cafe_text,
        'cafe_html': cafe_html
    }

    try:
        os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    _aftermarket_cache['data'] = data
    _aftermarket_cache['last_time'] = now_ts
    return data

# ==============================================================================
# [신규 기능 1] 장중 뉴스 영구 누적 아카이브 & 초고속 키워드 검색 엔진 (SQLite)
# ==============================================================================

def get_news_db_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'news_archive.db')

def init_news_db():
    """뉴스 아카이브 SQLite 데이터베이스 초기화"""
    db_path = get_news_db_path()
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT,
                    source TEXT,
                    published_time TEXT,
                    display_time TEXT,
                    timestamp REAL,
                    category TEXT,
                    tags TEXT,
                    created_date TEXT
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_art_time ON articles(timestamp DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_art_title ON articles(title)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_art_date ON articles(created_date)')
            conn.commit()
    except Exception as e:
        print(f"[NewsDB Error] init failed: {e}")

# 모듈 로드 시 DB 초기화
init_news_db()

def save_articles_to_archive(articles):
    """수집된 기사들을 SQLite 아카이브에 영구 누적 적재"""
    if not articles:
        return 0
    db_path = get_news_db_path()
    saved_count = 0
    today_str = datetime.now().strftime('%Y-%m-%d')
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            cursor = conn.cursor()
            rows_to_insert = []
            for a in articles:
                art_id = a.get('id') or a.get('link') or a.get('title')
                tags_json = json.dumps(a.get('tags', []), ensure_ascii=False)
                rows_to_insert.append((
                    art_id,
                    a.get('title', ''),
                    a.get('link', ''),
                    a.get('source', ''),
                    a.get('published_time', ''),
                    a.get('display_time', ''),
                    float(a.get('timestamp') or time.time()),
                    a.get('category', '속보'),
                    tags_json,
                    today_str
                ))
            cursor.executemany('''
                INSERT OR IGNORE INTO articles (
                    id, title, link, source, published_time, display_time,
                    timestamp, category, tags, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', rows_to_insert)
            conn.commit()
            saved_count = cursor.rowcount
    except Exception as e:
        print(f"[NewsDB Error] save failed: {e}")
    return saved_count

def search_news_archive(query='', limit=250):
    """
    장중 누적된 모든 기사에서 키워드로 초고속 전체 검색 (제목, 태그, 언론사)
    장중에 지나간 기사도 키워드 하나로 즉시 탐색 가능
    """
    db_path = get_news_db_path()
    results = []
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            cursor = conn.cursor()
            if query and query.strip():
                tokens = query.strip().split()
                where_clauses = []
                params = []
                for tok in tokens:
                    clause = "(title LIKE ? OR tags LIKE ? OR source LIKE ?)"
                    p = f"%{tok}%"
                    where_clauses.append(clause)
                    params.extend([p, p, p])
                params.append(limit)
                sql = f'''
                    SELECT id, title, link, source, published_time, display_time, timestamp, category, tags
                    FROM articles
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY timestamp DESC
                    LIMIT ?
                '''
                cursor.execute(sql, params)
            else:
                cursor.execute('''
                    SELECT id, title, link, source, published_time, display_time, timestamp, category, tags
                    FROM articles
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))

            for row in cursor.fetchall():
                try:
                    tags = json.loads(row[8]) if row[8] else []
                except Exception:
                    tags = []
                results.append({
                    'id': row[0],
                    'title': row[1],
                    'link': row[2],
                    'source': row[3],
                    'published_time': row[4],
                    'display_time': row[5],
                    'timestamp': row[6],
                    'category': row[7],
                    'tags': tags
                })
    except Exception as e:
        print(f"[NewsDB Error] search failed: {e}")
    return results


# ==============================================================================
# [신규 기능 2] 시황카세(sihwangkase.co.kr) 장전이슈 & 관심종목 100% 실시간 연동
# ==============================================================================

_sihwang_cache = {
    'issues': None,
    'last_issues_time': 0,
    'watchlist': None,
    'last_watchlist_time': 0
}

def get_sihwangkase_issues(force_refresh=False):
    """
    시황카세 장전이슈 수집:
    1. 오늘 3회 이상 언급된 종목 (핫박스 카운트 뱃지)
    2. 장전 핵심 이슈 & 테마별 관련주 칩 목록
    """
    now_ts = time.time()
    if not force_refresh and _sihwang_cache['issues'] and (now_ts - _sihwang_cache['last_issues_time'] < 180):
        return _sihwang_cache['issues']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://sihwangkase.co.kr/issue',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    hot_mentions = []
    issues = []
    
    try:
        req = urllib.request.Request('https://sihwangkase.co.kr/issue', headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. 오늘 3회 이상 언급된 종목 (핫박스)
        hotbox = soup.find(class_='hotbox')
        if hotbox:
            for chip in hotbox.find_all('a', class_=re.compile(r'chip')):
                sup = chip.find('sup')
                cnt = int(sup.get_text(strip=True)) if sup else 1
                if sup:
                    sup.decompose()
                name = chip.get_text(strip=True)
                href = chip.get('href', '')
                if name:
                    hot_mentions.append({
                        'name': name,
                        'count': cnt,
                        'link': href
                    })

        # 2. 핵심 이슈 및 섹터별 이슈 파싱
        for item in soup.find_all('details', class_=re.compile(r'item')):
            summary = item.find('summary')
            if not summary:
                continue
            
            when_tag = summary.find(class_='when')
            when = when_tag.get_text(" ", strip=True) if when_tag else ""
            
            tt_tag = summary.find(class_='tt')
            title = tt_tag.get_text(strip=True) if tt_tag else ""
            
            tags = [t.get_text(strip=True) for t in summary.find_all(class_='tag')]
            badge = summary.find(class_='badge')
            badge_text = badge.get_text(strip=True) if badge else ""
            
            detail = item.find(class_='detail')
            body_p = detail.find(class_='body') if detail else None
            body_text = body_p.get_text(strip=True) if body_p else ""
            
            stock_groups = []
            if detail:
                for sgrp in detail.find_all(class_='sgrp'):
                    slabel = sgrp.find(class_='slabel')
                    grp_name = slabel.get_text(strip=True) if slabel else "관련주"
                    chips = []
                    for chip in sgrp.find_all('a', class_=re.compile(r'chip')):
                        c_name = chip.get_text(strip=True)
                        c_href = chip.get('href', '')
                        is_hot = 'hot' in chip.get('class', [])
                        chips.append({'name': c_name, 'link': c_href, 'is_hot': is_hot})
                    if chips:
                        stock_groups.append({
                            'group_name': grp_name,
                            'stocks': chips
                        })
                        
            origin_a = detail.find('a', href=re.compile(r'^http')) if detail else None
            origin_link = origin_a.get('href') if origin_a else ""
            
            if title:
                issues.append({
                    'title': title,
                    'when': when,
                    'tags': tags,
                    'badge': badge_text,
                    'summary': body_text,
                    'stock_groups': stock_groups,
                    'origin_link': origin_link
                })
        
        result = {
            'status': 'ok',
            'hot_mentions': hot_mentions,
            'issues': issues,
            'count': len(issues),
            'updated_at': datetime.now().strftime('%H:%M:%S')
        }
        # 로컬 영구 백업 캐시 저장 (서버 다운/차단 대비)
        try:
            cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sihwang_issues.json')
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        _sihwang_cache['issues'] = result
        _sihwang_cache['last_issues_time'] = now_ts
        return result
    except Exception as e:
        print(f"[Sihwang Error] issue fetch failed: {e}")
        # 외부 사이트 장애나 네트워크 차단 시 로컬 백업 자동 복원
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sihwang_issues.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    cached['from_cache'] = True
                    return cached
            except Exception:
                pass
        return {
            'status': 'error',
            'message': str(e),
            'hot_mentions': [],
            'issues': []
        }

def get_sihwangkase_watchlist(force_refresh=False):
    """
    시황카세 국내 관심종목(/api/krwatch):
    - 61개 테마 그룹 (원전, 바이오, AI, 전력, 2차전지 등)
    - 839개 종목별 실시간 시세, 등락률, 거래대금(억원)
    - 다중 테마 중복 종목 태깅 및 정렬/전광판 데이터 제공
    - 외부 차단/장애 대비 로컬 스냅샷 자동 백업 및 복원
    """
    now_ts = time.time()
    if not force_refresh and _sihwang_cache['watchlist'] and (now_ts - _sihwang_cache['last_watchlist_time'] < 60):
        return _sihwang_cache['watchlist']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://sihwangkase.co.kr/krwatch',
        'Accept': 'application/json'
    }

    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sihwang_watchlist.json')
    catalog_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'themes_catalog.json')

    try:
        req = urllib.request.Request('https://sihwangkase.co.kr/api/krwatch', headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            groups = data.get('groups', [])
            themes_of = data.get('themes_of', {})

            # 중복 테마 통계 산출
            overlap2 = 0
            overlap3 = 0
            overlap4 = 0
            for code, th_list in themes_of.items():
                c = len(th_list)
                if c == 2: overlap2 += 1
                elif c == 3: overlap3 += 1
                elif c >= 4: overlap4 += 1

            for g in groups:
                tot = 0
                for r in g.get('rows', []):
                    eok_val = r.get('eok') or 0
                    try:
                        tot += int(eok_val)
                    except Exception:
                        pass
                    code = r.get('code', '')
                    t_list = themes_of.get(code, [])
                    r['overlap_count'] = len(t_list)
                    r['overlap_themes'] = t_list
                g['total_eok'] = tot
                if tot >= 10000:
                    g['total_amount_str'] = f"{tot / 10000:.1f}조"
                else:
                    g['total_amount_str'] = f"{tot:,}억"
                # avg_rate float 보장
                try:
                    g['avg_rate'] = float(g.get('avg_rate', 0.0))
                except Exception:
                    g['avg_rate'] = 0.0

            result = {
                'status': 'ok',
                'groups': groups,
                'stocks_count': data.get('stocks', 839),
                'themes_count': len(groups),
                'themes_of': themes_of,
                'overlap_stats': {
                    'overlap_2': overlap2,
                    'overlap_3': overlap3,
                    'overlap_4_plus': overlap4
                },
                'market': data.get('market', 'KRX+NXT 통합'),
                'updated_at': data.get('updated_at', datetime.now().strftime('%H:%M:%S'))
            }

            # 로컬 영구 백업 저장
            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                # 테마 카탈로그 구조 독립 영구 보존
                catalog = [{
                    'name': g.get('name'),
                    'sector': g.get('sector'),
                    'stocks': [{'code': r.get('code'), 'name': r.get('name')} for r in g.get('rows', [])]
                } for g in groups]
                with open(catalog_file, 'w', encoding='utf-8') as f:
                    json.dump(catalog, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            _sihwang_cache['watchlist'] = result
            _sihwang_cache['last_watchlist_time'] = now_ts
            return result
    except Exception as e:
        print(f"[Sihwang Error] watchlist fetch failed: {e}")
        # 외부 사이트 장애나 네트워크 차단 시 로컬 백업 자동 복원
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    cached['from_cache'] = True
                    return cached
            except Exception:
                pass
        return {
            'status': 'error',
            'message': str(e),
            'groups': [],
            'stocks_count': 0
        }

# 개별 종목 상세 및 차트 캐시 (TTL: 180초)
_stock_detail_cache = {}
_stock_chart_cache = {}

def get_stock_detail(code):
    """
    개별 종목 정밀 분석 데이터 (현재가, 등락률, 시총, 거래대금, 외인/기관 수급, RS점수, 상승사유 등)
    """
    if not code:
        return {'status': 'error', 'message': 'code required'}
    
    now_ts = time.time()
    if code in _stock_detail_cache:
        cached = _stock_detail_cache[code]
        if now_ts - cached['time'] < 180:
            return cached['data']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://sihwangkase.co.kr/krwatch',
    }
    try:
        url = f'https://sihwangkase.co.kr/api/stock?q={code}'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            data['status'] = 'ok'
            _stock_detail_cache[code] = {'data': data, 'time': now_ts}
            return data
    except Exception as e:
        try:
            n_url = f'https://m.stock.naver.com/api/stock/{code}/basic'
            n_req = urllib.request.Request(n_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(n_req, timeout=3) as n_resp:
                nd = json.loads(n_resp.read().decode('utf-8'))
                res = {
                    'status': 'ok',
                    'code': code,
                    'name': nd.get('stockName', ''),
                    'price': float(nd.get('closePrice', '0').replace(',', '')),
                    'change_rate': float(nd.get('fluctuationsRatio', '0')),
                    'market': '코스닥' if 'KOSDAQ' in str(nd.get('sosok', '')) else '코스피',
                    'reason': '실시간 증시 데이터',
                    'rs_rating': {'rs': 50, 'vs': '코스피'},
                }
                _stock_detail_cache[code] = {'data': res, 'time': now_ts}
                return res
        except Exception as e2:
            return {'status': 'error', 'message': f"{e} / {e2}"}

def get_stock_chart(code):
    """
    개별 종목 캔들 차트 및 이동평균선, 거래량 시계열 데이터
    """
    if not code:
        return {'status': 'error', 'message': 'code required', 'rows': []}
        
    now_ts = time.time()
    if code in _stock_chart_cache:
        cached = _stock_chart_cache[code]
        if now_ts - cached['time'] < 180:
            return cached['data']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://sihwangkase.co.kr/krwatch',
    }
    try:
        url = f'https://sihwangkase.co.kr/api/chart?code={code}'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            data['status'] = 'ok'
            _stock_chart_cache[code] = {'data': data, 'time': now_ts}
            return data
    except Exception as e:
        return {'status': 'error', 'message': str(e), 'rows': []}


_macro_cache = {'data': None, 'time': 0}
_indicators_cache = {'data': None, 'time': 0}
_calendar_cache = {}

def get_macro_data(force_refresh=False):
    """원자재, 환율, 반도체(DRAM/NAND/SOX/수출), 증시자금 등 23종 매크로 데이터 수집"""
    global _macro_cache
    now_ts = time.time()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(base_dir, 'data', 'sihwang_macro.json')

    if not force_refresh and _macro_cache['data'] and (now_ts - _macro_cache['time'] < 300):
        return _macro_cache['data']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://sihwangkase.co.kr/futures',
        'Accept': 'application/json'
    }

    try:
        url = 'https://sihwangkase.co.kr/api/macro'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            data['status'] = 'ok'
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _macro_cache = {'data': data, 'time': now_ts}
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return data
    except Exception as e:
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    cached['status'] = 'ok'
                    cached['from_cache'] = True
                    _macro_cache = {'data': cached, 'time': now_ts}
                    return cached
            except Exception:
                pass
        return {'status': 'error', 'message': str(e), 'items': []}

def get_indicators_data(force_refresh=False):
    """코스피200 선물, 미결제약정(OI), 베이시스(콘탱고/백워데이션), 괴리율, 프로그램 비차익 순매수"""
    global _indicators_cache
    now_ts = time.time()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(base_dir, 'data', 'sihwang_indicators.json')

    if not force_refresh and _indicators_cache['data'] and (now_ts - _indicators_cache['time'] < 30):
        return _indicators_cache['data']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://sihwangkase.co.kr/futures',
        'Accept': 'application/json'
    }

    try:
        url = 'https://sihwangkase.co.kr/api/indicators'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            data['status'] = 'ok'
            _indicators_cache = {'data': data, 'time': now_ts}
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return data
    except Exception as e:
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    cached['status'] = 'ok'
                    cached['from_cache'] = True
                    _indicators_cache = {'data': cached, 'time': now_ts}
                    return cached
            except Exception:
                pass
        return {'status': 'error', 'message': str(e)}

def get_calendar_data(month=None, force_refresh=False):
    """증시 캘린더 (실적발표, 공모주, FOMC, 경제지표, 만기일, 락업해제)"""
    global _calendar_cache
    now_ts = time.time()
    if not month:
        month = datetime.now().strftime('%Y-%m')

    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(base_dir, 'data', f'sihwang_calendar_{month}.json')
    default_cache_file = os.path.join(base_dir, 'data', 'sihwang_calendar.json')

    cached_entry = _calendar_cache.get(month)
    if not force_refresh and cached_entry and (now_ts - cached_entry['time'] < 600):
        return cached_entry['data']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://sihwangkase.co.kr/calendar',
        'Accept': 'application/json'
    }

    try:
        url = f'https://sihwangkase.co.kr/api/calendar?month={month}'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            data['status'] = 'ok'
            _calendar_cache[month] = {'data': data, 'time': now_ts}
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return data
    except Exception as e:
        for cf in [cache_file, default_cache_file]:
            if os.path.exists(cf):
                try:
                    with open(cf, 'r', encoding='utf-8') as f:
                        cached = json.load(f)
                        cached['status'] = 'ok'
                        cached['from_cache'] = True
                        _calendar_cache[month] = {'data': cached, 'time': now_ts}
                        return cached
                except Exception:
                    pass
        return {'status': 'error', 'message': str(e), 'events': [], 'kinds': [], 'month': month}


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
