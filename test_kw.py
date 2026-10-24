# -*- coding: utf-8 -*-
from collector import CLOSING_THEME_RULES
text = '서울식품우  “추락 방지 장비 없었다”… ‘나혼산’ 번지점프 업체, 노동부 조사 받는다 - 조선비즈'
for th, kws in CLOSING_THEME_RULES:
    for kw in kws:
        if kw.lower() in text.lower():
            print('Matched:', th, 'kw:', repr(kw))
