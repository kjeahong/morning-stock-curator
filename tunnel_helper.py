# -*- coding: utf-8 -*-
"""
Cloudflare Quick Tunnel Helper (비용 0원 영구 무료 외부 원격 접속 관리자)
"""

import os
import sys
import subprocess
import threading
import time
import re

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED_BIN = os.path.join(CURRENT_DIR, 'cloudflared.exe')

_tunnel_proc = None
_tunnel_url = ""
_tunnel_status = "stopped"  # "stopped", "starting", "running", "error"
_tunnel_lock = threading.Lock()

def get_cloudflared_path():
    # 1. PyInstaller 패키징 환경
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        p = os.path.join(exe_dir, 'cloudflared.exe')
        if os.path.exists(p):
            return p
        meipass = getattr(sys, '_MEIPASS', '')
        p2 = os.path.join(meipass, 'cloudflared.exe')
        if os.path.exists(p2):
            return p2
    # 2. 작업 디렉토리 및 스크립트 디렉토리
    candidates = [
        os.path.join(r'C:\Users\Administrator\Desktop\Overhang', 'cloudflared.exe'),
        CLOUDFLARED_BIN,
        os.path.join(os.getcwd(), 'cloudflared.exe'),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # 3. 시스템 PATH
    import shutil
    p_sys = shutil.which('cloudflared')
    if p_sys:
        return p_sys
    return None

def get_tunnel_status():
    global _tunnel_proc, _tunnel_url, _tunnel_status
    with _tunnel_lock:
        if _tunnel_proc is not None:
            if _tunnel_proc.poll() is not None:
                # 프로세스가 비정상 종료됨
                _tunnel_status = "stopped"
                _tunnel_proc = None
                _tunnel_url = ""
        return {
            'status': _tunnel_status,
            'url': _tunnel_url,
            'available': get_cloudflared_path() is not None
        }

def start_tunnel(port=5000):
    global _tunnel_proc, _tunnel_url, _tunnel_status
    with _tunnel_lock:
        if _tunnel_status == "running" and _tunnel_url:
            return {'status': 'running', 'url': _tunnel_url}
        if _tunnel_status == "starting":
            return {'status': 'starting', 'url': ''}

        bin_path = get_cloudflared_path()
        if not bin_path:
            return {'status': 'error', 'message': 'cloudflared.exe를 찾을 수 없습니다.'}

        _tunnel_status = "starting"
        _tunnel_url = ""

    def _worker():
        global _tunnel_proc, _tunnel_url, _tunnel_status
        try:
            cmd = [bin_path, 'tunnel', '--url', f'http://127.0.0.1:{port}']
            # Windows에서 콘솔 창 숨기기 플래그
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=creationflags
            )

            with _tunnel_lock:
                _tunnel_proc = proc

            found_url = ""
            start_t = time.time()
            while time.time() - start_t < 25:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                    continue

                m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if m:
                    found_url = m.group(0)
                    break

            with _tunnel_lock:
                if found_url and proc.poll() is None:
                    _tunnel_url = found_url
                    _tunnel_status = "running"
                    print(f"[Tunnel] 외부 무료 접속 URL 활성화: {_tunnel_url}")
                else:
                    _tunnel_status = "error"
                    _tunnel_proc = None

            # 프로세스 대기
            proc.wait()
            with _tunnel_lock:
                _tunnel_status = "stopped"
                _tunnel_proc = None
                _tunnel_url = ""
        except Exception as e:
            with _tunnel_lock:
                _tunnel_status = "error"
                _tunnel_proc = None
                _tunnel_url = ""
            print(f"[Tunnel Error] {e}")

    threading.Thread(target=_worker, daemon=True).start()

    # 최대 6초 대기하면서 URL이 나오는지 확인
    for _ in range(12):
        time.sleep(0.5)
        st = get_tunnel_status()
        if st['status'] == 'running' and st['url']:
            return st
        elif st['status'] == 'error':
            return {'status': 'error', 'message': '터널 연결 중 오류가 발생했습니다.'}

    return get_tunnel_status()

def stop_tunnel():
    global _tunnel_proc, _tunnel_url, _tunnel_status
    with _tunnel_lock:
        if _tunnel_proc is not None:
            try:
                _tunnel_proc.terminate()
                _tunnel_proc.wait(timeout=2)
            except Exception:
                try:
                    _tunnel_proc.kill()
                except Exception:
                    pass
            _tunnel_proc = None
        _tunnel_status = "stopped"
        _tunnel_url = ""
    return {'status': 'stopped', 'url': ''}
