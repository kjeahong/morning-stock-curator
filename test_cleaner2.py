# -*- coding: utf-8 -*-
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def clean_headline_catalyst(stock_name, headline):
    t = headline
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    t = re.sub(r'\[.*?\]', '', t)
    t = t.strip(' ,·:')
    
    # Check if there is an ellipsis separator (… or ... or ···)
    parts = re.split(r'\s*(?:…|\u2026|\.{2,}|···)\s*', t)
    if len(parts) > 1:
        p0 = parts[0].strip()
        p1 = parts[1].strip()
        # If p0 has stock name or pct or surge words, p1 is the catalyst
        if (stock_name in p0 or any(w in p0 for w in ['상승', '급등', '상한가', '폭등', '%', '↑', '강세'])) and not any(w in p1 for w in ['상한가', '폭등', '급등']):
            t = p1
        elif (stock_name in p1 or any(w in p1 for w in ['상승', '급등', '상한가', '폭등', '%', '↑', '강세'])) and not any(w in p0 for w in ['상한가', '폭등', '급등']):
            t = p0

    # Remove leading stock name
    t = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', t).strip()
    
    # Remove press brackets/tails
    t = re.sub(r'\(.*?\)', '', t).strip()

    # Pattern: "...에 ... 상한가/급등"
    m = re.search(r'^(.*?에(?:는)?)\s*(?:[\w\s,·]+)?(?:상한가|급등|강세|폭등|상승|돌파|안착|마감)', t)
    if m:
        reason = m.group(1).strip()
        reason = reason.replace(stock_name, '').strip(' ,·:')
        if len(reason) >= 4:
            t = reason

    # Pattern: "... 소식에", "... 기대감에", "... 영향에"
    m2 = re.search(r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급)에?)', t)
    if m2:
        reason = m2.group(1).strip()
        reason = reason.replace(stock_name, '').strip(' ,·:')
        if len(reason) >= 4:
            t = reason

    # Clean stock name out and trailing surge words
    t = re.sub(r'[\d\.]+%[↑상승급등]*', '', t).strip()
    t = re.sub(r'(?:상한가|급등|강세|폭등|직행|안착).*$', '', t).strip(' ,·:')
    t = t.replace(stock_name, '').strip(' ,·:')
    
    # Format nicely with particle if needed
    if t.endswith('에') or t.endswith('소식') or t.endswith('기대감') or t.endswith('영향') or t.endswith('주목'):
        pass
    elif t.endswith('개발') or t.endswith('체결') or t.endswith('발표') or t.endswith('선고') or t.endswith('성공'):
        t += ' 소식에'
    elif t.endswith('기대'):
        t += '감에'
        
    return t

cases = [
    ("도우인시스", "도우인시스, 차량용 롤러블 OLED UTG 개발한다 - 디일렉"),
    ("모니터랩", "PHP 보안 비상에 관련주 강세···모니터랩 25%↑ - 뉴스웨이"),
    ("AP위성", "AP위성 18.71% 상승…차세대 위성 사업 수주 기대 - 잡포스트"),
    ("아이패밀리에스씨", "[특징주] 아이패밀리에스씨, 日 기업 공개매수에 상한가 - 연합뉴스"),
    ("노을", "[특징주] 노을, 지구홀딩스 최대주주 변경 앞두고 상한가 - 바이오타임즈"),
    ("스페코", "김정은 사망설 확산에 스페코 상한가…방산주 매수세 집중 - 더팩트"),
    ("진양화학", "오세훈 무죄에 테마주 급등…진양화학·진양산업 상한가 - 한국금융신문"),
    ("MH에탄올", "MH에탄올 12.63% 상승…1대1 무상증자 일정 주목 - 잡포스트"),
    ("디티에스", "[특징주] 디티에스, 코스닥 상장 첫날 35% 강세 마감…상승폭은 줄어(종합) - 연합뉴스"),
    ("퓨쳐켐", "퓨쳐켐, 전립선암 치료제 'FC705' 미국 임상 2a상서 항암 효과 확인 - 히트뉴스")
]

for name, headline in cases:
    res = clean_headline_catalyst(name, headline)
    print(f"[{name}] -> {res}")
