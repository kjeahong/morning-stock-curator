# -*- coding: utf-8 -*-
"""
모닝 증시 큐레이터 로컬 웹 서버 (server.py)
"""

import sys
import os

class SafeWriter:
    def write(self, text):
        pass
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = SafeWriter()
elif hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = SafeWriter()
elif hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import json
import socket
import urllib.request
import webbrowser
from threading import Timer
from bottle import Bottle, run, request, response, static_file
import collector

app = Bottle()

if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def json_response(data):
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(data, ensure_ascii=False)

@app.route('/')
def index():
    disk_template = os.path.join(r'C:\Users\Administrator\Desktop\Overhang', 'templates', 'index.html')
    if os.path.exists(disk_template):
        with open(disk_template, 'r', encoding='utf-8') as f:
            return f.read()
    html_path = os.path.join(BASE_DIR, 'templates', 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/static/<filename:path>')
def serve_static(filename):
    return static_file(filename, root=os.path.join(BASE_DIR, 'static'))

@app.route('/api/indices')
def api_indices():
    try:
        indices = collector.get_market_indices()
        return json_response({'status': 'ok', 'data': indices})
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'data': []})

@app.route('/api/news')
def api_news():
    force = request.query.get('refresh', '0') == '1'
    try:
        news = collector.get_all_news(force_refresh=force)
        return json_response({'status': 'ok', 'count': len(news), 'news': news, 'data': news})
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'news': [], 'data': []})

@app.route('/mini')
def mini_window():
    disk_mini = os.path.join(r'C:\Users\Administrator\Desktop\Overhang', 'templates', 'mini.html')
    if os.path.exists(disk_mini):
        with open(disk_mini, 'r', encoding='utf-8') as f:
            return f.read()
    template_path = os.path.join(BASE_DIR, 'templates', 'mini.html')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Mini window template not found."

@app.route('/api/charts')
def api_charts():
    try:
        import importlib
        importlib.reload(collector)
        data = collector.get_charts_data()
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

@app.route('/api/closing')
def api_closing():
    try:
        import importlib
        importlib.reload(collector)
        data = collector.get_closing_market_data()
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

@app.route('/api/refresh', method=['GET', 'POST'])
def api_refresh():
    try:
        collector._cache['news'] = []
        collector._cache['indices'] = {}
        collector._cache['last_news_time'] = 0
        collector._cache['last_indices_time'] = 0
        news = collector.get_all_news(force_refresh=True)
        indices = collector.get_market_indices()
        return json_response({
            'status': 'ok', 
            'news_count': len(news), 
            'news': news,
            'indices': indices
        })
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

import socket

def find_free_port(start_port=5000):
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

def open_browser(port):
    webbrowser.open(f'http://localhost:{port}')

def check_already_running(port=5000):
    try:
        url = f'http://127.0.0.1:{port}/'
        req = urllib.request.Request(url, headers={'User-Agent': 'HealthCheck'})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False

if __name__ == '__main__':
    # 이미 서버가 실행 중인 경우 브라우저만 띄우고 종료
    if check_already_running(5000):
        webbrowser.open('http://localhost:5000')
        sys.exit(0)

    port = find_free_port(5000)
    print("=" * 60)
    print(f"[Morning Stock Radar] 모닝 증시 큐레이터 서버 시작...")
    print(f"웹 브라우저 주소: http://localhost:{port}")
    print("잠시 후 브라우저가 자동으로 열립니다. (창을 닫으면 종료)")
    print("=" * 60)
    
    # 1.5초 후 브라우저 자동 오픈
    Timer(1.5, open_browser, args=[port]).start()
    
    # 서버 실행
    run(app, host='127.0.0.1', port=port, quiet=True)
