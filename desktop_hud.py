# -*- coding: utf-8 -*-
"""
HTS 전체화면 및 43인치 대형 모니터 맞춤형 Always-on-Top 속보 HUD 오버레이
독립 프로세스 방식으로 실행되어 Tcl/Tk 충돌 없이 100번이든 1,000번이든 안정적으로 작동합니다.
"""

import sys
import os
import time
import webbrowser
import subprocess
try:
    import tkinter as tk
except Exception:
    tk = None

def run_hud_window(title, source="속보", link=None, position="top-center", duration_sec=7):
    """
    독립 프로세스 메인 스레드에서 단독 실행되는 HUD 창
    """
    if sys.platform != 'win32' or os.environ.get('RENDER'):
        return
    try:
        try:
    import tkinter as tk
except Exception:
    tk = None
    except Exception:
        return
    root = tk.Tk()
    root.title("MorningStockCurator_Alert")
    root.overrideredirect(True) # 타이틀바 제거
    root.attributes('-topmost', True) # HTS 화면 위에 항상 최상위 유지

    # 43인치 고해상도(UHD/QHD) 맞춤 크기
    w = 740
    h = 105
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()

    if position == 'center':
        x = (sw - w) // 2
        y = (sh - h) // 2
    elif position == 'bottom-right':
        x = sw - w - 30
        y = sh - h - 60
    else: # top-center (화면 상단 정중앙)
        x = (sw - w) // 2
        y = 45

    root.geometry(f"{w}x{h}+{x}+{y}")
    root.configure(bg="#f59e0b") # 골드 외곽선

    # 1. 외곽선 프레임 (2px)
    border_frame = tk.Frame(root, bg="#f59e0b", padx=2, pady=2)
    border_frame.pack(fill="both", expand=True)

    # 2. 내부 본체 (고급 딥 슬레이트 다크 배경)
    main_box = tk.Frame(border_frame, bg="#0f172a", padx=16, pady=10)
    main_box.pack(fill="both", expand=True)

    # 3. 상단 헤더 (속보 뱃지, 출처, 시간, 닫기)
    header = tk.Frame(main_box, bg="#0f172a")
    header.pack(fill="x")

    # 빨간 뱃지
    badge = tk.Label(header, text=" ⚡ 실시간 속보 ", bg="#dc2626", fg="#ffffff", font=("맑은 고딕", 10, "bold"), padx=4, pady=1)
    badge.pack(side="left", padx=(0, 8))

    # 출처 뱃지
    src_tag = f"[{source}]" if source else "[증시속보]"
    src_lbl = tk.Label(header, text=src_tag, bg="#1e293b", fg="#fbbf24", font=("맑은 고딕", 10, "bold"), padx=6, pady=1)
    src_lbl.pack(side="left", padx=(0, 8))

    time_str = time.strftime("%H:%M:%S")
    time_lbl = tk.Label(header, text=time_str, bg="#0f172a", fg="#94a3b8", font=("Consolas", 10))
    time_lbl.pack(side="left")

    guide_lbl = tk.Label(header, text="(클릭 시 기사 원문 열림)", bg="#0f172a", fg="#64748b", font=("맑은 고딕", 9))
    guide_lbl.pack(side="left", padx=(10, 0))

    def do_close(e=None):
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)

    btn_close = tk.Label(header, text=" ✕ 닫기 ", bg="#1e293b", fg="#cbd5e1", font=("맑은 고딕", 9, "bold"), cursor="hand2", padx=6, pady=1)
    btn_close.pack(side="right")
    btn_close.bind("<Button-1>", do_close)

    # 4. 헤드라인 제목 (43인치에서 아주 시원한 14pt 굵은 볼드 폰트)
    clean_title = (title or "실시간 증시 속보가 도착했습니다.").replace('\n', ' ').strip()
    display_title = clean_title if len(clean_title) <= 46 else clean_title[:44] + "..."

    title_lbl = tk.Label(
        main_box,
        text=display_title,
        bg="#0f172a",
        fg="#ffffff",
        font=("맑은 고딕", 14, "bold"),
        anchor="w",
        cursor="hand2"
    )
    title_lbl.pack(fill="x", pady=(6, 0))

    # 클릭 이벤트 (원문 기사 열기)
    def on_click(e=None):
        if link and link.startswith('http'):
            webbrowser.open(link)
        else:
            webbrowser.open('http://localhost:5000')
        do_close()

    for w_item in (main_box, title_lbl, border_frame):
        w_item.bind("<Button-1>", on_click)

    # 마우스 오버 시 타이머 일시정지 (천천히 읽기 지원)
    close_timer_id = [None]

    def start_timer():
        close_timer_id[0] = root.after(int(duration_sec * 1000), do_close)

    def on_enter(e):
        if close_timer_id[0]:
            root.after_cancel(close_timer_id[0])
            close_timer_id[0] = None

    def on_leave(e):
        if not close_timer_id[0]:
            close_timer_id[0] = root.after(3500, do_close)

    for w_item in (root, border_frame, main_box, title_lbl, header, badge, src_lbl, time_lbl, guide_lbl):
        w_item.bind("<Enter>", on_enter)
        w_item.bind("<Leave>", on_leave)

    start_timer()
    root.mainloop()

def show_desktop_hud(title, source="속보", link=None, position="top-center", duration_sec=7):
    """
    독립 백그라운드 프로세스로 HUD 창을 띄워 메인 서버와 Tcl/Tk가 절대 충돌하지 않도록 보장
    """
    if sys.platform != 'win32' or os.environ.get('RENDER'):
        return
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller exe 환경
            exe_path = sys.executable
            args = [exe_path, '--hud', str(title), str(source), str(link or ''), str(position), str(duration_sec)]
            subprocess.Popen(args, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        else:
            # 파이썬 개발 환경
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'desktop_hud.py')
            args = [sys.executable, script_path, str(title), str(source), str(link or ''), str(position), str(duration_sec)]
            subprocess.Popen(args)
    except Exception as e:
        # 서브프로세스 실패 시 백업으로 스레드 실행
        try:
            import threading
            threading.Thread(target=run_hud_window, args=(title, source, link, position, duration_sec), daemon=True).start()
        except Exception:
            pass

if __name__ == "__main__":
    # 커맨드라인에서 직접 호출된 경우 (독립 프로세스 모드)
    title_arg = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != '--hud' else (sys.argv[2] if len(sys.argv) > 2 else "속보 헤드라인 테스트")
    src_arg = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] != '--hud' else (sys.argv[3] if len(sys.argv) > 3 else "속보")
    link_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[1] != '--hud' else (sys.argv[4] if len(sys.argv) > 4 else "http://localhost:5000")
    pos_arg = sys.argv[4] if len(sys.argv) > 4 and sys.argv[1] != '--hud' else (sys.argv[5] if len(sys.argv) > 5 else "top-center")
    dur_arg = 7
    if len(sys.argv) > 5 and sys.argv[1] != '--hud':
        try: dur_arg = int(sys.argv[5])
        except Exception: pass
    elif len(sys.argv) > 6:
        try: dur_arg = int(sys.argv[6])
        except Exception: pass

    run_hud_window(title_arg, src_arg, link_arg, pos_arg, dur_arg)
