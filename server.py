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
from desktop_hud import show_desktop_hud
import tunnel_helper
import threading
import time

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
    query = request.query.get('q', '').strip()
    try:
        if query:
            # 키워드가 전달되면 장중 영구 아카이브 DB에서 고속 검색
            news = collector.search_news_archive(query=query, limit=300)
        else:
            news = collector.get_all_news(force_refresh=force)
        return json_response({'status': 'ok', 'count': len(news), 'news': news, 'data': news})
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'news': [], 'data': []})

@app.route('/api/news/archive')
def api_news_archive():
    query = request.query.get('q', '').strip()
    limit = int(request.query.get('limit', 250))
    try:
        news = collector.search_news_archive(query=query, limit=limit)
        return json_response({'status': 'ok', 'count': len(news), 'news': news})
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'news': []})

@app.route('/api/sihwang/issues')
def api_sihwang_issues():
    force = request.query.get('refresh', '0') == '1'
    try:
        import importlib
        importlib.reload(collector)
        data = collector.get_sihwangkase_issues(force_refresh=force)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'hot_mentions': [], 'issues': []})

@app.route('/api/sihwang/watchlist')
def api_sihwang_watchlist():
    force = request.query.get('refresh', '0') == '1'
    try:
        data = collector.get_sihwangkase_watchlist(force_refresh=force)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'groups': []})

@app.route('/api/stock/detail')
def api_stock_detail():
    code = request.query.get('code', '').strip()
    try:
        data = collector.get_stock_detail(code)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

@app.route('/api/stock/chart')
def api_stock_chart():
    code = request.query.get('code', '').strip()
    try:
        data = collector.get_stock_chart(code)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'rows': []})

@app.route('/api/macro')
def api_macro():
    force = request.query.get('refresh', '0') == '1'
    try:
        data = collector.get_macro_data(force_refresh=force)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'items': []})

@app.route('/api/futures/indicators')
@app.route('/api/indicators')
def api_indicators():
    force = request.query.get('refresh', '0') == '1'
    try:
        data = collector.get_indicators_data(force_refresh=force)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

@app.route('/api/calendar')
def api_calendar():
    force = request.query.get('refresh', '0') == '1'
    month = request.query.get('month', '').strip()
    try:
        data = collector.get_calendar_data(month=month, force_refresh=force)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'events': []})

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@app.route('/api/network/info')
def api_network_info():
    ip = get_local_ip()
    port = request.environ.get('SERVER_PORT', 5000)
    t_status = tunnel_helper.get_tunnel_status()
    return json_response({
        'status': 'ok',
        'local_ip': ip,
        'port': port,
        'local_url': f"http://{ip}:{port}",
        'tunnel': t_status,
        'tip': '같은 Wi-Fi(공유기)에 연결된 스마트폰, 태블릿, PC 브라우저에서 위 주소로 바로 접속할 수 있습니다.'
    })

@app.route('/api/tunnel/start')
def api_tunnel_start():
    port = int(request.environ.get('SERVER_PORT', 5000))
    res = tunnel_helper.start_tunnel(port)
    return json_response(res)

@app.route('/api/tunnel/status')
def api_tunnel_status():
    res = tunnel_helper.get_tunnel_status()
    return json_response(res)

@app.route('/api/tunnel/stop')
def api_tunnel_stop():
    res = tunnel_helper.stop_tunnel()
    return json_response(res)

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
        force = request.query.get('refresh', '0') == '1'
        data = collector.get_charts_data(force_refresh=force)
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

@app.route('/api/aftermarket')
def api_aftermarket():
    force = request.query.get('refresh', '0') == '1'
    try:
        import importlib
        importlib.reload(collector)
        data = collector.get_aftermarket_data(force_refresh=force)
        return json_response(data)
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e), 'rising': [], 'falling': []})

@app.route('/api/refresh', method=['GET', 'POST'])
def api_refresh():
    try:
        collector._cache['news'] = []
        collector._cache['indices'] = {}
        collector._cache['last_news_time'] = 0
        collector._cache['last_indices_time'] = 0
        collector._aftermarket_cache['data'] = None
        collector._aftermarket_cache['last_time'] = 0
        news = collector.get_all_news(force_refresh=True)
        indices = collector.get_market_indices()
        aftermarket = collector.get_aftermarket_data(force_refresh=True)
        return json_response({
            'status': 'ok', 
            'news_count': len(news), 
            'news': news,
            'indices': indices,
            'aftermarket': aftermarket
        })
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

@app.route('/api/trigger_hud', method=['GET', 'POST'])
def api_trigger_hud():
    """브라우저 또는 외부 호출을 받아 바탕화면 최상단(HTS 위)에 큼직한 HUD 속보창 표시"""
    try:
        data = request.json or {}
        title = data.get('title') or request.params.get('title', '실시간 증시 속보')
        source = data.get('source') or request.params.get('source', '속보')
        link = data.get('link') or request.params.get('link', '')
        pos = data.get('position') or request.params.get('position', 'top-center')
        show_desktop_hud(title=title, source=source, link=link, position=pos)
        return json_response({'status': 'ok'})
    except Exception as e:
        return json_response({'status': 'error', 'message': str(e)})

_seen_news_ids = set()
_watcher_initialized = False

def background_news_watcher():
    """브라우저를 내려놓거나 닫아두어도 HTS 위로 실시간 속보창을 띄워주는 독립 백그라운드 감시기"""
    global _watcher_initialized
    time.sleep(3)
    while True:
        try:
            news_list = collector.get_all_news(force_refresh=True)
            if not _watcher_initialized:
                for it in news_list:
                    _seen_news_ids.add(it['id'])
                _watcher_initialized = True
            else:
                new_items = [it for it in news_list if it['id'] not in _seen_news_ids]
                for it in new_items:
                    _seen_news_ids.add(it['id'])
                if new_items:
                    latest = new_items[0]
                    show_desktop_hud(
                        title=latest['title'],
                        source=latest.get('source', '속보'),
                        link=latest.get('link', ''),
                        position='top-center',
                        duration_sec=7
                    )
        except Exception:
            pass
        try:
            # 평일 장중(08:40~15:50)에는 미결제약정·프로그램 비차익 일중 추이를 백그라운드 자동 누적
            from datetime import datetime as _dt
            _now = _dt.now()
            _hm = _now.hour * 100 + _now.minute
            if _now.weekday() < 5 and 840 <= _hm <= 1550:
                collector.get_indicators_data(force_refresh=True)
        except Exception:
            pass
        time.sleep(30)


import socket

def find_free_port(start_port=5000):
    for port in range(start_port, start_port + 5):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('127.0.0.1', port))
            s.close()
            return port
        except Exception:
            s.close()
            continue
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
    # 1. 만약 --hud 인자로 호출된 경우: 웹 서버가 아니라 단독 속보 HUD 창만 띄우고 즉시 종료!
    if len(sys.argv) > 1 and sys.argv[1] == '--hud':
        title = sys.argv[2] if len(sys.argv) > 2 else "실시간 증시 속보"
        source = sys.argv[3] if len(sys.argv) > 3 else "속보"
        link = sys.argv[4] if len(sys.argv) > 4 else ""
        pos = sys.argv[5] if len(sys.argv) > 5 else "top-center"
        dur = 7
        if len(sys.argv) > 6:
            try: dur = int(sys.argv[6])
            except Exception: pass
        from desktop_hud import run_hud_window
        run_hud_window(title, source, link, pos, dur)
        sys.exit(0)
    # 이미 서버가 실행 중인 경우 브라우저만 띄우고 종료
    if check_already_running(5000):
        webbrowser.open('http://localhost:5000')
        sys.exit(0)

    port = find_free_port(5000)
    local_ip = get_local_ip()
    print("=" * 60)
    print(f"[Morning Stock Radar] 모닝 증시 큐레이터 서버 시작...")
    print(f"▶ 로컬 PC 브라우저 주소: http://localhost:{port}")
    print(f"▶ 같은 Wi-Fi 제자/스마트폰/태블릿 접속 주소: http://{local_ip}:{port}")
    print("잠시 후 브라우저가 자동으로 열립니다. (창을 닫으면 종료)")
    print("=" * 60)
    
    # 1.5초 후 브라우저 자동 오픈
    Timer(1.5, open_browser, args=[port]).start()
    
    # HTS 위 속보 오버레이 백그라운드 감시 스레드 시작
    threading.Thread(target=background_news_watcher, daemon=True).start()
    
    # 멀티스레드 WSGI 서버 어댑터 (동시 접속 및 모바일 제자 접속 시 블로킹 방지)
    from wsgiref.simple_server import WSGIServer, make_server
    from socketserver import ThreadingMixIn

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    import bottle
    class ThreadedWSGIRefServer(bottle.ServerAdapter):
        def run(self, handler):
            server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
            server.serve_forever()

    # 서버 실행 (0.0.0.0으로 바인딩하여 동일 공유기/와이파이 내 모바일 및 타 기기 접근 허용)
    run(app, host='0.0.0.0', port=port, server=ThreadedWSGIRefServer, quiet=True)
