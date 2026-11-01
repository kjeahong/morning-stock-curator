# -*- coding: utf-8 -*-
"""
HTS 전체화면 및 43인치 대형 모니터 맞춤형 Always-on-Top 속보 HUD 오버레이
브라우저를 내려놓아도 HTS 화면 바로 위 정중앙에 큼직한 속보창을 띄웁니다.
"""

import sys
import time
import webbrowser
import threading
import tkinter as tk

_current_hud_root = None
_hud_lock = threading.Lock()

def show_desktop_hud(title, source="속보", link=None, position="top-center", duration_sec=7):
    """
    Windows 바탕화면 최상단(HTS 등 전체화면 앱 위)에 속보 HUD 알림창 표시
    :param title: 기사 헤드라인 제목
    :param source: 언론사 출처 (예: 한국경제, 연합뉴스)
    :param link: 기사 원문 URL
    :param position: 'top-center' (상단 중앙) 또는 'center' (화면 정중앙) 또는 'bottom-right'
    :param duration_sec: 자동 닫힘 시간(초)
    """
    def _run():
        global _current_hud_root
        with _hud_lock:
            # 기존에 열려 있는 알림창이 있다면 안전하게 닫기
            if _current_hud_root:
                try:
                    _current_hud_root.after(0, _current_hud_root.destroy)
                except Exception:
                    pass
                _current_hud_root = None

        root = tk.Tk()
        with _hud_lock:
            _current_hud_root = root

        root.title("MorningStockCurator_HUD")
        root.overrideredirect(True) # 윈도우 타이틀바/테두리 제거
        root.attributes('-topmost', True) # HTS 화면 위에 항상 최상위 유지

        # 43인치 고해상도(UHD/QHD) 맞춤 크기
        w = 720
        h = 105
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()

        if position == 'center':
            x = (sw - w) // 2
            y = (sh - h) // 2
        elif position == 'bottom-right':
            x = sw - w - 30
            y = sh - h - 60
        else: # 기본: top-center (화면 상단 정중앙)
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

        def do_close():
            global _current_hud_root
            with _hud_lock:
                if _current_hud_root == root:
                    _current_hud_root = None
            try:
                root.destroy()
            except Exception:
                pass

        btn_close = tk.Label(header, text=" ✕ 닫기 ", bg="#1e293b", fg="#cbd5e1", font=("맑은 고딕", 9, "bold"), cursor="hand2", padx=6, pady=1)
        btn_close.pack(side="right")
        btn_close.bind("<Button-1>", lambda e: do_close())

        # 4. 헤드라인 제목 (43인치에서 아주 시원한 14pt 굵은 볼드 폰트)
        clean_title = title.replace('\n', ' ').strip()
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
            if link:
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

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    return th

if __name__ == "__main__":
    print("Desktop HUD test running...")
    show_desktop_hud("현대차그룹 아틀라스 휴머노이드 로봇 부품 공급망 본격 가동 소식", source="매일경제", link="https://news.naver.com")
    time.sleep(3)
    print("Done!")
