# modules/topology.py - Topology CRUD, project/session management, OP parsing
import os, json, hashlib, threading, time, uuid, re, random, shutil

# ─── Path globals (set by server.py / modules/__init__.py) ───────────────────
APP_DIR = None
DATA_DIR = None
PROJECTS_DIR = None
UPLOADS_DIR = None
CONFIG_DIR = None

def _init_paths(app_dir, data_dir, projects_dir, uploads_dir, config_dir):
    global APP_DIR, DATA_DIR, PROJECTS_DIR, UPLOADS_DIR, CONFIG_DIR
    APP_DIR = app_dir
    DATA_DIR = data_dir
    PROJECTS_DIR = projects_dir
    UPLOADS_DIR = uploads_dir
    CONFIG_DIR = config_dir

# ─── Global batch position counter ────────────────────────────────────────────
_GLOBAL_BATCH_POS = {'count': 0}

def next_grid_pos():
    """为批量添加的节点分配网格位置，避免重叠。"""
    cols = 4
    spacing_x, spacing_y = 200, 160
    row = _GLOBAL_BATCH_POS['count'] // cols
    col = _GLOBAL_BATCH_POS['count'] % cols
    x = 200 + col * spacing_x
    y = 200 + row * spacing_y
    _GLOBAL_BATCH_POS['count'] += 1
    return x, y

# ─── OP Pattern Matching ───────────────────────────────────────────────────────
OP_PATTERNS = {
    'add':       re.compile(r'^\[op\]\s*add:type=(router|switch|server|firewall|pc),ip=(\d+\.\d+\.\d+\.\d+)(,label=.*)?$'),
    'delete':    re.compile(r'^\[op\]\s*delete:node_id=(\w+)$'),
    'update':    re.compile(r'^\[op\]\s*update:node_id=(\w+)(,ip=(\d+\.\d+\.\d+\.\d+))?(,label=.*)?$'),
    'ping':      re.compile(r'^\[op\]\s*ping:ip=(\d+\.\d+\.\d+\.\d+)$'),
    'terminal':  re.compile(r'^\[op\]\s*terminal:ip=(\d+\.\d+\.\d+\.\d+),method=(ssh|telnet),port=(\d+)$'),
    'backup':    re.compile(r'^\[op\]\s*backup:ip=(\d+\.\d+\.\d+\.\d+)$'),
    'get_topology': re.compile(r'^\[op\]\s*get_topology$'),
}

def parse_op(text: str):
    """Parse [op] text, return {'op': 'xxx', 'params': {...}} or None."""
    text = text.strip()
    for op_name, pattern in OP_PATTERNS.items():
        m = pattern.match(text)
        if m:
            groups = m.groups()
            if op_name == 'add':
                params = {'type': groups[0], 'ip': groups[1], 'label': (groups[2] or '').lstrip(',label=')}
            elif op_name == 'delete':
                params = {'node_id': groups[0]}
            elif op_name == 'update':
                ip = groups[2] if len(groups) > 2 and groups[2] else None
                label = (groups[4] if len(groups) > 4 and groups[4] else '').lstrip(',label=')
                if ip:
                    params = {'node_id': groups[0], 'ip': ip, 'label': label}
                else:
                    params = {'node_id': groups[0], 'label': label} if label else {'node_id': groups[0]}
            elif op_name == 'ping':
                params = {'ip': groups[0]}
            elif op_name == 'terminal':
                params = {'ip': groups[0], 'method': groups[1], 'port': groups[2]}
            elif op_name == 'backup':
                params = {'ip': groups[0]}
            else:
                params = {}
            return {'op': op_name, 'params': params}
    return None

def extract_json_ops(text: str):
    """Extract operations from JSON blocks in AI reply text."""
    ops = []
    json_re = re.compile(r'\[\s*\{.*?"action".*?\}\s*\]|\{\s*".*?"action".*?\}', re.DOTALL)
    for m in json_re.finditer(text):
        try:
            parsed = json.loads(m.group())
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and 'action' in item:
                        ops.append(item)
            elif isinstance(parsed, dict) and 'action' in parsed:
                ops.append(parsed)
        except json.JSONDecodeError:
            pass
    return ops

# ─── Topology Action Executor ─────────────────────────────────────────────────
def execute_single_action(action, params, nodes, edges):
    """Execute a single topology action.
    Modifies nodes/edges in place. Returns dict with action, ok, and result fields.
    """
    result = {'action': action, 'ok': False, 'error': None}

    def find_node(nid):
        for n in nodes:
            if n.get('id') == nid or n.get('label', '').lower() == str(nid).lower():
                return n
        return None

    def find_edge(src, tgt):
        for e in edges:
            if (e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt):
                return e
            if (e.get('source') == tgt or e.get('from') == tgt) and (e.get('target') == src or e.get('to') == src):
                return e
        return None

    try:
        if action == 'add_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'add_node 需要 id 参数'
                return result
            if find_node(nid):
                result['error'] = f'设备 {nid} 已存在'
                return result
            ntype = params.get('type', 'switch')
            nip = params.get('ip', '')
            nlabel = params.get('label', nid)
            if params.get('x') is not None and params.get('y') is not None:
                nx, ny = int(params.get('x')), int(params.get('y'))
            else:
                nx, ny = next_grid_pos()
            nodes.append({
                'id': nid, 'type': ntype, 'label': nlabel, 'ip': nip,
                '_x': nx, '_y': ny,
                'availablePorts': params.get('availablePorts', []),
                'usedPorts': params.get('usedPorts', [])
            })
            result['ok'] = True
            result['id'] = nid
            result['node'] = nid

        elif action == 'add_edge':
            src = params.get('from') or params.get('from_node') or params.get('src', '')
            tgt = params.get('to') or params.get('to_node') or params.get('tgt', '')
            if not src or not tgt:
                result['error'] = 'add_edge 需要 from 和 to'
                return result
            sn = find_node(src)
            tn = find_node(tgt)
            if not sn:
                result['error'] = f'源设备 {src} 不存在'
                return result
            if not tn:
                result['error'] = f'目标设备 {tgt} 不存在'
                return result
            if find_edge(src, tgt):
                result['error'] = f'{src} 和 {tgt} 之间已有连线'
                return result
            sp = params.get('srcPort', '')
            tp = params.get('tgtPort', '')
            used_ports_src = sn.get('usedPorts', [])
            used_ports_tgt = tn.get('usedPorts', [])
            if sp and sp in used_ports_src:
                result['error'] = f'{src} 的端口 {sp} 已被占用，请换一个端口（如 GE0/0/2）'
                return result
            if tp and tp in used_ports_tgt:
                result['error'] = f'{tgt} 的端口 {tp} 已被占用，请换一个端口（如 GE0/0/2）'
                return result
            if sp:
                sn['usedPorts'] = used_ports_src + [sp]
            if tp:
                tn['usedPorts'] = used_ports_tgt + [tp]
            edges.append({
                'source': sn['id'], 'target': tn['id'],
                'from': sn['id'], 'to': tn['id'],
                'fromLabel': sn.get('label', sn['id']),
                'toLabel': tn.get('label', tn['id']),
                'srcPort': sp, 'tgtPort': tp,
                'edgeStyle': 'solid', 'edgeColor': '#374151', 'edgeWidth': 2
            })
            result['ok'] = True
            result['edge'] = src + ' -> ' + tgt

        elif action == 'delete_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'delete_node 需要 id'
                return result
            nn = find_node(nid)
            if not nn:
                result['error'] = f'设备 {nid} 不存在'
                return result
            nid_r = nn.get('id')
            remaining_edges = []
            for e in edges:
                if e.get('source') == nid_r or e.get('from') == nid_r or e.get('target') == nid_r or e.get('to') == nid_r:
                    other_id = e.get('target') or e.get('to')
                    if other_id == nid_r:
                        other_id = e.get('source') or e.get('from')
                    other_node = find_node(other_id)
                    if other_node:
                        sp = e.get('srcPort', '')
                        tp = e.get('tgtPort', '')
                        if (e.get('source') == nid_r or e.get('from') == nid_r) and sp and sp in other_node.get('usedPorts', []):
                            other_node['usedPorts'].remove(sp)
                        if (e.get('target') == nid_r or e.get('to') == nid_r) and tp and tp in other_node.get('usedPorts', []):
                            other_node['usedPorts'].remove(tp)
                else:
                    remaining_edges.append(e)
            edges[:] = remaining_edges
            nodes[:] = [n for n in nodes if n.get('id') != nid_r]
            result['ok'] = True
            result['deleted'] = nid

        elif action == 'delete_edge':
            src = params.get('from') or params.get('from_node') or params.get('src', '')
            tgt = params.get('to') or params.get('to_node') or params.get('tgt', '')
            if not src or not tgt:
                result['error'] = 'delete_edge 需要 from 和 to'
                return result
            sn = find_node(src)
            tn = find_node(tgt)
            removed = False
            for i, e in enumerate(edges):
                if (e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt):
                    sp = e.get('srcPort', '')
                    tp = e.get('tgtPort', '')
                    if sp and sn and sp in sn.get('usedPorts', []):
                        sn['usedPorts'].remove(sp)
                    if tp and tn and tp in tn.get('usedPorts', []):
                        tn['usedPorts'].remove(tp)
                    edges.pop(i)
                    removed = True
                    break
                if (e.get('source') == tgt or e.get('from') == tgt) and (e.get('target') == src or e.get('to') == src):
                    sp = e.get('srcPort', '')
                    tp = e.get('tgtPort', '')
                    if sp and tn and sp in tn.get('usedPorts', []):
                        tn['usedPorts'].remove(sp)
                    if tp and sn and tp in sn.get('usedPorts', []):
                        sn['usedPorts'].remove(tp)
                    edges.pop(i)
                    removed = True
                    break
            if not removed:
                result['error'] = f'连线 {src} <-> {tgt} 不存在'
                return result
            result['ok'] = True
            result['deleted'] = src + ' <-> ' + tgt

        elif action == 'modify_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'modify_node 需要 id'
                return result
            nn = find_node(nid)
            if not nn:
                result['error'] = f'设备 {nid} 不存在'
                return result
            if 'label' in params:
                nn['label'] = params['label']
            if 'ip' in params:
                nn['ip'] = params['ip']
            if 'type' in params:
                nn['type'] = params['type']
            result['ok'] = True
            result['updated'] = nid

        elif action == 'move_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'move_node 需要 id'
                return result
            nn = find_node(nid)
            if not nn:
                result['error'] = f'设备 {nid} 不存在'
                return result
            nn['_x'] = int(params.get('x', 300))
            nn['_y'] = int(params.get('y', 200))
            result['ok'] = True
            result['moved'] = nid

        else:
            result['error'] = f'未知 action: {action}'

    except Exception as e:
        result['error'] = str(e)

    return result

# ─── Topology Store ───────────────────────────────────────────────────────────
topo_store = {}
_lock = threading.Lock()

def _key(u, p):
    return hashlib.md5(f"{u}::{p}".encode()).hexdigest()

def load_topo(u, p):
    k = _key(u, p)
    with _lock:
        if k in topo_store:
            return topo_store[k]
        if u == p:
            path = os.path.join(PROJECTS_DIR, u, 'topo.json')
        else:
            path = os.path.join(DATA_DIR, k + ".json")
        if os.path.exists(path):
            with open(path) as f:
                topo_store[k] = json.load(f)
            return topo_store[k]
        return None

def save_topo(u, p, data):
    k = _key(u, p)
    with _lock:
        topo_store[k] = data
        if u == p:
            proj_dir = os.path.join(PROJECTS_DIR, u)
            os.makedirs(proj_dir, exist_ok=True)
            _ensure_project_files(proj_dir, u)
            path = os.path.join(proj_dir, 'topo.json')
        else:
            path = os.path.join(DATA_DIR, k + ".json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f)
    if WS_AVAILABLE:
        proj_id = p if p != 'default' else u
        _notify_ws_topo_change(proj_id, data)

# WS reference (set by websocket module)
WS_AVAILABLE = False
def _notify_ws_topo_change(proj_id, topo):
    pass  # filled in by websocket module

def _ensure_project_files(proj_dir, proj_id):
    """Ensure all necessary project files exist."""
    import time as _time_module

    # meta.json
    meta_file = os.path.join(proj_dir, 'meta.json')
    if not os.path.exists(meta_file):
        meta = {'id': proj_id, 'name': proj_id, 'created': _time_module.strftime('%Y-%m-%d %H:%M:%S')}
        with open(meta_file, 'w') as f:
            json.dump(meta, f, indent=2)

    # topo.json
    topo_file = os.path.join(proj_dir, 'topo.json')
    if not os.path.exists(topo_file):
        with open(topo_file, 'w') as f:
            json.dump({'nodes': [], 'edges': []}, f)

    # chat.json
    chat_file = os.path.join(proj_dir, 'chat.json')
    if not os.path.exists(chat_file):
        with open(chat_file, 'w') as f:
            json.dump([], f)

    # oplog.json
    oplog_file = os.path.join(proj_dir, 'oplog.json')
    if not os.path.exists(oplog_file):
        with open(oplog_file, 'w') as f:
            json.dump([], f)

    # users.json
    users_file = os.path.join(proj_dir, 'users.json')
    if not os.path.exists(users_file):
        _pw_hash = hashlib.sha256(b"auto-created").hexdigest()[:16]
        users = {
            "owner": {
                "username": "owner",
                "password_hash": _pw_hash,
                "role": "owner"
            },
            "members": []
        }
        with open(users_file, 'w') as f:
            json.dump(users, f, indent=2)

    # index.html
    index_file = os.path.join(proj_dir, 'index.html')
    if not os.path.exists(index_file):
        template_index = os.path.join(os.path.dirname(__file__), '..', 'index.html')
        if os.path.exists(template_index):
            shutil.copy(template_index, index_file)

    # sessions/default
    sessions_dir = os.path.join(proj_dir, 'sessions')
    os.makedirs(sessions_dir, exist_ok=True)
    default_session_dir = os.path.join(sessions_dir, 'default')
    if not os.path.exists(default_session_dir):
        os.makedirs(default_session_dir, exist_ok=True)
        with open(os.path.join(default_session_dir, 'meta.json'), 'w') as f:
            json.dump({'id': 'default', 'name': 'default'}, f)
        with open(os.path.join(default_session_dir, 'messages.json'), 'w') as f:
            json.dump([], f)

# ─── Project File Helpers ─────────────────────────────────────────────────────
def load_project_file(proj_id, fname, default=None):
    path = os.path.join(PROJECTS_DIR, proj_id, fname)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except:
            pass
    return default

def save_project_file(proj_id, fname, data):
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    os.makedirs(proj_dir, exist_ok=True)
    path = os.path.join(proj_dir, fname)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    if fname == 'topo.json' and WS_AVAILABLE:
        _notify_ws_topo_change(proj_id, data)

# ─── Project Management ──────────────────────────────────────────────────────
def get_all_projects():
    """List all projects with metadata."""
    if not os.path.exists(PROJECTS_DIR):
        return []
    projects = []
    for name in os.listdir(PROJECTS_DIR):
        proj_dir = os.path.join(PROJECTS_DIR, name)
        if not os.path.isdir(proj_dir):
            continue
        meta = {'id': name, 'name': name, 'created': '', 'nodeCount': 0, 'edgeCount': 0}
        meta_file = os.path.join(proj_dir, 'meta.json')
        if os.path.exists(meta_file):
            try:
                with open(meta_file) as f:
                    meta.update(json.load(f))
            except:
                pass
        topo_file = os.path.join(proj_dir, 'topo.json')
        if os.path.exists(topo_file):
            try:
                with open(topo_file) as f:
                    t = json.load(f)
                    meta['nodeCount'] = len(t.get('nodes', []))
                    meta['edgeCount'] = len(t.get('edges', []))
            except:
                pass
        users_file = os.path.join(proj_dir, 'users.json')
        users_info = {}
        if os.path.exists(users_file):
            try:
                with open(users_file) as f:
                    users_info = json.load(f)
            except:
                pass
        meta['hasOwner'] = bool(users_info.get('owner'))
        owner = users_info.get('owner', {})
        auto_created_hash = hashlib.sha256(b"auto-created").hexdigest()[:16]
        meta['isAutoCreated'] = (
            owner.get('username') == 'owner' and
            owner.get('password_hash', '').startswith(auto_created_hash)
        )
        meta['memberCount'] = len(users_info.get('members', []))
        projects.append(meta)
    projects.sort(key=lambda p: p.get('created', ''), reverse=True)
    return projects

def get_project(proj_id):
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    if not os.path.isdir(proj_dir):
        return None
    meta = {'id': proj_id, 'name': proj_id, 'created': ''}
    meta_file = os.path.join(proj_dir, 'meta.json')
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta.update(json.load(f))
        except:
            pass
    return meta

def create_project(proj_id, name=None, owner_username=None, owner_password=None):
    """Create project dir + files. Optionally create owner account."""
    if name is None:
        name = proj_id
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', proj_id)
    proj_dir = os.path.join(PROJECTS_DIR, safe_name)
    os.makedirs(proj_dir, exist_ok=True)
    meta = {'id': safe_name, 'name': name, 'created': time.strftime('%Y-%m-%d %H:%M:%S')}
    with open(os.path.join(proj_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)
    for fname, default in [('topo.json', {'nodes': [], 'edges': []}), ('chat.json', []), ('oplog.json', [])]:
        fpath = os.path.join(proj_dir, fname)
        if not os.path.exists(fpath):
            with open(fpath, 'w') as f:
                json.dump(default, f)

    # Create owner account via auth module
    try:
        from . import auth
        if owner_username and owner_password:
            auth.add_project_user(safe_name, owner_username, owner_password, 'owner')
        else:
            auth.migrate_project_users(safe_name)
    except ImportError:
        # Auth not yet available, skip
        pass

    # Generate index.html
    idx_content = _generate_project_index(safe_name)
    with open(os.path.join(proj_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(idx_content)

    # Create default session
    create_session(safe_name, 'default')
    return meta

def delete_project(proj_id):
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    if os.path.isdir(proj_dir):
        shutil.rmtree(proj_dir)

def _generate_project_index(proj_name):
    """Generate index.html for a project with name injected."""
    global APP_DIR
    idx_path = os.path.join(APP_DIR or os.path.dirname(os.path.dirname(__file__)), 'index.html')
    if not os.path.exists(idx_path):
        return '<html><body><h1>NetOps</h1><p>index.html not found</p></body></html>'
    with open(idx_path, 'r', encoding='utf-8', errors='replace') as f:
        html = f.read()
    inj = "window._projId = " + json.dumps(proj_name) + ";\n  currentProjectId = " + json.dumps(proj_name) + ";"
    html = html.replace("window._projId = params.get('proj') || null;", inj)
    html = html.replace(
        "var currentProjectId = window._projId || null;",
        "var currentProjectId = " + json.dumps(proj_name) + ";"
    )
    return html

# ─── Session Management ───────────────────────────────────────────────────────
def get_project_sessions_dir(proj_id):
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    if not os.path.isdir(proj_dir):
        return None
    d = os.path.join(proj_dir, 'sessions')
    os.makedirs(d, exist_ok=True)
    return d

def get_all_sessions(proj_id):
    """Return list of session metadata."""
    sessions_dir = get_project_sessions_dir(proj_id)
    if not sessions_dir:
        return []
    sessions = []
    for sid in os.listdir(sessions_dir):
        meta_path = os.path.join(sessions_dir, sid, 'meta.json')
        msgs_path = os.path.join(sessions_dir, sid, 'messages.json')
        if os.path.isdir(os.path.join(sessions_dir, sid)):
            msgs = []
            if os.path.exists(msgs_path):
                try:
                    msgs = json.loads(open(msgs_path, encoding='utf-8').read())
                except:
                    pass
            meta = {}
            if os.path.exists(meta_path):
                try:
                    meta = json.loads(open(meta_path, encoding='utf-8').read())
                except:
                    pass
            sessions.append({
                'id': sid,
                'name': meta.get('name', sid),
                'date': meta.get('date', ''),
                'messageCount': len(msgs)
            })
    sessions.sort(key=lambda s: s.get('date', ''), reverse=True)
    return sessions

def create_session(proj_id, session_name=None):
    """Create a new session folder and return its id."""
    sessions_dir = get_project_sessions_dir(proj_id)
    sid = 's' + str(int(time.time())) + str(random.randint(1000, 9999))
    sdir = os.path.join(sessions_dir, sid)
    os.makedirs(sdir, exist_ok=True)
    meta = {
        'id': sid,
        'name': session_name or 'default',
        'date': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(os.path.join(sdir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(sdir, 'messages.json'), 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    return sid

def delete_session(proj_id, session_id):
    """Delete a session folder."""
    sdir = os.path.join(get_project_sessions_dir(proj_id), session_id)
    if os.path.isdir(sdir):
        shutil.rmtree(sdir)

def get_session_messages(proj_id, session_id):
    """Return messages list for a session."""
    sessions_dir = get_project_sessions_dir(proj_id)
    if not sessions_dir:
        return []
    path = os.path.join(sessions_dir, session_id, 'messages.json')
    if os.path.exists(path):
        try:
            return json.loads(open(path, encoding='utf-8').read())
        except:
            pass
    return []

def append_session_message(proj_id, session_id, role, content, ops=None):
    """Append a message to a session."""
    sessions_dir = get_project_sessions_dir(proj_id)
    if not sessions_dir:
        return None  # project not found, refuse write
    msgs = get_session_messages(proj_id, session_id)
    msg = {'role': role, 'content': content, 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    if ops:
        msg['ops'] = ops
    msgs.append(msg)
    sdir = os.path.join(sessions_dir, session_id)
    os.makedirs(sdir, exist_ok=True)
    path = os.path.join(sdir, 'messages.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(msgs, f, ensure_ascii=False, indent=2)
    return msgs
