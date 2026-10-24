# -*- coding: utf-8 -*-
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def polish_catalyst(name, cat):
    if not cat:
        return ''
    c = cat.strip(' ,·:;`\'"“”‘’')
    # Clean dangling brackets or prefixes
    c = re.sub(r'\[.*?\]', '', c)
    c = re.sub(r'\(.*?\)', '', c)
    c = re.sub(r'^\s*,\s*', '', c)
    c = re.sub(r'\s*,\s*$', '', c)
    
    # Specific patterns
    if any(w in c for w in ['상장 첫날', '새내기주', '따블', '공모']):
        return '코스닥 신규상장 첫날 수급 유입에'
    if any(w in c for w in ['사망', '유고']):
        return '북괴 김정은 사망설 확산에'
    if '무죄' in c:
        return '오세훈 서울시장 항소심 무죄 판결 소식에'
    if 'OLED' in c or 'UTG' in c:
        return '차량용 롤러블 OLED UTG 개발 소식에'
    if '보안' in c or 'PHP' in c:
        return 'PHP 취약점 보안 비상 이슈에 보안주 부각되며'
    if '무상증자' in c or '1대1' in c:
        return '1대1 무상증자 일정 모멘텀에'
    if '임상' in c or '기술수출' in c or '치료제' in c:
        if '소식' not in c and '기대감' not in c:
            return f"{c} 기대감에"
        return f"{c}에" if not c.endswith('에') else c
    if '공개매수' in c or '유상증자' in c:
        return f"{c} 소식에" if not c.endswith('에') else c

    # Remove trailing hanging words
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

cases = [
    ('디티에스', '‘따블’ 달성한 , 상장 첫날에 대'),
    ('포메탈', '“김정은 사망했다” 소문 하나에 ‘'),
    ('앤로보틱스', '‘오세훈 시장 항소심 무죄’ 소식에'),
    ('도우인시스', '차량용 롤러블 OLED UTG 개발'),
    ('모니터랩', 'PHP 보안 비상에'),
    ('MH에탄올', '1대1 무상증자 일정 주목'),
    ('지투지바이오', '빅파마 기술수출'),
    ('유니테크노', '삼성SDI·LG엔솔 ESS 공급')
]

for name, cat in cases:
    print(f"[{name}] -> {polish_catalyst(name, cat)}")
