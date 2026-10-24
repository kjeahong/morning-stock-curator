# -*- coding: utf-8 -*-
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def trace_clean(stock_name, headline):
    print(f"\n--- {stock_name}: {headline} ---")
    t = headline
    if ' - ' in t:
        t = t.rsplit(' - ', 1)[0]
    t = re.sub(r'\[.*?\]', '', t)
    t = t.strip(' ,·:')
    print("Step 1 (strip media/brackets):", repr(t))
    
    parts = re.split(r'\s*(?:…|\u2026|\.{2,}|···)\s*', t)
    print("Parts:", parts)
    if len(parts) > 1:
        p0 = parts[0].strip()
        p1 = parts[1].strip()
        # If p0 has stock name or pct
        if (stock_name in p0 or any(w in p0 for w in ['상승', '급등', '상한가', '폭등', '%', '↑', '강세'])) and not any(w in p1 for w in ['상한가', '폭등', '급등']):
            t = p1
        elif (stock_name in p1 or any(w in p1 for w in ['상승', '급등', '상한가', '폭등', '%', '↑', '강세'])) and not any(w in p0 for w in ['상한가', '폭등', '급등']):
            t = p0
    print("Step 2 (parts select):", repr(t))

    t = re.sub(rf'^{re.escape(stock_name)}[은는이가]?\s*[,·:\-]?\s*', '', t).strip()
    t = re.sub(r'\(.*?\)', '', t).strip()
    print("Step 3 (strip leading name):", repr(t))

    m = re.search(r'^(.*?에(?:는)?)\s*(?:[\w\s,·]+)?(?:상한가|급등|강세|폭등|상승|돌파|안착|마감)', t)
    if m:
        reason = m.group(1).strip()
        print("Step 4a (matched pattern 1):", repr(reason))
        t = reason
    else:
        m2 = re.search(r'(.*?(?:소식|영향|기대감|기대|부각|발표|체결|수주|공시|선고|성공|승인|확인|인수|합병|공개매수|유증|무증|개발|공급)에?)', t)
        if m2:
            print("Step 4b (matched pattern 2):", repr(m2.group(1).strip()))
            t = m2.group(1).strip()

    t = re.sub(r'[\d\.]+%[↑상승급등]*', '', t).strip()
    t = re.sub(r'(?:상한가|급등|강세|폭등|직행|안착).*$', '', t).strip(' ,·:')
    t = t.replace(stock_name, '').strip(' ,·:')
    print("Final:", repr(t))

trace_clean("모니터랩", "PHP 보안 비상에 관련주 강세···모니터랩 25%↑ - 뉴스웨이")
trace_clean("스페코", "김정은 사망설 확산에 스페코 상한가…방산주 매수세 집중 - 더팩트")
trace_clean("디티에스", "[특징주] 디티에스, 코스닥 상장 첫날 35% 강세 마감…상승폭은 줄어(종합) - 연합뉴스")
