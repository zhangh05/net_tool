#!/usr/bin/env python3
"""
NetTool Portal - 统一入口服务器
端口: 9000
功能: 登录认证 + 应用列表 + 反向代理到各子应用
"""
import os
import re
import json
import mimetypes
import hashlib
import secrets
import time
import http.server
import socketserver
import http.client
from urllib.parse import urlparse, parse_qs, unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NETTOOL_DIR = os.path.dirname(BASE_DIR)
PORT = 9000
STATIC_DIR = os.path.join(BASE_DIR, 'static')
SHARED_DIR = os.path.join(NETTOOL_DIR, 'shared')
USERS_FILE = os.path.join(SHARED_DIR, 'users.json')
COOKIE_SECRET = 'netool_sso_v1'
COOKIE_NAME = 'netool_session'
SESSION_TTL = 86400 * 7  # 7天

_sessions = {}

# ═══════════════════════════════════════════════════════════════════════════
# 认证模块
# ═══════════════════════════════════════════════════════════════════════════

def _hash_pwd(password):
    return hashlib.sha256((password + COOKIE_SECRET).encode()).hexdigest()

def _load_users():
    if not os.path.exists(USERS_FILE):
        return [{'id': 'root', 'username': 'root', 'password_hash': _hash_pwd('1234qazhh'), 'role': 'admin'}]
    try:
        with open(USERS_FILE, encoding='utf-8') as f:
            return json.load(f).get('users', [])
    except:
        return [{'id': 'root', 'username': 'root', 'password_hash': _hash_pwd('1234qazhh'), 'role': 'admin'}]

def _save_users(users):
    os.makedirs(SHARED_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': users}, f, indent=2, ensure_ascii=False)

def verify_login(username, password):
    pwd_hash = _hash_pwd(password)
    for u in _load_users():
        stored = u.get('password_hash', _hash_pwd(u.get('password', '')))
        if u['username'] == username and stored == pwd_hash:
            return {'id': u['id'], 'username': u['username'], 'role': u.get('role', 'user')}
    return None

def create_session(user_info):
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = {'user_id': user_info['id'], 'username': user_info['username'],
                       'role': user_info.get('role', 'user'), 'expire': time.time() + SESSION_TTL}
    return sid

def get_session(sid):
    if not sid or sid not in _sessions:
        return None
    s = _sessions[sid]
    if time.time() > s['expire']:
        del _sessions[sid]
        return None
    return s

def delete_session(sid):
    if sid in _sessions:
        del _sessions[sid]

def make_session_cookie(sid):
    age = SESSION_TTL if sid else 0
    return f'{COOKIE_NAME}={sid}; Path=/; Max-Age={age}; HttpOnly'

# ═══════════════════════════════════════════════════════════════════════════
# 用户管理 API
# ═══════════════════════════════════════════════════════════════════════════

def list_users():
    return [{'id': u['id'], 'username': u['username'], 'role': u.get('role', 'user'), 'created_at': u.get('created_at', '')}
            for u in _load_users()]

def create_user(username, password, role='user'):
    new_id = secrets.token_urlsafe(8)
    users = _load_users()
    users.append({'id': new_id, 'username': username, 'password_hash': _hash_pwd(password), 'role': role,
                   'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ')})
    _save_users(users)
    return {'id': new_id, 'username': username, 'role': role}

def delete_user(user_id):
    users = _load_users()
    for i, u in enumerate(users):
        if u['id'] == user_id:
            if u['username'] == 'root':
                return False
            users.pop(i)
            _save_users(users)
            return True
    return False

def update_user(user_id, password=None, role=None):
    users = _load_users()
    for u in users:
        if u['id'] == user_id:
            if password:
                u['password_hash'] = _hash_pwd(password)
            if role and u['username'] != 'root':
                u['role'] = role
            _save_users(users)
            return True
    return False

# ═══════════════════════════════════════════════════════════════════════════
# 应用发现
# ═══════════════════════════════════════════════════════════════════════════

def discover_apps():
    apps = []
    for name in os.listdir(NETTOOL_DIR):
        manifest_path = os.path.join(NETTOOL_DIR, name, 'manifest.json')
        if os.path.isdir(os.path.join(NETTOOL_DIR, name)) and os.path.exists(manifest_path):
            try:
                with open(manifest_path, encoding='utf-8') as f:
                    m = json.load(f)
                m['_path'] = name
                apps.append(m)
            except:
                pass
    apps.sort(key=lambda a: a.get('order', 99))
    return apps

# ═══════════════════════════════════════════════════════════════════════════
# 模板渲染
# ═══════════════════════════════════════════════════════════════════════════

def render(template_name, **kwargs):
    path = os.path.join(BASE_DIR, 'templates', template_name)
    if not os.path.exists(path):
        return b'404'
    with open(path, encoding='utf-8') as f:
        content = f.read()
    for k, v in kwargs.items():
        # 条件块 {{#if key}}...{{/if}}
        if str(v).strip():
            content = re.sub(r'\{\{#if\s+' + re.escape(k) + r'\}\}(.*?)\{\{/if\}\}', r'\1', content)
        else:
            content = re.sub(r'\{\{#if\s+' + re.escape(k) + r'\}\}.*?\{\{/if\}\}', '', content, flags=re.DOTALL)
        content = content.replace('{{' + k + '}}', str(v))
    return content.encode('utf-8')

# ═══════════════════════════════════════════════════════════════════════════
# 反向代理
# ═══════════════════════════════════════════════════════════════════════════

def _app_dir(app_name):
    """获取应用目录，优先框架内，fallback到 /root/{app_name}/"""
    d = os.path.join(NETTOOL_DIR, app_name)
    if os.path.exists(os.path.join(d, 'manifest.json')):
        return d
    # Fallback: 外部独立应用（如 /root/netops/）
    ext = f'/root/{app_name}'
    if os.path.exists(os.path.join(ext, 'manifest.json')):
        return ext
    return d


def proxy_to(session, path):
    """代理请求到子应用"""
    parts = path.strip('/').split('/')
    if not parts:
        return 404, {}, b'Not Found'
    
    app_name = parts[0]
    remaining = '/' + '/'.join(parts[1:])
    
    # 动态找 manifest（外部独立应用优先，因为文件更完整）
    manifest_paths_ordered = [
        os.path.join('/root', app_name, 'manifest.json'),       # 外部独立应用
        os.path.join(NETTOOL_DIR, app_name, 'manifest.json'),  # 框架内应用
    ]
    manifest_path = None
    for mp in manifest_paths_ordered:
        if os.path.exists(mp):
            # 同时检查该目录下是否有 index.html 或 manifest 指向的 port
            with open(mp, encoding='utf-8') as f:
                manifest = json.load(f)
            app_root_check = os.path.dirname(mp)
            # 优先用有 index.html 的目录
            if os.path.exists(os.path.join(app_root_check, 'index.html')) or manifest.get('port'):
                manifest_path = mp
                break
    
    if not manifest_path:
        return 404, {}, f'应用 {app_name} 不存在'.encode()
    
    # manifest已在上面的循环中加载完成，app_root 即为其目录
    app_root = os.path.dirname(manifest_path)
    app_port = manifest.get('port')
    if not app_port:
        return 500, {}, f'应用 {app_name} 未配置端口'.encode()
    
    # 静态文件: /appname/static/... → 从子应用目录读取
    static_prefix = f'/{app_name}/static/'
    if remaining.startswith(static_prefix):
        static_file = remaining[len(static_prefix):]
        full_path = os.path.join(app_root, 'static', static_file)
        if os.path.exists(full_path) and '..' not in static_file:
            mt, _ = mimetypes.guess_type(static_file)
            with open(full_path, 'rb') as f:
                body = f.read()
            return 200, [('Content-Type', mt or 'application/octet-stream'), ('Content-Length', str(len(body)))], body
        return 404, {}, b'Not Found'
    
    # HTML 首页: 注入 <base href="/appname/"> 修复相对路径
    if remaining == '/' or remaining == '':
        index_paths = [
            os.path.join(app_root, 'index.html'),
            os.path.join(app_root, 'templates', 'index.html'),
        ]
        for ip in index_paths:
            if os.path.exists(ip):
                with open(ip, 'rb') as f:
                    body = f.read()
                # 注入 base + 修复相对路径
                text = body.decode('utf-8', errors='ignore')
                if '<base href' not in text:
                    text = text.replace('<head>', f'<head>\n<base href="/{app_name}/">', 1)
                # 修复 /api/ /icons/ 等路径
                import re
                def fix_url(m):
                    prefix, path = m.group(1), m.group(2)
                    if path.startswith(f'/{app_name}/'):
                        return m.group(0)
                    return prefix + f'/{app_name}' + path
                text = re.sub(r'(src|href|url\(\s*["\']?)\s*(/[^"\')\s]*)', fix_url, text)
                body = text.encode('utf-8')
                return 200, [('Content-Type', 'text/html; charset=utf-8'), ('Content-Length', str(len(body)))], body
        return 404, {}, '首页不存在'.encode()
    
    # API 代理
    conn = http.client.HTTPConnection(f'127.0.0.1:{app_port}', timeout=15)
    headers = {'X-User-Id': session.get('user_id', ''),
              'X-Username': session.get('username', ''),
              'X-User-Role': session.get('role', ''),
              'Host': f'127.0.0.1:{app_port}'}
    
    try:
        conn.request('GET', remaining, headers=headers)
        resp = conn.getresponse()
        resp_headers = [(k, v) for k, v in resp.getheaders() if k.lower() not in ('transfer-encoding', 'connection')]
        return resp.status, resp_headers, resp.read()
    except Exception as e:
        return 502, {}, f'代理失败: {e}'.encode()
    finally:
        conn.close()

# ═══════════════════════════════════════════════════════════════════════════
# HTTP 请求处理
# ═══════════════════════════════════════════════════════════════════════════

class Handler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")
    
    def get_session(self):
        cookies = {}
        for part in self.headers.get('Cookie', '').split(';'):
            k, _, v = part.strip().partition('=')
            cookies[k.strip()] = v.strip()
        return get_session(cookies.get(COOKIE_NAME))
    
    def parse_post_data(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode('utf-8')
        args = {}
        for part in body.split('&'):
            k, _, v = part.partition('=')
            args[k] = unquote(v)
        return args
    
    def send_html(self, status, body, headers=None):
        headers = headers or []
        headers += [('Content-Type', 'text/html; charset=utf-8'), ('Content-Length', str(len(body)))]
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
    
    def send_json(self, status, body, headers=None):
        headers = headers or []
        headers += [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))]
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())
    
    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def do_GET(self):
        path = unquote(self.path.split('?')[0])
        session = self.get_session()
        
        # 静态文件
        if path.startswith('/static/'):
            filepath = path[8:]
            full = os.path.join(STATIC_DIR, filepath)
            if os.path.exists(full) and '..' not in filepath:
                mt, _ = mimetypes.guess_type(full)
                with open(full, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mt or 'application/octet-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_html(404, b'404 Not Found')
            return
        
        # 登出
        if path == '/logout/':
            cookies = {}
            for part in self.headers.get('Cookie', '').split(';'):
                k, _, v = part.strip().partition('=')
                cookies[k.strip()] = v.strip()
            delete_session(cookies.get(COOKIE_NAME))
            self.send_response(302)
            self.send_header('Location', '/login/')
            self.send_header('Set-Cookie', f'{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly')
            self.end_headers()
            return
        
        # 需要登录
        if not session and path not in ('/login/', '/login'):
            self.redirect('/login/')
            return
        
        # 登录页
        if path in ('/login/', '/login'):
            self.send_html(200, render('login.html'))
            return
        
        # 管理面板 /admin/
        if path in ('/admin/', '/admin'):
            self.send_html(200, render('admin.html', username=session.get('username', ''), role=session.get('role', '')))
            return
        
        # 用户 API
        if path.startswith('/api/'):
            if session.get('role') != 'admin':
                self.send_json(403, '{"error":"需要管理员权限"}')
                return
            
            if path == '/api/users/':
                self.send_json(200, json.dumps(list_users(), ensure_ascii=False))
                return
        
        # 子应用路由: /appname/... 或 /appname (排除认证和应用内路径)
        first_seg = path.strip('/').split('/')[0]
        if first_seg and first_seg not in ('login', 'logout', 'api', 'static', 'favicon.ico'):
            status, resp_headers, body = proxy_to(session, path)
            status, resp_headers, body = proxy_to(session, path)
            self.send_response(status)
            for k, v in resp_headers:
                if k.lower() not in ('transfer-encoding',):
                    self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)
            return
        
        # 首页: 应用列表
        apps = discover_apps()
        app_cards = ''
        for app in apps:
            app_path = app.get('_path', '')
            app_cards += f'''
        <div class="app-card" onclick="goApp('{app_path}')">
            <div class="app-icon">{app.get('icon_emoji', '📦')}</div>
            <div class="app-name">{app.get('name', '')}</div>
            <div class="app-desc">{app.get('description', '')}</div>
            <div class="app-version">v{app.get('version', '1.0')}</div>
        </div>'''
        
        self.send_html(200, render('index.html',
            username=session.get('username', 'Guest'),
            role=session.get('role', 'user'),
            is_admin='1' if session.get('role') == 'admin' else '',
            app_cards=app_cards,
            year=2026
        ))
    
    def do_POST(self):
        path = unquote(self.path.split('?')[0])
        
        if path in ('/login/', '/login'):
            args = self.parse_post_data()
            user = verify_login(args.get('username', ''), args.get('password', ''))
            if user:
                sid = create_session(user)
                self.send_response(302)
                self.send_header('Location', '/')
                self.send_header('Set-Cookie', make_session_cookie(sid))
                self.end_headers()
            else:
                body = render('login.html', error='<div class="error-msg">用户名或密码错误</div>')
                self.send_html(200, body)
            return
        
        # Portal API: /api/users/ POST/PUT/DELETE
        if path.startswith('/api/'):
            session = self.get_session()
            if session.get('role') != 'admin':
                self.send_json(403, '{"error":"需要管理员权限"}')
                return
            if path == '/api/users/' and self.command == 'POST':
                args = self.parse_post_data()
                if not args.get('username') or not args.get('password'):
                    self.send_json(400, '{"error":"缺少参数"}')
                    return
                user = create_user(args['username'], args['password'], args.get('role', 'user'))
                self.send_json(201, json.dumps(user, ensure_ascii=False))
                return
            self.send_json(404, '{"error":"未找到"}')
            return
        
        # 子应用 POST
        first_seg = path.strip('/').split('/')[0]
        if first_seg and first_seg not in ('login', 'logout', 'api', 'static', 'favicon.ico'):
            if self.get_session():
                self.proxy_request('POST')
                return
        self.send_response(405)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Method Not Allowed')


def _proxy_method(meth):
    def do_method(self):
        path = unquote(self.path.split('?')[0])
        first_seg = path.strip('/').split('/')[0]
        
        # Portal API: PUT /api/users/:id
        if path.startswith('/api/') and meth == 'PUT':
            session = self.get_session()
            if not session or session.get('role') != 'admin':
                self.send_json(403, '{"error":"需要管理员权限"}')
                return
            if path.startswith('/api/users/'):
                uid = path.split('/')[-1]
                args = self.parse_post_data()
                update_user(uid, password=args.get('password') or None, role=args.get('role') or None)
                self.send_json(200, '{"ok":true}')
                return
            self.send_json(404, '{"error":"未找到"}')
            return
        
        # 子应用代理
        if first_seg and first_seg not in ('login', 'logout', 'api', 'static', 'favicon.ico'):
            if self.get_session():
                self.proxy_request(meth)
                return
        self.send_response(405)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Method Not Allowed')
    return do_method


Handler.do_PUT = _proxy_method('PUT')


def _do_delete(self):
    path = unquote(self.path.split('?')[0])
    session = self.get_session()
    if not session:
        self.redirect('/login/')
        return
    if session.get('role') != 'admin':
        self.send_json(403, '{"error":"需要管理员权限"}')
        return
    if path.startswith('/api/users/') and self.command == 'DELETE':
        uid = path.split('/')[-1]
        if not uid or uid == 'users':
            self.send_json(400, '{"error":"缺少用户ID"}')
            return
        # 支持 id 或 username 删除
        users = list_users()
        user_to_del = None
        for u in users:
            if u['id'] == uid or u['username'] == uid:
                user_to_del = u
                break
        if not user_to_del:
            self.send_json(404, '{"error":"用户不存在"}')
            return
        if user_to_del['username'] == 'root':
            self.send_json(400, '{"error":"禁止删除root"}')
            return
        if delete_user(user_to_del['id']):
            self.send_json(200, '{"ok":true}')
        else:
            self.send_json(400, '{"error":"删除失败"}')
        return
    # 代理到子应用
    first_seg = path.strip('/').split('/')[0]
    if first_seg and first_seg not in ('login', 'logout', 'api', 'static', 'favicon.ico'):
        self.proxy_request('DELETE')
        return
    self.send_response(405)
    self.end_headers()


Handler.do_DELETE = _do_delete


if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    print(f"NetTool Portal 启动: http://0.0.0.0:{PORT}")
    with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nPortal 已停止")
