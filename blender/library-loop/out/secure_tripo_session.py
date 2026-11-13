"""One-use loopback form; the API key exists in process memory only."""
import contextlib
import html
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / 'out' / 'tripo-generation.ready'
previous_url = (ROOT / 'out' / 'tripo-session-url.txt').read_text().strip() if (ROOT / 'out' / 'tripo-session-url.txt').exists() else ''
previous = urlsplit(previous_url)
TOKEN = previous.path.lstrip('/') if previous.hostname == '127.0.0.1' else secrets.token_urlsafe(24)
STATE = {'phase': '等待在此页面输入国内站 API Key', 'submitted': False, 'done': False}
CREDENTIAL = ''
LOCK = threading.Lock()
BASE = 'https://openapi.tripo3d.com/v3'


def clean(value):
    value = str(value)
    secret = os.environ.get('TRIPO_API_KEY') or CREDENTIAL
    return value.replace(secret, '[REDACTED]') if secret else value


class SafeStream:
    def __init__(self, stream):
        self.stream = stream
    def write(self, value):
        return self.stream.write(clean(value))
    def flush(self):
        self.stream.flush()


def phase(message):
    STATE['phase'] = clean(message)
    print(STATE['phase'], flush=True)


def balance():
    spec = importlib.util.spec_from_file_location('tripo_balance', ROOT / 'scripts' / 'tripo_batch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.call('GET', '/account/balance')
    if not isinstance(data.get('balance'), (int, float)) or not isinstance(data.get('frozen'), (int, float)):
        raise RuntimeError('Unexpected balance fields: ' + clean(json.dumps(data)))
    return {'balance': data['balance'], 'frozen': data['frozen']}


def worker():
    global CREDENTIAL
    started = time.monotonic()
    os.environ['TRIPO_API_KEY'] = CREDENTIAL
    CREDENTIAL = ''
    os.environ['TRIPO_API_BASE'] = BASE
    os.environ['TRIPO_ANALYTICS_ENABLED'] = '0'
    STATE['failed'] = False
    STATE['done'] = False
    try:
        phase('正在只读核对国内账号余额。')
        before = balance()
        phase('国内账号余额：可用 %s，冻结 %s。' % (before['balance'], before['frozen']))
        if before['balance'] < 300:
            raise RuntimeError('Insufficient available credits for the approved 300-credit plan')
        phase('密钥已在内存中就绪，等待本机脚本检查完成；生成预算 300 积分。')
        deadline = time.monotonic() + 3600
        while not READY.is_file():
            if time.monotonic() >= deadline:
                raise TimeoutError('Preparation timed out; no generation was submitted')
            time.sleep(1)
        READY.unlink()
        phase('开始已确认的五尊雕像、每尊两版生成；发生错误即停止。')
        spec = importlib.util.spec_from_file_location('tripo_batch', ROOT / 'scripts' / 'tripo_batch.py')
        batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(batch)
        sys.argv = ['tripo_batch.py', '--variants', '2', '--max-credits', '300']
        with contextlib.redirect_stdout(SafeStream(sys.stdout)), contextlib.redirect_stderr(SafeStream(sys.stderr)):
            batch.main()
        after = balance()
        initial_path = ROOT / 'out' / 'tripo-initial-balance.json'
        initial = json.loads(initial_path.read_text()) if initial_path.exists() else before
        billing = {'before': initial, 'session_before': before, 'after': after, 'balance_difference': initial['balance'] - after['balance'],
                   'elapsed_seconds': round(time.monotonic() - started, 2)}
        (ROOT / 'out' / 'tripo-billing.json').write_text(json.dumps(billing, indent=2) + '\n')
        phase('生成完成。余额核对：' + json.dumps(billing, ensure_ascii=False))
    except BaseException as exc:
        detail = clean(str(exc))
        if hasattr(exc, 'read'):
            try:
                detail += '\n' + clean(exc.read().decode(errors='replace'))
            except Exception:
                pass
        phase('STOPPED: ' + type(exc).__name__ + ': ' + detail)
        READY.unlink(missing_ok=True)
        STATE['failed'] = True
    finally:
        if not STATE.get('failed'):
            os.environ.pop('TRIPO_API_KEY', None)
        CREDENTIAL = ''
        STATE['done'] = True
        STATE['finished_at'] = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def send_page(self, code, body):
        encoded = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(encoded)
    def allowed(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}' and self.path == '/' + TOKEN
    def do_GET(self):
        if not self.allowed():
            return self.send_page(404, 'Not found')
        form = '' if STATE['submitted'] else f'''<form method="post" action="/{TOKEN}" autocomplete="off">
        <input type="hidden" name="csrf" value="{TOKEN}">
        <label>国内站 API Key<input type="password" name="api_key" autocomplete="new-password" required maxlength="512"></label>
        <button type="submit">提交密钥，执行已确认的 300 积分计划</button></form>'''
        refresh = '<meta http-equiv="refresh" content="5">' if STATE['submitted'] and not STATE['done'] else ''
        self.send_page(200, f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">{refresh}<title>Tripo 本机安全输入</title>
        <style>body{{font:17px system-ui;max-width:680px;margin:60px auto;padding:24px;background:#f5f7fa;color:#172336}}
        input,button{{display:block;width:100%;box-sizing:border-box;margin:16px 0;padding:14px;font:inherit}}button{{background:#155ccc;color:white;border:0;border-radius:8px}}pre{{white-space:pre-wrap}}</style>
        <h1>Tripo 本机安全输入</h1><p>五尊雕像，各生成两版；已确认预算 300 积分。仅使用国内站接口。</p>
        <p>密钥只在本机进程内存中使用，不写入文件、日志或聊天。进程结束后释放。</p>
        {form}<pre>{html.escape(STATE['phase'])}</pre></html>''')
    def do_POST(self):
        global CREDENTIAL
        if not self.allowed():
            return self.send_page(403, 'Forbidden')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send_page(400, 'Invalid request')
        if not 0 < length <= 2048 or not self.headers.get('Content-Type','').startswith('application/x-www-form-urlencoded'):
            return self.send_page(400, 'Invalid request')
        values = parse_qs(self.rfile.read(length).decode())
        csrf = values.pop('csrf', [''])[0]
        if not secrets.compare_digest(csrf, TOKEN):
            values.clear()
            return self.send_page(403, '页面版本已更新，请刷新后重新输入。')
        key = values.pop('api_key', [''])[0].strip()
        values.clear()
        if not key.startswith('tsk_') or len(key) > 512:
            key = ''
            return self.send_page(400, '请输入国内开发者平台的 API Key（tsk_ 开头）；请返回上一页重填。')
        with LOCK:
            if STATE['submitted']:
                key = ''
                return self.send_page(409, '已提交，不能重复提交。')
            CREDENTIAL = key
            key = ''
            STATE['submitted'] = True
        self.send_response(303)
        self.send_header('Location', '/' + TOKEN)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', '0')
        self.end_headers()
        threading.Thread(target=worker, daemon=True).start()


server = ThreadingHTTPServer(('127.0.0.1', previous.port if previous.hostname == '127.0.0.1' else 0), Handler)
server.timeout = 1
url = f'http://127.0.0.1:{server.server_port}/{TOKEN}'
(ROOT / 'out' / 'tripo-session-url.txt').write_text(url + '\n')
print('SECURE_INPUT_URL=' + url, flush=True)
expiry = time.monotonic() + 3600
while time.monotonic() < expiry:
    server.handle_request()
    if STATE.get('failed') and STATE['done'] and READY.is_file():
        CREDENTIAL = os.environ.get('TRIPO_API_KEY', '')
        STATE['done'] = False
        threading.Thread(target=worker, daemon=True).start()
    if STATE['done'] and not STATE.get('failed') and time.monotonic() - STATE['finished_at'] > 10:
        break
server.server_close()
os.environ.pop('TRIPO_API_KEY', None)
CREDENTIAL = ''
sys.exit(1 if STATE.get('failed') or not STATE['done'] else 0)
