# modules/http_handler.py - HTTP Request Handler (do_GET, do_POST, do_DELETE)
# Includes H (BaseHTTPRequestHandler) and T (ThreadingHTTPServer)
import os, json, hashlib, urllib.parse, threading, time, uuid, re, random, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ─── Import from sibling modules (lazy to avoid circular imports) ─────────────
# These are set by server.py via _init()
_auth = None
_llm = None
_topology = None
_terminal = None
_websocket = None

def _init(auth_mod, llm_mod, topo_mod, term_mod, ws_mod):
    global _auth, _llm, _topology, _terminal, _websocket
    _auth = auth_mod
    _llm = llm_mod
    _topology = topo_mod
    _terminal = term_mod
    _websocket = ws_mod

# ─── Path globals (set by server.py) ─────────────────────────────────────────
PORT = None
BASE_DIR = None
OPEN_MODE = True

def _init_paths(port, base_dir, open_mode=True):
    global PORT, BASE_DIR, OPEN_MODE
    PORT = port
    BASE_DIR = base_dir
    OPEN_MODE = open_mode

# ─── Plan Parser Helpers ──────────────────────────────────────────────────────
def _parse_plan_from_response(text):
    """从 LLM 返回的文本中提取 [plan] 块并解析为 ops 列表。"""
    ops = []
    # 提取所有 [plan] 块，取最后一个
    all_plan_blocks = re.findall(r'\[plan\](.*?)\[/plan\]', text, re.DOTALL)
    if not all_plan_blocks:
        return ops
    plan_text = all_plan_blocks[-1]
    # 跳过模板值
    skip_values = {'设备ID', '设备类型', '名称', '源ID', '目标ID', 'IP', '描述', 'ID'}
    for m in re.finditer(r'\[op\]\s*(\w+)(.*)', plan_text):
        act = m.group(1).strip()
        args_str = m.group(2) or ''
        op = {'action': act}
        for pair in args_str.split(','):
            pair = pair.strip()
            if not pair or '=' not in pair:
                continue
            k, v = pair.split('=', 1)
            k, v = k.strip(), v.strip()
            # 去掉 key 前面的冒号
            if k.startswith(':'):
                k = k[1:]
            if v not in skip_values:
                op[k] = v
        if len(op) > 1 and op not in ops:
            ops.append(op)
    return ops


def _build_plan_summary(ops):
    """根据 ops 列表生成人类可读的 plan 摘要。"""
    if not ops:
        return "空 plan"
    parts = []
    add_count = sum(1 for o in ops if o.get('action') == 'add')
    connect_count = sum(1 for o in ops if o.get('action') == 'connect')
    delete_count = sum(1 for o in ops if o.get('action') == 'delete')
    if add_count > 0:
        parts.append(f"添加{add_count}台设备")
    if connect_count > 0:
        parts.append(f"建立{connect_count}条连线")
    if delete_count > 0:
        parts.append(f"删除{delete_count}台设备")
    if not parts:
        parts.append(f"执行{len(ops)}个操作")
    return "、".join(parts)


# ─── HTTP Handler ─────────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def _cors(self, code=200):
        self.send_response(code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Session-Token')
        if code != 204:
            self.send_header('Content-Type', 'application/json')

    def _json(self, data, code=200):
        try:
            self._cors(code)
            self.end_headers()
            if code != 204:
                self.wfile.write(json.dumps(data).encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _send_login_resp(self, token, username, role, project_id, message):
        """Send login response with netool_session cookie (for Portal SSO)."""
        try:
            self._cors(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie', f'netool_session={token}; Path=/; Max-Age={86400 * 7}')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok', 'token': token,
                'username': username, 'role': role,
                'project_id': project_id, 'message': message
            }).encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self._cors(204)
        self.end_headers()

    # ── do_GET ────────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = urllib.parse.unquote(parsed.path), urllib.parse.unquote(parsed.query)
        params = urllib.parse.parse_qs(qs)

        # GET /api/term/sessions - list sessions
        if path == '/api/term/sessions' and self.command == 'GET':
            with _terminal._term_sessions_lock:
                sessions_list = []
                for sid, info in _terminal._term_sessions.items():
                    sessions_list.append({
                        'id': sid,
                        'ip': info.get('ip', ''),
                        'port': info.get('port', ''),
                        'protocol': info.get('protocol', ''),
                        'user': info.get('user', ''),
                        'pid': info.get('pid', 0)
                    })
            self._json({'sessions': sessions_list})
            return

        # GET /api/auth/verify
        if path == '/api/auth/verify':
            token = params.get('token', [None])[0]
            if not token:
                self._json({'valid': False, 'error': 'token 参数不能为空'}, 400); return
            s = _auth.get_session(token)
            if s:
                self._json({'valid': True, 'username': s['username'], 'role': s['role'], 'project_id': s.get('project_id')})
            else:
                self._json({'valid': False, 'error': '会话已过期或不存在'})
            return

        # GET /api/auth/status
        if path == '/api/auth/status':
            token = self.headers.get('X-Session-Token', '')
            cookie_str = self.headers.get('Cookie', '')
            if not token:
                for part in cookie_str.split(';'):
                    part = part.strip()
                    if part.startswith('netops_session='):
                        token = part.split('=', 1)[1].strip(' "\'')
                        break
            s = _auth.get_session(token)
            if s:
                self._json({'logged_in': True, 'username': s['username'], 'role': s['role'], 'project_id': s.get('project_id')})
            else:
                self._json({'logged_in': False})
            return

        if path == '/api/llm/settings':
            self._json(_llm.load_llm_settings())
            return

        if path == '/api/project/current':
            self._json({'id': 'default', 'name': '默认项目'})
            return

        if path == '/api/topology' and self.command == 'GET':
            project = params.get('projectId', [params.get('project_id', ['default'])])
            project = project[0] if isinstance(project, list) else project
            topo = _topology.load_topo(project, project)
            self._json(topo if topo else {'nodes': [], 'edges': []})
            return

        if path.startswith('/api/topo'):
            project = params.get('projectId', ['default'])[0]
            topo = _topology.load_topo(project, project)
            self._json(topo)
            return

        if path == '/api/pending':
            self._json({'pending': _llm.get_analysis_pending(), 'hasResult': not _llm.get_analysis_pending() and _llm.get_analysis_result() is not None})
            return

        if path == '/api/analysis-result':
            result = _llm.get_analysis_result()
            self._json({'result': result if result is not None else ''})
            return

        if path.startswith('/api/chat/session/') or path == '/api/chat/messages':
            self._json([])
            return

        if path == '/api/chat/clear-ops':
            self._json({'ok': True})
            return

        if path == '/api/terminal/start':
            self._json({'sid': 'stub'})
            return

        if path.startswith('/api/ping'):
            ip = params.get('ip', [''])[0].strip()
            if not ip:
                self._json({'success': False, 'output': 'IP is required'})
                return
            try:
                cmd = ['ping', '-c', '4', '-W', 3, ip]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                output = r.stdout
                if r.returncode == 0:
                    self._json({'success': True, 'output': output})
                else:
                    self._json({'success': False, 'output': output or '目标不可达'})
            except subprocess.TimeoutExpired:
                self._json({'success': False, 'output': 'Ping 超时'})
            except Exception as e:
                self._json({'success': False, 'output': str(e)})
            return

        if path.startswith('/api/terminal/'):
            self._json({'ok': True})
            return

        # GET /api/projects/ - list all projects
        if path == '/api/projects/' or path == '/api/projects':
            self._json(_topology.get_all_projects())
            return

        # GET /api/projects/<id>/users
        m = re.match(r'^/api/projects/([^/]+)/users$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            users = _auth.list_project_users(proj_id)
            self._json({'users': users})
            return

        # GET /api/projects/<id>/topo
        m = re.match(r'^/api/projects/([^/]+)/topo$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            self._json(topo)
            return

        # GET /api/projects/<id>/chat
        m = re.match(r'^/api/projects/([^/]+)/chat$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            chat = _topology.load_project_file(proj_id, 'chat.json', [])
            self._json(chat)
            return

        # GET /api/projects/<id>/oplog
        m = re.match(r'^/api/projects/([^/]+)/oplog$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            oplog = _topology.load_project_file(proj_id, 'oplog.json', [])
            self._json(oplog)
            return

        # GET /api/projects/<id>/meta
        m = re.match(r'^/api/projects/([^/]+)/meta$', path)
        if m:
            meta = _topology.get_project(m.group(1))
            if meta:
                self._json(meta)
            else:
                self._json({'error': 'not found'}, 404)
            return

        # GET /api/projects/<id>/sessions
        m = re.match(r'^/api/projects/([^/]+)/sessions$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            sessions = _topology.get_all_sessions(proj_id)
            self._json(sessions)
            return

        # GET /api/projects/<id>/sessions/<sid>/messages
        m = re.match(r'^/api/projects/([^/]+)/sessions/([^/]+)/messages$', path)
        if m:
            proj_id, session_id = m.group(1), m.group(2)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            msgs = _topology.get_session_messages(proj_id, session_id)
            self._json(msgs)
            return

        # GET /api/projects/<id>/files
        m = re.match(r'^/api/projects/([^/]+)/files$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            files_dir = os.path.join(_topology.PROJECTS_DIR, proj_id, 'file_AIScreen')
            if not os.path.exists(files_dir):
                self._json([]); return
            files = []
            for fname in os.listdir(files_dir):
                fpath = os.path.join(files_dir, fname)
                if os.path.isfile(fpath):
                    files.append({'name': fname, 'size': os.path.getsize(fpath)})
            self._json(files)
            return

        # GET /api/projects/<id>/files/<filename>
        m = re.match(r'^/api/projects/([^/]+)/files/(.+)$', path)
        if m:
            proj_id = m.group(1)
            fname = os.path.basename(m.group(2))
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            fpath = os.path.join(_topology.PROJECTS_DIR, proj_id, 'file_AIScreen', fname)
            if not os.path.exists(fpath):
                self._json({'error': '文件不存在'}, 404); return
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self._json({'name': fname, 'content': content})
            return

        # Root: redirect or serve index.html
        if path in ('', '/'):
            if 'proj=' in qs:
                proj_name = params.get('proj', [''])[0]
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, must-revalidate')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(os.path.join(BASE_DIR, 'index.html'), 'rb') as f:
                    self.wfile.write(f.read())
                return
            if not os.path.isdir(os.path.join(_topology.PROJECTS_DIR, 'Admin')):
                _topology.create_project('Admin', 'Admin')
            self.send_response(302)
            self.send_header('Location', '/projects.html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            return

        # Static files
        fpath = os.path.join(BASE_DIR, urllib.parse.unquote(path).lstrip('/'))
        if os.path.isfile(fpath):
            ext = os.path.splitext(fpath)[1].lower()
            ct = {'.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8',
                  '.js': 'application/javascript', '.css': 'text/css',
                  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml',
                  '.woff2': 'font/woff2', '.woff': 'font/woff'}.get(ext, 'application/octet-stream')
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Access-Control-Allow-Origin', '*')
            if ext in ('.js', '.css', '.woff2', '.woff', '.png', '.jpg', '.svg'):
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            elif ext == '.html':
                self.send_header('Cache-Control', 'no-cache, must-revalidate')
            self.end_headers()
            with open(fpath, 'rb') as f:
                self.wfile.write(f.read())
            return

        # Project sub-path: /<proj_name>/...
        path_parts = path.split('/')
        decoded_parts = [urllib.parse.unquote(p) for p in path_parts]
        skip_dirs = ('api', 'icons', 'webfonts', 'tools', 'data', 'css', 'js', 'fonts', 'uploads')
        if len(decoded_parts) >= 2 and decoded_parts[1] and decoded_parts[1] not in skip_dirs:
            proj_name = decoded_parts[1]
            proj_dir = os.path.join(_topology.PROJECTS_DIR, proj_name)
            if not os.path.isdir(proj_dir):
                self.send_response(302)
                self.send_header('Location', '/projects.html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            remaining = '/'.join([urllib.parse.unquote(p) for p in path_parts[2:]]) or 'index.html'
            fpath = os.path.join(proj_dir, remaining)
            allowed_exts = ('.html', '.js', '.css', '.json', '.png', '.jpg', '.svg', '.ico', '.woff2', '.woff')
            ext = os.path.splitext(fpath)[1].lower()
            if ext not in allowed_exts:
                fpath = os.path.join(proj_dir, 'index.html')
            if os.path.isfile(fpath):
                ct = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript',
                      '.css': 'text/css', '.json': 'application/json',
                      '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml',
                      '.woff2': 'font/woff2', '.woff': 'font/woff'}.get(ext, 'application/octet-stream')
                self.send_response(200)
                self.send_header('Content-Type', ct)
                self.send_header('Access-Control-Allow-Origin', '*')
                if ext in ('.js', '.css', '.woff2', '.woff', '.png', '.jpg', '.svg'):
                    self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
                elif ext == '.html':
                    self.send_header('Cache-Control', 'no-cache, must-revalidate')
                self.end_headers()
                if ext == '.html' and remaining in ('', 'index.html'):
                    content = _topology._generate_project_index(proj_name)
                    self.wfile.write(content.encode('utf-8'))
                else:
                    with open(fpath, 'rb') as f:
                        self.wfile.write(f.read())
                return
            else:
                # File not found in project dir — try BASE_DIR
                base_fpath = os.path.join(BASE_DIR, remaining)
                if os.path.isfile(base_fpath):
                    ext = os.path.splitext(base_fpath)[1].lower()
                    ct = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript',
                          '.css': 'text/css', '.json': 'application/json',
                          '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml',
                          '.woff2': 'font/woff2', '.woff': 'font/woff'}.get(ext, 'application/octet-stream')
                    self.send_response(200)
                    self.send_header('Content-Type', ct)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    if ext in ('.js', '.css', '.woff2', '.woff', '.png', '.jpg', '.svg'):
                        self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
                    elif ext == '.html':
                        self.send_header('Cache-Control', 'no-cache, must-revalidate')
                    self.end_headers()
                    with open(base_fpath, 'rb') as f:
                        self.wfile.write(f.read())
                    return
                self.send_response(302)
                self.send_header('Location', '/projects.html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return

        if path in ('', '/', '/index.html'):
            self.send_response(302)
            self.send_header('Location', '/projects.html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            return

        fpath = os.path.join(BASE_DIR, urllib.parse.unquote(path).lstrip('/'))
        if os.path.isfile(fpath):
            ext = os.path.splitext(fpath)[1].lower()
            ct = {'.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8',
                  '.js': 'application/javascript', '.css': 'text/css',
                  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml',
                  '.woff2': 'font/woff2', '.woff': 'font/woff'}.get(ext, 'application/octet-stream')
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Access-Control-Allow-Origin', '*')
            if ext in ('.js', '.css', '.woff2', '.woff', '.png', '.jpg', '.svg'):
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            elif ext == '.html':
                self.send_header('Cache-Control', 'no-cache, must-revalidate')
            self.end_headers()
            with open(fpath, 'rb') as f:
                self.wfile.write(f.read())
            return

        # Agent API: GET /api/agent/topology
        if path == '/api/agent/topology':
            proj_id = params.get('project_id', ['default'])[0]
            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            self._json({'ok': True, 'project_id': proj_id, 'topology': topo})
            return

        # Agent API: GET /api/agent/resource_pool
        if path == '/api/agent/resource_pool':
            proj_id = params.get('project_id', ['default'])[0]
            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])
            device_ids = set(n.get('id') for n in nodes)
            port_map = {}
            for n in nodes:
                port_map[n.get('id')] = set(n.get('usedPorts') or [])
            edge_ids = set()
            for e in edges:
                eid = e.get('id', '')
                if eid:
                    edge_ids.add(eid)
            self._json({'ok': True, 'project_id': proj_id, 'device_ids': list(device_ids),
                         'port_map': {k: list(v) for k, v in port_map.items()},
                         'edge_ids': list(edge_ids), 'edge_count': len(edges)})
            return

        # Agent API: GET /api/agent/export
        if path == '/api/agent/export':
            proj_id = params.get('project_id', ['default'])[0]
            fmt = params.get('format', ['json'])[0].lower()
            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            if fmt == 'json':
                self._json({'ok': True, 'format': 'json', 'project_id': proj_id, 'topology': topo})
            elif fmt == 'yaml':
                try:
                    import yaml
                    yaml_str = yaml.dump({'project_id': proj_id, 'topology': topo}, allow_unicode=True, default_flow_style=False)
                    self._json({'ok': True, 'format': 'yaml', 'project_id': proj_id, 'data': yaml_str})
                except ImportError:
                    self._json({'ok': False, 'error': 'YAML 格式需要 pyyaml 库支持'})
            elif fmt == 'png':
                try:
                    import base64
                    svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><text x="10" y="20">拓扑: {proj_id}</text><text x="10" y="40">节点: {len(topo.get("nodes", []))}</text></svg>'
                    png_b64 = base64.b64encode(svg_content.encode('utf-8')).decode('ascii')
                    self._json({'ok': True, 'format': 'png', 'project_id': proj_id, 'image': png_b64})
                except Exception as e:
                    self._json({'ok': False, 'error': f'PNG 生成失败: {str(e)}'})
            else:
                self._json({'ok': False, 'error': f'不支持的格式: {fmt}，支持 json/yaml/png'})
            return

        # Agent API: GET /api/agent/snapshots
        if path == '/api/agent/snapshots':
            proj_id = params.get('project_id', ['default'])[0]
            snaps_file = os.path.join(_topology.PROJECTS_DIR, proj_id, 'snapshots.json')
            snaps = []
            if os.path.exists(snaps_file):
                try:
                    with open(snaps_file) as f:
                        snaps = json.load(f)
                except:
                    pass
            brief = []
            for s in snaps:
                brief.append({'id': s.get('id'), 'name': s.get('name'), 'created': s.get('created'),
                              'nodeCount': len(s.get('topology', {}).get('nodes', [])),
                              'edgeCount': len(s.get('topology', {}).get('edges', []))})
            self._json({'ok': True, 'snapshots': brief})
            return

        # GET /api/chat/poll/<task_id>
        m = re.match(r'^/api/chat/poll/([\w-]+)$', path)
        if m and self.command == 'GET':
            task_id = m.group(1)
            task = _llm.get_task(task_id)
            if not task:
                self._json({'status': 'error', 'error': 'Task not found'}, 404); return
            self._json({'status': task['status'], 'reply': task.get('reply', ''),
                        'ops': task.get('ops', []), 'error': task.get('error', '')})
            return

        # 404
        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write('<html><body><h1>404 Not Found</h1><p>文件不存在</p><a href="/projects.html">返回项目列表</a></body></html>'.encode('utf-8'))

    # ── do_DELETE ──────────────────────────────────────────────────────────────
    def do_DELETE(self):
        path = urllib.parse.unquote(self.path)

        # DELETE /api/projects/<proj>
        m = re.match(r'^/api/projects/([^/]+)$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            if s['role'] not in ('owner', 'super'):
                self._json({'error': '只有项目所有者或超级管理员可以删除项目'}, 403); return
            _topology.delete_project(proj_id)
            self._json({'status': 'ok'})
            return

        # DELETE /api/projects/<proj>/sessions/<sid>
        m = re.match(r'^/api/projects/([^/]+)/sessions/([^/]+)$', path)
        if m:
            proj_id, session_id = m.group(1), m.group(2)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            _topology.delete_session(proj_id, session_id)
            self._json({'status': 'ok'})
            return

        # DELETE /api/super/sessions/<token>
        m = re.match(r'^/api/super/sessions/([^/]+)$', path)
        if m and self.command == 'DELETE':
            s = {'username': 'admin', 'role': 'super'}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            _auth.del_session(m.group(1))
            self._json({'status': 'ok'})
            return

        if path == '/api/chat/messages':
            self.send_response(405)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{}')
            return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{}')

    # ── do_POST ────────────────────────────────────────────────────────────────
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = urllib.parse.unquote(parsed.path), urllib.parse.unquote(parsed.query)
        params = urllib.parse.parse_qs(qs)
        length = int(self.headers.get('Content-Length', 0) or 0)
        body = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else '{}'
        try:
            parsed_body = json.loads(body)
            payload = parsed_body if isinstance(parsed_body, dict) else {}
        except:
            payload = {}

        # ── AI Topology Analysis: POST /api/topology ────────────────────────
        if path == '/api/topology' and self.command == 'POST':
            topo_data = payload  # full payload: {nodes, edges, summary}
            settings = _llm.load_llm_settings()
            api_url = settings.get('api_url', '').strip()
            api_key = settings.get('api_key', '').strip()
            oauth_token = settings.get('oauth_token', '').strip()
            if oauth_token:
                api_key = oauth_token
                api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key:
                self._json({'error': '请先在 AI设置 中配置 API Key'}); return
            model = settings.get('model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = float(settings.get('temperature', 0.7))
            max_tokens = int(settings.get('max_tokens', 8192))
            # Start async analysis
            _llm.set_analysis_pending(True)
            _llm.set_analysis_result(None)
            t = threading.Thread(target=_llm.async_analyze_topology,
                                args=('', topo_data, api_url, api_key, model, temperature, max_tokens))
            t.daemon = True
            t.start()
            self._json({'status': 'ok'})
            return

        # ── Auth: POST /api/projects/<id>/login ─────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/login$', path)
        if m:
            proj_id = m.group(1)
            username = payload.get('username', '').strip() or 'admin'
            token = _auth.new_session('admin', 'super', project_id=proj_id)
            self._send_login_resp(token, 'admin', 'super', proj_id, '登录成功（认证已禁用）')
            return

        # ── Auth: POST /api/projects/<id>/logout ────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/logout$', path)
        if m:
            token = self.headers.get('X-Session-Token', '')
            if token:
                _auth.del_session(token)
            self._json({'status': 'ok', 'message': '已退出登录'})
            return

        # ── Auth: POST /api/projects/<id>/register ──────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/register$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            if s['role'] not in ('owner', 'super'):
                self._json({'error': '只有项目所有者或超级管理员可以添加成员'}, 403); return
            username = payload.get('username', '').strip()
            password = payload.get('password', '')
            role = payload.get('role', 'member').strip()
            if not username or not password:
                self._json({'error': '用户名和密码不能为空'}, 400); return
            if role not in ('owner', 'member'):
                self._json({'error': 'role 必须是 owner 或 member'}, 400); return
            if role == 'owner' and s['role'] != 'super':
                self._json({'error': '只有超级管理员可以添加所有者'}, 403); return
            _auth.add_project_user(proj_id, username, password, role)
            self._json({'status': 'ok', 'message': f'用户 {username} 已添加'})
            return

        # ── Auth: POST /api/projects/<id>/users/<username> DELETE ──────────
        m = re.match(r'^/api/projects/([^/]+)/users/([^/]+)$', path)
        if m and self.command == 'DELETE':
            proj_id, target_user = m.group(1), m.group(2)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            if s['role'] not in ('owner', 'super'):
                self._json({'error': '只有项目所有者或超级管理员可以删除成员'}, 403); return
            if _auth.remove_project_user(proj_id, target_user):
                self._json({'status': 'ok', 'message': f'用户 {target_user} 已删除'})
            else:
                self._json({'error': '用户不存在'}, 404)
            return

        # ── Super Admin: GET /api/super/users ──────────────────────────────
        if path == '/api/super/users':
            s = {'username': 'admin', 'role': 'super'}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            result = []
            if os.path.exists(_topology.PROJECTS_DIR):
                for name in os.listdir(_topology.PROJECTS_DIR):
                    proj_dir = os.path.join(_topology.PROJECTS_DIR, name)
                    if os.path.isdir(proj_dir):
                        users = _auth.get_project_users(name)
                        proj_users = []
                        if users.get("owner"):
                            proj_users.append({"username": users["owner"]["username"], "role": users["owner"]["role"]})
                        proj_users.extend([{"username": u["username"], "role": u["role"]} for u in users.get("members", [])])
                        result.append({"project_id": name,
                                       "project_name": _topology.get_project(name).get("name", name) if _topology.get_project(name) else name,
                                       "users": proj_users})
            self._json({"projects": result})
            return

        # ── Super Admin: GET /api/super/sessions ───────────────────────────
        if path == '/api/super/sessions':
            s = {'username': 'admin', 'role': 'super'}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            with _auth._session_lock:
                sessions = [{"token": k, "username": v["username"], "role": v["role"],
                             "project_id": v.get("project_id"),
                             "created": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(v["created_at"]))}
                            for k, v in _auth._session_store.items()]
            self._json({"sessions": sessions})
            return

        # ── Project Management: POST /api/projects/ ─────────────────────────
        if path == '/api/projects/' or path == '/api/projects':
            proj_name = payload.get('name', '')
            owner_username = payload.get('username', '').strip()
            owner_password = payload.get('password', '')
            if not proj_name:
                self._json({'error': '项目名称不能为空'}, 400); return
            safe_proj_id = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', proj_name)
            if not safe_proj_id:
                self._json({'error': '项目名称无效'}, 400); return
            if os.path.isdir(os.path.join(_topology.PROJECTS_DIR, safe_proj_id)):
                self._json({'error': '项目已存在'}, 409); return
            _topology.create_project(safe_proj_id, proj_name, owner_username, owner_password)
            self._json({'status': 'ok', 'id': safe_proj_id, 'name': proj_name, 'redirect': '/?proj=' + safe_proj_id})
            return

        # ── Project DELETE ──────────────────────────────────────────────────
        if path.startswith('/api/projects/') and (self.command == 'DELETE' or payload.get('_method') == 'delete'):
            m = re.match(r'^/api/projects/([^/]+)$', path)
            if m:
                proj_id = m.group(1)
                s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
                if err:
                    self._json(err, err.get('_code', 401)); return
                if s['role'] not in ('owner', 'super'):
                    self._json({'error': '只有项目所有者或超级管理员可以删除项目'}, 403); return
                _topology.delete_project(proj_id)
                self._json({'status': 'ok'})
                return

        # ── POST /api/projects/<proj>/sessions ─────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/sessions$', path)
        if m and self.command == 'POST':
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            if not isinstance(payload, dict):
                self._json({'error': 'Invalid request body'}, status=400); return
            session_name = payload.get('name')
            sid = _topology.create_session(proj_id, session_name)
            self._json({'status': 'ok', 'id': sid, 'name': session_name or 'default'})
            return

        # ── POST /api/projects/<id>/sessions/<sid>/messages ─────────────────
        m = re.match(r'^/api/projects/([^/]+)/sessions/([^/]+)/messages$', path)
        if m and self.command == 'POST':
            proj_id, session_id = m.group(1), m.group(2)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            role = payload.get('role', 'user')
            msg_content = payload.get('content', '')
            ops = payload.get('ops')
            if _topology.append_session_message(proj_id, session_id, role, msg_content, ops) is None:
                self._json({'error': 'project not found'}, 404); return
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/topo ───────────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/topo$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            topo_data = payload.get('data', payload)
            _topology.save_project_file(proj_id, 'topo.json', topo_data)
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/chat ───────────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/chat$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            chat = payload.get('messages', payload)
            _topology.save_project_file(proj_id, 'chat.json', chat)
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/oplog ──────────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/oplog$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            oplog = payload.get('oplog', {}) if isinstance(payload, dict) else payload
            _topology.save_project_file(proj_id, 'oplog.json', oplog)
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/files ──────────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/files$', path)
        if m:
            proj_id = m.group(1)
            s = {'username': 'admin', 'role': 'super', 'project_id': proj_id}; err = None
            if err:
                self._json(err, err.get('_code', 401)); return
            files_dir = os.path.join(_topology.PROJECTS_DIR, proj_id, 'file_AIScreen')
            os.makedirs(files_dir, exist_ok=True)
            filename = os.path.basename(payload.get('name', 'untitled.txt'))
            content = payload.get('content', '')
            fpath = os.path.join(files_dir, filename)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            self._json({'ok': True, 'name': filename, 'size': len(content)})
            return

        # ── LLM Settings ────────────────────────────────────────────────────
        if path == '/api/llm/settings':
            _llm.save_llm_settings(payload)
            self._json({'status': 'ok'})
            return

        if path == '/api/llm/test':
            test_url = payload.get('api_url', '').strip()
            test_key = payload.get('api_key', '').strip()
            test_model = payload.get('model', '').strip() or 'MiniMax-M2.5-highspeed'
            oauth_tok = payload.get('oauth_token', '').strip()
            if oauth_tok:
                test_key = oauth_tok
                test_url = 'https://api.minimaxi.com/anthropic'
                test_model = payload.get('model', '').strip() or 'MiniMax-M2.5-highspeed'
            if not test_key:
                self._json({'ok': False, 'error': 'API Key 或 Access Token 不能为空'}); return
            messages = [{'role': 'user', 'content': 'hi'}]
            reply = _llm.call_llm_chat(test_url, test_key, test_model, messages)
            if reply.startswith('LLM调用失败'):
                self._json({'ok': False, 'error': reply})
            else:
                self._json({'ok': True, 'reply': reply})
            return

        # ── Chat: proxy to LLM ──────────────────────────────────────────────
        if path == '/api/chat/send':
            settings = _llm.load_llm_settings()
            oauth_token = settings.get('oauth_token', '').strip()
            api_url = settings.get('api_url', '').strip()
            api_key = settings.get('api_key', '').strip()
            model = settings.get('model', '').strip() or settings.get('oauth_model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = settings.get('temperature', 0.7)
            max_tokens_cfg = settings.get('max_tokens', 8192)

            if oauth_token:
                api_key = oauth_token
                api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key:
                self._json({'reply': '请先在 AI设置 中配置 API Key'}); return

            proj_id = payload.get('projectId', 'default')
            session_id = payload.get('sessionId', 'default')
            user_text = payload.get('text', '')
            if len(user_text) > 10000:
                self._json({'reply': '消息过长'}); return
            topo_info = payload.get('topology', {})
            with_topo = payload.get('withTopo', False)
            topo_mode = payload.get('topoMode', 'detail')

            sys_prompt = _llm.build_system_prompt(proj_id)
            settings2 = _llm.load_llm_settings()
            custom_sys = settings2.get('system_prompt', '').strip()
            if custom_sys:
                sys_prompt = sys_prompt + '\n\n' + custom_sys

            msgs_history = _topology.get_session_messages(proj_id, session_id)
            is_first_message = len(msgs_history) == 0

            user_content = user_text
            if with_topo and topo_info:
                nodes = topo_info.get('nodes', [])
                edges = topo_info.get('edges', [])
                if topo_mode == 'brief' or not is_first_message:
                    brief_lines = [f"当前拓扑（共 {len(nodes)} 个设备，{len(edges)} 条连线）"]
                    if nodes:
                        key_names = [n.get('label', '?') for n in nodes[:10]]
                        brief_lines.append(f"关键设备：{', '.join(key_names)}" + (f" 等（更多设备略）" if len(nodes) > 10 else ""))
                    user_content = user_text + "\n\n" + "\n".join(brief_lines)
                else:
                    lines = [f"当前拓扑（共 {len(nodes)} 个设备，{len(edges)} 条连线）："]
                    for n in nodes:
                        avail = n.get('availablePorts', [])
                        used = n.get('usedPorts', [])
                        lines.append(f"  设备：{n.get('label','?')} [ID={n.get('id','')}] 类型={n.get('type','?')} IP={n.get('ip','') or '-'}")
                        if used:
                            lines.append(f"    已用端口: {', '.join(used)}")
                        if avail:
                            lines.append(f"    可用端口: {', '.join(avail[:6])}")
                    lines.append("")
                    lines.append("现有连线：")
                    for e in edges:
                        lines.append(f"  {e.get('fromLabel','?')} --{e.get('srcPort','?')}→ {e.get('toLabel','?')} [{e.get('tgtPort','?')}]")
                    lines.append("")
                    lines.append("━━━ 操作规范（必须严格遵守）━━━")
                    lines.append("【格式】")
                    lines.append("  添加设备：[op] add:id=设备ID,type=类型,x=横坐标,y=纵坐标")
                    lines.append("  添加连线：[op] add_edge:from=源设备ID,to=目标设备ID,src_port=源端口,tgt_port=目标端口")
                    lines.append("  删除设备：[op] del:id=设备ID")
                    lines.append("  删除连线：[op] del_edge:from=源ID,to=目标ID")
                    lines.append("【设备类型】router | switch | firewall | server | PC | cloud | wan")
                    lines.append("【端口规范】优先使用 availablePorts；无端口时选 GE0/0/0～GE0/0/3、GE0/1/0～GE0/1/3 等")
                    lines.append("【核心规则】禁止自动连线；设备不存在时先创建再连线；同一项目 ID 不重复")
                    user_content = user_text + "\n\n" + "\n".join(lines)

            messages = [{'role': 'system', 'content': sys_prompt}]
            for h in msgs_history[-20:]:
                role = h.get('role', 'user')
                if role not in ('user', 'assistant'):
                    role = 'user'
                content = h.get('content', '')
                if content:
                    messages.append({'role': role, 'content': content})
            attachment = payload.get('attachment', '')
            attachment_name = payload.get('attachmentName', '文档')
            if attachment:
                user_content = f"[用户上传了文档：{attachment_name}]\n[文档内容如下]\n{'='*40}\n{attachment}\n{'='*40}\n[文档内容结束]\n\n{user_content}"
            messages.append({'role': 'user', 'content': user_content})

            topo_data = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            task_id = _llm.create_task()
            t = threading.Thread(target=_llm.async_chat,
                                 args=(task_id, messages, api_url, api_key, model, temperature, max_tokens_cfg,
                                       proj_id, session_id, user_text, topo_data))
            t.daemon = True
            t.start()
            self._json({'status': 'ok', 'task_id': task_id})
            return

        # Legacy topology save
        if path.startswith('/api/save') or path.startswith('/api/topo'):
            project = params.get('projectId', [payload.get('project', 'default')])[0]
            if path.startswith('/api/topo'):
                _topology.save_topo(project, project, {'nodes': payload.get('nodes', []), 'edges': payload.get('edges', [])})
            else:
                _topology.save_topo(payload.get('username', 'default'), payload.get('project', 'default'), payload.get('data', {}))
            self._json({'status': 'ok'})
            return

        # ── Terminal: POST /api/term/sessions ────────────────────────────────
        if path == '/api/term/sessions' and self.command == 'POST':
            stype = payload.get('type', 'shell')
            ip = payload.get('ip', '')
            port = payload.get('port', '')
            user = payload.get('user', '')
            password = payload.get('password', '')
            sid = str(uuid.uuid4())
            try:
                _terminal._term_session_queue.put(('create', (sid, stype, ip, str(port), user, password)))
                for _ in range(20):
                    with _terminal._term_sessions_lock:
                        if sid in _terminal._term_sessions:
                            break
                    time.sleep(0.05)
                self._json({'id': sid, 'ws_port': _terminal.TERM_WS_PORT}, 201)
            except Exception as e:
                self._json({'error': str(e)}, 400)
            return

        # ── Terminal: DELETE /api/term/sessions/<sid> ─────────────────────────
        m = re.match(r'^/api/term/sessions/([\w-]+)$', path)
        if m and self.command == 'DELETE':
            sid = m.group(1)
            _terminal._term_session_queue.put(('kill', sid))
            time.sleep(0.1)
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            return

        # ── Agent API: POST /api/agent/plan ─────────────────────────────────
        if path == '/api/agent/plan':
            proj_id = payload.get('project_id', 'default')
            user_text = payload.get('user_text', '')
            if not user_text:
                self._json({'ok': False, 'error': '缺少 user_text 参数'}); return
            settings = _llm.load_llm_settings()
            api_key = settings.get('api_key', '').strip()
            oauth_token = settings.get('oauth_token', '').strip()
            api_url = settings.get('api_url', '').strip()
            model = settings.get('model', '').strip() or settings.get('oauth_model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = float(settings.get('temperature', 0.3))
            max_tokens_cfg = int(settings.get('max_tokens', 2000))
            if oauth_token:
                api_key = oauth_token; api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key:
                self._json({'ok': False, 'error': '请先配置 API Key'}); return
            try:
                system = _llm.build_plan_system_prompt(proj_id)
                messages = [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user_text}
                ]
                req_data = {'model': model, 'messages': messages, 'max_tokens': max_tokens_cfg, 'temperature': temperature}
                req = urllib.request.Request(
                    api_url + '/v1/messages',
                    data=json.dumps(req_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_key, 'anthropic-version': '2023-06-01'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    rd = json.loads(resp.read().decode('utf-8'))
                    text_parts = []
                    for block in rd.get('content', []):
                        if block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    reply = '\n'.join(text_parts) if text_parts else ''
                    ops = _parse_plan_from_response(reply)
                    plan_summary = _build_plan_summary(ops)
                    self._json({'ok': True, 'plan': ops, 'plan_summary': plan_summary})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # ── Agent API: POST /api/agent/execute ──────────────────────────────
        if path == '/api/agent/execute':
            proj_id = payload.get('project_id', 'default')
            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])

            actions_list = payload.get('actions', None)
            if actions_list is not None:
                results = []
                all_ok = True
                for item in actions_list:
                    if not isinstance(item, dict):
                        results.append({'action': 'unknown', 'ok': False, 'error': 'invalid action item'})
                        all_ok = False
                        continue
                    batch_action = item.get('action', '')
                    params = item.get('params', {})
                    if 'project_id' not in params:
                        params['project_id'] = proj_id
                    res = _topology.execute_single_action(batch_action, params, nodes, edges)
                    results.append(res)
                    if not res.get('ok', False):
                        all_ok = False
                topo['nodes'] = nodes
                topo['edges'] = edges
                _topology.save_project_file(proj_id, 'topo.json', topo)
                self._json({'ok': all_ok, 'results': results})
                return

            # Single action mode
            action = payload.get('action', '')
            if not action:
                self._json({'ok': False, 'error': '缺少 action 参数'}); return
            res = _topology.execute_single_action(action, payload, nodes, edges)
            topo['nodes'] = nodes
            topo['edges'] = edges
            _topology.save_project_file(proj_id, 'topo.json', topo)
            self._json(res)
            return

        # ── Agent API: POST /api/agent/chat ─────────────────────────────────
        if path == '/api/agent/chat':
            settings = _llm.load_llm_settings()
            api_key = settings.get('api_key', '').strip()
            oauth_token = settings.get('oauth_token', '').strip()
            api_url = settings.get('api_url', '').strip()
            model = settings.get('model', '').strip() or settings.get('oauth_model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = float(settings.get('temperature', 0.7))
            max_tokens_cfg = int(settings.get('max_tokens', 8192))
            if oauth_token:
                api_key = oauth_token; api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key:
                self._json({'ok': False, 'error': '请先配置 API Key'}); return
            proj_id = payload.get('project_id', 'default')
            user_text = payload.get('message', '')
            if not user_text:
                self._json({'ok': False, 'error': '缺少 message 参数'}); return
            # 支持 Manage 转发的对话历史（来自 history 参数）
            history = payload.get('history', [])
            confirm_mode = payload.get('confirm', False)
            sys_prompt = _llm.build_system_prompt(proj_id)
            messages = [{'role': 'system', 'content': sys_prompt}]
            # 注入 Manage 转发的历史消息
            for h in history:
                hrole = h.get('role', 'user')
                if hrole in ('user', 'assistant', 'bot'):
                    role = 'assistant' if hrole in ('assistant', 'bot') else 'user'
                    messages.append({'role': role, 'content': h.get('content', '')})
            topo_data = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo_data.get('nodes', []); edges = topo_data.get('edges', [])
            # 如果 Manage 传递了 topology_brief，优先使用；否则从文件构建
            payload_brief = payload.get('topology_brief', '')
            brief = [payload_brief] if payload_brief else [f'当前拓扑（共 {len(nodes)} 个设备，{len(edges)} 条连线）']
            if not payload_brief and nodes:
                kn = [n.get('label', '?') for n in nodes[:10]]
                brief.append(f'关键设备：{", ".join(kn)}' + (' 等（更多设备略）' if len(nodes) > 10 else ''))
            confirm_hint = ('\n\n[系统提示]用户已确认执行，请直接输出操作指令，不需要任何描述文字。'
                        '格式：每行一个 [op] 指令，例如：\n'
                        '[op] add:id=SW1,type=switch,label=接入交换机\n'
                        '[op] add:id=R1,type=router,label=核心路由器\n'
                        '[op] connect:from=R1,to=SW1,srcPort=GE0/0/1,tgtPort=GE0/0/1\n'
                        '禁止在回复中出现 ✅ ❌ ⚠️ 等状态符号，禁止描述网络架构。') if confirm_mode else ''
            messages.append({'role': 'user', 'content': user_text + confirm_hint + '\n\n' + '\n\n'.join(brief)})
            try:
                req_data = {'model': model, 'messages': messages, 'max_tokens': max_tokens_cfg, 'temperature': temperature}
                req = urllib.request.Request(
                    api_url + '/v1/messages',
                    data=json.dumps(req_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_key, 'anthropic-version': '2023-06-01'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    rd = json.loads(resp.read().decode('utf-8'))
                    text_parts = []
                    for block in rd.get('content', []):
                        if block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    reply = '\n'.join(text_parts) if text_parts else ''
                    ops = []
                    for m in re.finditer(r'\[op\]\s*(\w+)(?:[:：](.+))?', reply):
                        act = m.group(1).strip()
                        args = m.group(2) or ''
                        op = {'action': act}
                        for pair in args.split(','):
                            pair = pair.strip()
                            if not pair:
                                continue
                            if '=' in pair:
                                k, v = pair.split('=', 1)
                                op[k.strip()] = v.strip()
                        if op not in ops:
                            ops.append(op)
                    if not ops:
                        import re as re_module
                        json_blocks = re_module.findall(r'\[\s*\{[^{}]*\}\s*\]', reply, re_module.DOTALL)
                        for jb in json_blocks:
                            try:
                                parsed = json.loads(jb)
                                if isinstance(parsed, list):
                                    for item in parsed:
                                        if isinstance(item, dict) and 'action' in item and item not in ops:
                                            ops.append(item)
                                elif isinstance(parsed, dict) and 'action' in parsed and parsed not in ops:
                                    ops.append(parsed)
                            except:
                                pass
                    self._json({'ok': True, 'reply': reply, 'ops': ops})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # ── Agent API: POST /api/agent/snapshot ────────────────────────────
        if path == '/api/agent/snapshot' and self.command == 'POST':
            proj_id = payload.get('project_id', 'default')
            name = payload.get('name', time.strftime('%Y-%m-%d %H:%M:%S'))
            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            snap_id = 'snap_' + str(int(time.time() * 1000)) + str(random.randint(100, 999))
            snap = {'id': snap_id, 'name': name, 'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'topology': topo}
            snaps_file = os.path.join(_topology.PROJECTS_DIR, proj_id, 'snapshots.json')
            snaps = []
            if os.path.exists(snaps_file):
                try:
                    with open(snaps_file) as f:
                        snaps = json.load(f)
                except:
                    pass
            snaps.append(snap)
            with open(snaps_file, 'w') as f:
                json.dump(snaps, f, ensure_ascii=False, indent=2)
            self._json({'ok': True, 'snapshot': snap})
            return

        # ── Agent API: POST /api/agent/restore/{snapshot_id} ───────────────
        m = re.match(r'^/api/agent/restore/([^/]+)$', path)
        if m and self.command == 'POST':
            snap_id = m.group(1)
            proj_id = payload.get('project_id', 'default')
            snaps_file = os.path.join(_topology.PROJECTS_DIR, proj_id, 'snapshots.json')
            if not os.path.exists(snaps_file):
                self._json({'ok': False, 'error': '快照文件不存在'}); return
            try:
                with open(snaps_file) as f:
                    snaps = json.load(f)
            except:
                self._json({'ok': False, 'error': '快照文件读取失败'}); return
            target = None
            for s in snaps:
                if s.get('id') == snap_id:
                    target = s; break
            if not target:
                self._json({'ok': False, 'error': f'快照 {snap_id} 不存在'}); return
            topo = target.get('topology', {'nodes': [], 'edges': []})
            _topology.save_project_file(proj_id, 'topo.json', topo)
            self._json({'ok': True, 'message': f'已恢复到快照: {target.get("name", snap_id)}', 'topology': topo})
            return

        # ── Agent API: POST /api/agent/goal ────────────────────────────────
        if path == '/api/agent/goal':
            settings = _llm.load_llm_settings()
            api_key = settings.get('api_key', '').strip()
            oauth_token = settings.get('oauth_token', '').strip()
            api_url = settings.get('api_url', '').strip()
            model = settings.get('model', '').strip() or settings.get('oauth_model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = float(settings.get('temperature', 0.7))
            max_tokens_cfg = int(settings.get('max_tokens', 8192))
            if oauth_token:
                api_key = oauth_token; api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key:
                self._json({'ok': False, 'error': '请先配置 API Key'}); return

            proj_id = payload.get('project_id', 'default')
            goal = payload.get('goal', '').strip()
            if not goal:
                self._json({'ok': False, 'error': '缺少 goal 参数'}); return

            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', []); edges = topo.get('edges', [])

            topo_lines = [f'当前拓扑（共 {len(nodes)} 个设备，{len(edges)} 条连线）：']
            for n in nodes:
                avail = n.get('availablePorts', [])
                used = n.get('usedPorts', [])
                topo_lines.append(
                    f'  设备：{n.get("label","?")} [ID={n.get("id","")}] 类型={n.get("type","?")} '
                    f'IP={n.get("ip","") or "-"}'
                    + (f' 已用端口={",".join(used)}' if used else '')
                    + (f' 可用端口={",".join(avail[:6])}' if avail else ' 可用端口=无')
                )
            for e in edges:
                topo_lines.append(
                    f'  连线：{e.get("fromLabel",e.get("source","?"))} --{e.get("srcPort","?")}→ '
                    f'{e.get("toLabel",e.get("target","?"))} [{e.get("tgtPort","?")}]'
                )
            topo_context = '\n'.join(topo_lines) or '  （空拓扑）'

            goal_rules = _llm.load_goal_system_prompt()
            prompt = f"""你是 NetOps 执行规划 Agent。收到高层目标后，自动规划具体执行步骤。

【拓扑上下文】
{topo_context}

【你的任务】
用户目标：{goal}

请根据拓扑上下文，分析目标并生成执行计划：
{goal_rules}"""

            messages = [{'role': 'user', 'content': prompt}]
            try:
                req_data = {'model': model, 'messages': messages, 'max_tokens': max_tokens_cfg, 'temperature': temperature}
                req = urllib.request.Request(
                    api_url + '/v1/messages',
                    data=json.dumps(req_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_key, 'anthropic-version': '2023-06-01'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    rd = json.loads(resp.read().decode('utf-8'))
                    text_parts = []
                    for block in rd.get('content', []):
                        if block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    llm_reply = '\n'.join(text_parts) if text_parts else ''

                import re as re_module
                plan_data = None
                json_blocks = re_module.findall(r'```json\s*([\s\S]*?)\s*```', llm_reply)
                for jb in json_blocks:
                    try:
                        plan_data = json.loads(jb.strip())
                        break
                    except json.JSONDecodeError:
                        pass
                if not plan_data:
                    json_objs = re_module.findall(r'\{[\s\S]*?"execution_plan"[\s\S]*?\}', llm_reply)
                    for jo in json_objs:
                        try:
                            plan_data = json.loads(jo.strip())
                            break
                        except json.JSONDecodeError:
                            pass

                if plan_data and isinstance(plan_data, dict):
                    self._json({
                        'ok': True, 'goal': goal,
                        'goal_summary': plan_data.get('goal_summary', goal),
                        'execution_plan': plan_data.get('execution_plan', []),
                        'topology_change': plan_data.get('topology_change', {}),
                        'risk_note': plan_data.get('risk_note'),
                        'llm_raw': llm_reply[:500]
                    })
                else:
                    self._json({'ok': False, 'error': '执行计划解析失败', 'llm_reply': llm_reply[:1000]})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # ── Agent API: POST /api/agent/goal/execute ────────────────────────
        if path == '/api/agent/goal/execute':
            proj_id = payload.get('project_id', 'default')
            plan = payload.get('plan', [])
            if not plan:
                self._json({'ok': False, 'error': '缺少 plan 参数'}); return

            topo = _topology.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])

            results = []
            all_ok = True
            try:
                for step in plan:
                    action = step.get('action', '')
                    params = step.get('params', {})
                    ok = True
                    msg = ''
                    try:
                        if action == 'add_node':
                            nid = params.get('id')
                            if not nid:
                                raise ValueError('add_node 需要 id 参数')
                            if any(n.get('id') == nid for n in nodes):
                                raise ValueError(f'设备 {nid} 已存在')
                            ntype = params.get('type', 'switch')
                            nip = params.get('ip', '')
                            nlabel = params.get('label', nid)
                            if params.get('x') is not None and params.get('y') is not None:
                                nx = int(params.get('x'))
                                ny = int(params.get('y'))
                            else:
                                nx, ny = _topology.next_grid_pos()
                            nodes.append({'id': nid, 'type': ntype, 'label': nlabel, 'ip': nip,
                                          '_x': nx, '_y': ny,
                                          'availablePorts': params.get('availablePorts', []),
                                          'usedPorts': params.get('usedPorts', [])})
                            msg = f'添加设备 {nlabel} [{ntype}]'

                        elif action == 'add_edge':
                            src = params.get('from') or params.get('src', '')
                            tgt = params.get('to') or params.get('tgt', '')
                            if not src or not tgt:
                                raise ValueError('add_edge 需要 from 和 to')
                            sn = next((n for n in nodes if n.get('id') == src), None)
                            tn = next((n for n in nodes if n.get('id') == tgt), None)
                            if not sn:
                                if params.get('fromX') is not None:
                                    sx, sy = int(params.get('fromX')), int(params.get('fromY'))
                                else:
                                    sx, sy = _topology.next_grid_pos()
                                nodes.append({'id': src, 'type': params.get('fromType', 'switch'),
                                              'label': params.get('fromLabel', src),
                                              'ip': params.get('fromIp', ''), '_x': sx, '_y': sy,
                                              'availablePorts': [], 'usedPorts': []})
                                sn = next((n for n in nodes if n.get('id') == src), None)
                                msg += f' [auto-add:{src}]'
                            if not tn:
                                if params.get('toX') is not None:
                                    tx, ty = int(params.get('toX')), int(params.get('toY'))
                                else:
                                    tx, ty = _topology.next_grid_pos()
                                nodes.append({'id': tgt, 'type': params.get('toType', 'switch'),
                                              'label': params.get('toLabel', tgt),
                                              'ip': params.get('toIp', ''), '_x': tx, '_y': ty,
                                              'availablePorts': [], 'usedPorts': []})
                                tn = next((n for n in nodes if n.get('id') == tgt), None)
                                msg += f' [auto-add:{tgt}]'
                            if any((e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt) for e in edges):
                                raise ValueError(f'{src} 和 {tgt} 之间已有连线')
                            # Port auto-allocation: if device already has used ports, increment to next
                            def _next_port(used_list):
                                max_num = 0
                                for p in used_list:
                                    for part in p.split('/'):
                                        try:
                                            n = int(part)
                                            if n > max_num:
                                                max_num = n
                                        except ValueError:
                                            pass
                                return 'GE0/0/' + str(max_num + 1)

                            used_s = sn.get('usedPorts', [])
                            used_t = tn.get('usedPorts', [])
                            sp_provided = params.get('srcPort', '')
                            tp_provided = params.get('tgtPort', '')
                            sp = _next_port(used_s) if used_s else (sp_provided or 'GE0/0/1')
                            tp = _next_port(used_t) if used_t else (tp_provided or 'GE0/0/1')
                            sn['usedPorts'] = used_s + [sp]
                            tn['usedPorts'] = used_t + [tp]
                            edges.append({'source': sn['id'], 'target': tn['id'],
                                          'from': sn['id'], 'to': tn['id'],
                                          'fromLabel': sn.get('label', sn['id']),
                                          'toLabel': tn.get('label', tn['id']),
                                          'srcPort': sp, 'tgtPort': tp,
                                          'edgeStyle': 'solid', 'edgeColor': '#374151', 'edgeWidth': 2})
                            msg = '添加连线 ' + src + ' -> ' + tgt + ' (端口 ' + sp + ' -> ' + tp + ')'

                        elif action == 'delete_node':
                            nid = params.get('id')
                            if not nid:
                                raise ValueError('delete_node 需要 id')
                            nn = next((n for n in nodes if n.get('id') == nid), None)
                            if not nn:
                                raise ValueError(f'设备 {nid} 不存在')
                            nid_r = nn.get('id')
                            edges[:] = [e for e in edges
                                        if e.get('source') != nid_r and e.get('from') != nid_r
                                        and e.get('target') != nid_r and e.get('to') != nid_r]
                            nodes[:] = [n for n in nodes if n.get('id') != nid_r]
                            msg = f'删除设备 {nid} 及相关连线'

                        elif action == 'delete_edge':
                            src = params.get('from') or params.get('src', '')
                            tgt = params.get('to') or params.get('tgt', '')
                            if not src or not tgt:
                                raise ValueError('delete_edge 需要 from 和 to')
                            removed = False
                            for i, e in enumerate(edges):
                                if (e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt):
                                    edges.pop(i); removed = True; break
                                if (e.get('source') == tgt or e.get('from') == tgt) and (e.get('target') == src or e.get('to') == src):
                                    edges.pop(i); removed = True; break
                            if not removed:
                                raise ValueError(f'连线 {src} ↔ {tgt} 不存在')
                            msg = f'删除连线 {src} ↔ {tgt}'

                        elif action == 'modify_node':
                            nid = params.get('id')
                            if not nid:
                                raise ValueError('modify_node 需要 id')
                            nn = next((n for n in nodes if n.get('id') == nid), None)
                            if not nn:
                                raise ValueError(f'设备 {nid} 不存在')
                            if 'label' in params:
                                nn['label'] = params['label']
                            if 'ip' in params:
                                nn['ip'] = params['ip']
                            if 'type' in params:
                                nn['type'] = params['type']
                            msg = f'修改设备 {nid}'

                        elif action == 'move_node':
                            nid = params.get('id')
                            if not nid:
                                raise ValueError('move_node 需要 id')
                            nn = next((n for n in nodes if n.get('id') == nid), None)
                            if not nn:
                                raise ValueError(f'设备 {nid} 不存在')
                            nn['_x'] = int(params.get('x', 300))
                            nn['_y'] = int(params.get('y', 200))
                            msg = f'移动设备 {nid}'

                        else:
                            ok = False
                            msg = f'未知 action: {action}'
                            all_ok = False

                    except Exception as ex:
                        ok = False
                        msg = str(ex)
                        all_ok = False

                    results.append({'step': step.get('step'), 'action': action, 'ok': ok, 'message': msg})

                topo['nodes'] = nodes
                topo['edges'] = edges
                _topology.save_project_file(proj_id, 'topo.json', topo)
                self._json({'ok': all_ok, 'results': results, 'topology': topo})

            except Exception as e:
                self._json({'ok': False, 'error': str(e), 'results': results})
            return

        self._json({'error': 'not found'}, 404)


class T(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
