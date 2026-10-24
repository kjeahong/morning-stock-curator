# -*- coding: utf-8 -*-
import os
import shutil

src = r"C:\Users\Administrator\Desktop\Overhang\dist\모닝증시큐레이터.exe"
dst = r"C:\Users\Administrator\Desktop\모닝증시큐레이터.exe"

if os.path.exists(src):
    shutil.copy2(src, dst)
    print("Copied successfully to Desktop:", dst)
else:
    print("Source not found:", src)
