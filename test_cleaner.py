# -*- coding: utf-8 -*-
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def clean_headline_catalyst(stock_name, headline):
    t = headline
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    # Remove press tags [특징주], [마감분석], [종목NOW]
    t = re.sub(r'\[.*?\]', '', t)
    # Remove percent changes like 25%↑, 18.71% 상승, 30% 폭등
    t = t.strip(' ,·:')
    
    # Check if there is an ellipsis separator (… or ... or ···)
    parts = re.split(r'[…\.\.·]{2,}', t)
    if len(parts) > 1:
        # One part usually has the reason, the other has "종목 20% 상승"
        p0 = parts[0].strip()
        p1 = parts[1].strip()
        # If part 0 has stock name + surge word, part 1 is likely the reason!
        if stock_name in p0 and any(w in p0 for w in ['상승', '급등', '상한가', '폭등', '%', '↑']):
            t = p1
        elif stock_name in p1 and any(w in p1 for w in ['상승', '급등', '상한가', '폭등', '%', '↑']):
            t = p0

    # If it starts with stock_name: "도우인시스, 차량용 롤러블 OLED..."
    t = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', t).strip()

    # Pattern: "...에 ... 상한가/급등/강세" -> extract the cause
    m = re.search(r'^(.*?에(?:는)?)\s*(?:[\w\s,·]+)?(?:상한가|급등|강세|폭등|상승|돌파|안착|마감)', t)
    if m:
        reason = m.group(1).strip()
        # remove stock name from inside reason if present
        reason = reason.replace(stock_name, '').strip(' ,·:')
        if len(reason) >= 5:
            return reason

    # Pattern: "... 소식에", "... 기대감에", "... 영향에"
    m2 = re.search(r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급)에?)', t)
    if m2:
        reason = m2.group(1).strip()
        reason = reason.replace(stock_name, '').strip(' ,·:')
        if len(reason) >= 5:
            return reason

    # Clean stock name out and trailing surge words
    cleaned = re.sub(r'(?:상한가|급등|강세|폭등|상승|직행|안착|마감).*$', '', t).strip(' ,·:')
    cleaned = cleaned.replace(stock_name, '').strip(' ,·:')
    
    return cleaned if len(cleaned) >= 5 else t

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
