# -*- coding: utf-8 -*-
import os
import win32com.client

shell = win32com.client.Dispatch('WScript.Shell')
desktop = shell.SpecialFolders('Desktop')

shortcut_path = os.path.join(desktop, '모닝 증시 큐레이터.lnk')
target = os.path.join(desktop, '모닝증시큐레이터.exe')
icon_path = os.path.join(r'C:\Users\Administrator\Desktop\Overhang', 'app_icon.ico')

shortcut = shell.CreateShortCut(shortcut_path)
shortcut.TargetPath = target
shortcut.WorkingDirectory = r'C:\Users\Administrator\Desktop\Overhang'
shortcut.Description = '장전 증시 뉴스 수집 및 네이버 카페 칼럼 발행기'
if os.path.exists(icon_path):
    shortcut.IconLocation = icon_path + ',0'
shortcut.Save()

print('Shortcut updated successfully:', shortcut_path)
