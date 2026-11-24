# -*- coding: utf-8 -*-
"""
클라우드 및 로컬 겸용 HUD 모듈 (desktop_hud.py)
클라우드(리눅스) 환경에서는 GUI 에러 없이 안전하게 통과합니다.
"""
import sys
import os

def show_desktop_hud(title, source="속보", link=None, position="top-center", duration_sec=7):
    # 클라우드/리눅스 환경에서는 GUI 창을 띄우지 않고 안전하게 무시
    if sys.platform != 'win32' or os.environ.get('RENDER'):
        return
    try:
        import subprocess
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'desktop_hud.py')
        args = [sys.executable, script_path, str(title), str(source), str(link or ''), str(position), str(duration_sec)]
        subprocess.Popen(args)
    except Exception:
        pass

def run_hud_window(title, source="속보", link=None, position="top-center", duration_sec=7):
    if sys.platform != 'win32' or os.environ.get('RENDER'):
        return
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("MorningStockCurator_Alert")
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.destroy()
    except Exception:
        pass

if __name__ == "__main__":
    pass
