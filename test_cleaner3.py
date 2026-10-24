# -*- coding: utf-8 -*-
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get_catalyst_from_headline(stock_name, headline):
    t = headline
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    t = re.sub(r'\[.*?\]', '', t)
    t = t.strip(' ,·:')
    
    # Split by ellipsis
    parts = re.split(r'\s*(?:…|\u2026|\.{2,}|···)\s*', t)
    if len(parts) > 1:
        p0, p1 = parts[0].strip(), parts[1].strip()
        # If stock is in p1 and p1 is mostly just stock name and percent: e.g. "모니터랩 25%↑"
        p1_no_name = re.sub(rf'{re.escape(stock_name)}', '', p1)
        p1_no_name = re.sub(r'[\d\.,%↑상승급등폭등\s]', '', p1_no_name)
        if stock_name in p1 and len(p1_no_name) <= 2:
            t = p0
        # If stock is in p0 and p0 is mostly just stock name and percent: e.g. "AP위성 18.71% 상승"
        p0_no_name = re.sub(rf'{re.escape(stock_name)}', '', p0)
        p0_no_name = re.sub(r'[\d\.,%↑상승급등폭등\s]', '', p0_no_name)
        if stock_name in p0 and len(p0_no_name) <= 2:
            t = p1
        elif stock_name in p0:
            t = p0

    # Clean leading stock name: "도우인시스, ..." -> "..."
    t = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', t).strip()
    t = re.sub(r'\(.*?\)', '', t).strip()

    # Pattern A: "...에 ... 상한가/급등/강세" -> extract reason before "에"
    mA = re.search(r'^(.*?에(?:는)?)\s*(?:[\w\s,·]+)?(?:상한가|급등|강세|폭등|상승|돌파|안착|마감)', t)
    if mA:
        cand = mA.group(1).strip()
        cand = cand.replace(stock_name, '').strip(' ,·:')
        if len(cand) >= 4:
            return cand

    # Pattern B: "... 앞두고/소식에/기대감에/영향에/선고에"
    mB = re.search(r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급|앞두고)에?)', t)
    if mB:
        cand = mB.group(1).strip()
        cand = cand.replace(stock_name, '').strip(' ,·:')
        if len(cand) >= 4:
            return cand

    # Pattern C: Remove trailing percentage and surge verbs
    t = re.sub(r'[\d\.]+%[↑상승급등]*', '', t).strip()
    t = re.sub(r'(?:상한가|급등|강세|폭등|직행|안착|마감|상승).*$', '', t).strip(' ,·:')
    t = t.replace(stock_name, '').strip(' ,·:')
    
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
    ("퓨쳐켐", "퓨쳐켐, 전립선암 치료제 'FC705' 미국 임상 2a상서 항암 효과 확인 - 히트뉴스"),
    ("와이바이오로직스", "애브비 한선염 3상 성공…HK이노엔·와이바이오 신약도 '16주 HiSCR75' 검증 - 메디코파마")
]

for name, headline in cases:
    res = get_catalyst_from_headline(name, headline)
    print(f"[{name}] -> {res}")
