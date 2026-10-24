# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('c:/Users/Administrator/Desktop/Overhang/templates/index.html', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'closing' in l.lower() or 'closingview' in l.lower():
        print(f"{i+1}: {l.strip()}")
