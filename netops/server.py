#!/usr/bin/env python3
"""NetOps Server - Static file + Topology API + LLM Proxy + WebSocket + Project Auth + Terminal"""
import os, json, hashlib, urllib.parse, threading, time, uuid, re, sys, random, shutil, asyncio, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.request, urllib.error

# ──────────────────────────────────────────────
# [op] Format Patterns & Validator
# ──────────────────────────────────────────────
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
                # groups: (node_id, ,ip=..., ip, ,label=...)
                # When ,ip= is absent: (node_id, None, None, None, ,label=...)
                # When ,label= is absent: (node_id, None, None, None) or (node_id, ,ip=..., ip, None)
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
            else:  # get_topology
                params = {}
            return {'op': op_name, 'params': params}
    return None


# ──────────────────────────────────────────────
# System Prompt Template (new [op] format)
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """你是 NetOps 拓扑编辑器的 AI 助手，负责操作网络拓扑和管控网络设备。

## 语气风格
像和懂行的同事讨论。可以用"这个"、"其实"、"可以"等口语。不废话，有话直说。

## 当前项目状态
- 项目：{project_name}
- 节点数：{node_count}
- 拓扑：{topology_json}

---

## 操作格式
所有操作统一用 JSON 数组，放在 ops 字段里返回：

```json
[{"action":"操作类型", "参数1":"值", ...}]
```

### 拓扑操作（OpSkills）

| action | 说明 | 关键参数 |
|--------|------|---------|
| add_node | 添加设备 | id, type, x, y, ip, color |
| add_edge | 添加连线 | from, to, srcPort, tgtPort |
| move_node | 移动设备 | id, x, y |
| delete_node | 删除设备 | id |
| delete_edge | 删除连线 | from, to |
| modify_node | 修改属性 | id, label, ip, color |

**添加设备示例：**
```json
[{"action":"add_node","id":"Router-1","type":"router","x":300,"y":200,"ip":"192.168.1.1"}]
```

**添加连线示例：**
```json
[{"action":"add_edge","from":"Router-1","to":"Switch-1","srcPort":"ge0/0/1","tgtPort":"ge0/0/1"}]
```

**设备 type 可选值：** router | switch | firewall | server | PC | cloud

---

### 设备操控（Device Skills）

| action | 说明 | 关键参数 |
|--------|------|---------|
| device_connect | 连接设备 | protocol, ip, port, user, password |
| device_send | 发送命令 | session_id, cmd |
| device_expect | 等待确认提示 | session_id, pattern |
| device_confirm | 发送 Y/N | session_id, answer |
| device_wait | 等待处理 | ms |
| device_close | 关闭会话 | session_id |
| device_batch | 批量命令 | session_id, commands, delay_ms |

**连接设备示例（无需用户名密码）：**
```json
[{"action":"device_connect","protocol":"telnet","ip":"192.168.32.227","port":30007}]
```

**发送命令示例：**
```json
[{"action":"device_send","session_id":"{{session_id}}","cmd":"display version"}]
```

**完整流程示例（查看设备版本）：**
```json
[
  {"action":"device_connect","protocol":"telnet","ip":"192.168.32.227","port":30007},
  {"action":"device_send","session_id":"{{sid}}","cmd":"display version"},
  {"action":"device_close","session_id":"{{sid}}"}
]
```

---

### 查询操作（直接执行，不需要用户确认）

| action | 说明 |
|--------|------|
| ping | 检测连通性，{ip:"IP"} |
| get_topology_summary | 获取拓扑概览 |
| get_node_ip | 获取设备 IP，{id:"设备ID"} |
| select_node | 选中设备，{id:"设备ID"} |
| fit_view | 缩放视图适应全部 |
| toast | 提示消息，{message:"内容"} |
| save_project | 保存当前项目 |

---

## 核心规则（违反会被投诉）

1. **禁止自动连线**：用户没说"连接/连线/接入/互联"时，禁止 add_edge。
2. **设备存在才能连线**：add_edge 前设备必须已存在。
3. **类型匹配**：用户说"防火墙"→type=firewall，禁止乱填。
4. **端口不重复**：同一端口不能同时连两个设备。
5. **20台以上分批**：每批≤20台，必须同时有 add 和 add_edge。

## 危险操作
删除节点、批量修改等操作必须告知用户风险，等确认后再执行。

## 输出风格
- 简洁，不废话
- 操作结果用「✅成功/❌失败」格式
- 不主动创建文件或文档
"""

# Terminal PTY support
import pty, fcntl, select, signal, struct, termios
import queue as _queue

# WebSocket support (pip install websockets)
try:
    import websockets
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False
    print("[WebSocket] websockets library not found, real-time sync disabled")

# Open mode: skip login requirement for all project operations
OPEN_MODE = True

# Resolve APP_DIR (netops root)
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    APP_DIR = os.path.join(_exe_dir, 'app')
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Configurable paths via environment variables, default to APP_DIR-relative paths
PORT = int(os.environ.get('NETOPS_PORT', sys.argv[1] if len(sys.argv) > 1 else 9000))
BASE_DIR = APP_DIR
DATA_DIR = os.environ.get('NETOPS_DATA_DIR') or os.path.join(APP_DIR, 'data')
PROJECTS_DIR = os.path.join(DATA_DIR, 'projects')
UPLOADS_DIR = os.path.join(DATA_DIR, 'uploads')
CONFIG_DIR = os.environ.get('NETOPS_CONFIG_DIR') or os.path.join(APP_DIR, 'config')

# Create data directory on first run
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# LLM settings: use data/ai_soul.json (user data), fallback to config template
AI_SOUL_FILE = os.path.join(APP_DIR, 'ai_soul.json')
AI_SOUL_TEMPLATE = os.path.join(APP_DIR, 'ai_soul_template.json')
LLM_SETTINGS_FILE = os.path.join(APP_DIR, 'llm_settings.json')
LLM_SETTINGS_TEMPLATE = os.path.join(APP_DIR, 'llm_settings.json')
for src, dst in [(LLM_SETTINGS_TEMPLATE, LLM_SETTINGS_FILE),
                  (AI_SOUL_TEMPLATE, AI_SOUL_FILE)]:
    if not os.path.exists(dst) and os.path.exists(src):
        shutil.copy2(src, dst)

# ============================================================
# Auth: Super Admin (hardcoded)
# ============================================================
SUPER_ADMIN = {
    "username": "admin",
    # admin / admin 的 sha256 hash
    "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
    "role": "super"
}

# ============================================================
# Auth: In-memory session store
# session_token -> {username, role, project_id, expire_at}
# ============================================================
_session_store = {}          # token -> session dict
_session_lock = threading.Lock()
SESSION_TTL = 86400 * 7      # 7 days

def _gen_token():
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]

def _hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

def _new_session(username, role, project_id=None):
    """Create a new session, return (token, session_dict)."""
    token = _gen_token()
    with _session_lock:
        _session_store[token] = {
            "username": username,
            "role": role,          # 'super' | 'owner' | 'member'
            "project_id": project_id,  # None for super admin
            "created_at": time.time(),
            "expire_at": time.time() + SESSION_TTL,
        }
    return token

def _get_session(token):
    """Validate session, return session dict or None."""
    if not token:
        return None
    with _session_lock:
        s = _session_store.get(token)
        if not s:
            return None
        if time.time() > s["expire_at"]:
            del _session_store[token]
            return None
        return s

def _del_session(token):
    with _session_lock:
        _session_store.pop(token, None)

def _check_super(token):
    """Check if session token belongs to super admin."""
    s = _get_session(token)
    return s is not None and s.get("role") == "super"

def _check_project_access(token, project_id):
    """Check if session allows access to the given project.
    Super admin can access any project. Others must match project_id.
    """
    s = _get_session(token)
    if not s:
        return False
    if s.get("role") == "super":
        return True
    return s.get("project_id") == project_id

# ============================================================
# Auth: Project-level user management
# ============================================================
def get_project_users(project_id):
    """Load users.json for a project. Returns {} if not exists."""
    path = os.path.join(PROJECTS_DIR, project_id, 'users.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def save_project_users(project_id, users):
    """Save users.json for a project."""
    proj_dir = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    path = os.path.join(proj_dir, 'users.json')
    with open(path, 'w') as f:
        json.dump(users, f, indent=2)

def migrate_project_users(project_id):
    """Migrate existing project to have users.json (backward compat).
    Creates owner entry from 'default' user hash.
    """
    path = os.path.join(PROJECTS_DIR, project_id, 'users.json')
    if os.path.exists(path):
        return  # already has users.json

    users = {
        "owner": {
            "username": "owner",
            "password_hash": _hash_pw("owner"),
            "role": "owner"
        },
        "members": []
    }
    save_project_users(project_id, users)

def add_project_user(project_id, username, password, role):
    """Add a user to project. role must be 'owner' or 'member'."""
    users = get_project_users(project_id)
    pw_hash = _hash_pw(password)

    if role == "owner":
        users["owner"] = {"username": username, "password_hash": pw_hash, "role": "owner"}
    else:
        if "members" not in users:
            users["members"] = []
        # Check duplicate
        for m in users["members"]:
            if m["username"] == username:
                m["password_hash"] = pw_hash
                m["role"] = role
                save_project_users(project_id, users)
                return
        users["members"].append({"username": username, "password_hash": pw_hash, "role": role})

    save_project_users(project_id, users)

def verify_project_user(project_id, username, password):
    """Verify username/password against project users. Returns role or None."""
    # Super admin
    if username == SUPER_ADMIN["username"]:
        if password == "admin":
            return "super"
        return None

    users = get_project_users(project_id)
    pw_hash = _hash_pw(password)

    if users.get("owner", {}).get("username") == username:
        if users["owner"].get("password_hash") == pw_hash:
            return users["owner"].get("role", "owner")
        return None

    for m in users.get("members", []):
        if m.get("username") == username:
            if m.get("password_hash") == pw_hash:
                return m.get("role", "member")
            return None

    return None

def list_project_users(project_id):
    """Return list of all users (without password_hash) for a project."""
    users = get_project_users(project_id)
    result = []
    if users.get("owner"):
        o = users["owner"]
        result.append({"username": o["username"], "role": o["role"]})
    for m in users.get("members", []):
        result.append({"username": m["username"], "role": m["role"]})
    return result

def remove_project_user(project_id, username):
    """Remove a member by username. Returns True if removed."""
    users = get_project_users(project_id)
    if not users.get("members"):
        return False
    original_len = len(users["members"])
    users["members"] = [m for m in users["members"] if m["username"] != username]
    if len(users["members"]) < original_len:
        save_project_users(project_id, users)
        return True
    return False

# Migrate all existing projects on startup
def _migrate_all_projects():
    if not os.path.exists(PROJECTS_DIR):
        return
    for name in os.listdir(PROJECTS_DIR):
        proj_dir = os.path.join(PROJECTS_DIR, name)
        if os.path.isdir(proj_dir):
            migrate_project_users(name)

# ============================================================
# Topology store (legacy compat)
# ============================================================
topo_store = {}
_lock = threading.Lock()

def _key(u, p):
    return hashlib.md5(f"{u}::{p}".encode()).hexdigest()

def load_topo(u, p):
    k = _key(u, p)
    with _lock:
        if k in topo_store: return topo_store[k]
        path = os.path.join(DATA_DIR, k + ".json")
        if os.path.exists(path):
            with open(path) as f: topo_store[k] = json.load(f)
            return topo_store[k]
        return None

def save_topo(u, p, data):
    k = _key(u, p)
    with _lock:
        topo_store[k] = data
        path = os.path.join(DATA_DIR, k + ".json")
        with open(path, 'w') as f: json.dump(data, f)
    if WS_AVAILABLE:
        proj_id = p if p != 'default' else u
        ws_notify_topo_change(proj_id, data)

_llm_lock = threading.Lock()

def load_llm_settings():
    with _llm_lock:
        if os.path.exists(LLM_SETTINGS_FILE):
            try:
                with open(LLM_SETTINGS_FILE) as f:
                    s = json.load(f)
                    if 'api_key' in s and s['api_key']:
                        s['api_key_display'] = s['api_key'][:12] + '****' + s['api_key'][-6:] if len(s['api_key']) > 20 else '****'
                    return s
            except: pass
        return {}

def save_llm_settings(data):
    with _llm_lock:
        existing = {}
        if os.path.exists(LLM_SETTINGS_FILE):
            try:
                with open(LLM_SETTINGS_FILE) as f:
                    existing = json.load(f)
            except: pass
        existing.update(data)
        with open(LLM_SETTINGS_FILE, 'w') as f:
            json.dump(existing, f, indent=2)


# ============================================================
# Project Management (folder-based)
# ============================================================
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
                with open(meta_file) as f: meta.update(json.load(f))
            except: pass
        topo_file = os.path.join(proj_dir, 'topo.json')
        if os.path.exists(topo_file):
            try:
                with open(topo_file) as f:
                    t = json.load(f)
                    meta['nodeCount'] = len(t.get('nodes', []))
                    meta['edgeCount'] = len(t.get('edges', []))
            except: pass
        users_file = os.path.join(proj_dir, 'users.json')
        users_info = {}
        if os.path.exists(users_file):
            try:
                with open(users_file) as f: users_info = json.load(f)
            except: pass
        meta['hasOwner'] = bool(users_info.get('owner'))
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
            with open(meta_file) as f: meta.update(json.load(f))
        except: pass
    return meta

def create_project(proj_id, name=None, owner_username=None, owner_password=None):
    """Create project dir + files. Optionally create owner account."""
    if name is None:
        name = proj_id
    import re as re_module
    safe_name = re_module.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', proj_id)
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

    # Create owner account
    if owner_username and owner_password:
        users = {
            "owner": {
                "username": owner_username,
                "password_hash": _hash_pw(owner_password),
                "role": "owner"
            },
            "members": []
        }
        save_project_users(safe_name, users)
    else:
        # Backward compat: create default owner account
        migrate_project_users(safe_name)

    # Generate index.html for this project
    idx_content = generate_project_index(safe_name)
    with open(os.path.join(proj_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(idx_content)
    # Copy ai_soul.json into project folder
    soul_src = AI_SOUL_TEMPLATE
    soul_dst = os.path.join(proj_dir, 'ai_soul.json')
    if os.path.exists(soul_src) and not os.path.exists(soul_dst):
        with open(soul_src, 'r', encoding='utf-8') as src:
            with open(soul_dst, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
    # Create a default session
    create_session(safe_name, 'default')
    return meta

def delete_project(proj_id):
    import shutil
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    if os.path.isdir(proj_dir):
        shutil.rmtree(proj_dir)

# ──────────────────────────────────────────────
# Session Management (folder-based per project)
# ──────────────────────────────────────────────
def get_project_sessions_dir(proj_id):
    d = os.path.join(PROJECTS_DIR, proj_id, 'sessions')
    os.makedirs(d, exist_ok=True)
    return d

def get_all_sessions(proj_id):
    """Return list of session metadata."""
    sessions_dir = get_project_sessions_dir(proj_id)
    sessions = []
    for sid in os.listdir(sessions_dir):
        meta_path = os.path.join(sessions_dir, sid, 'meta.json')
        msgs_path = os.path.join(sessions_dir, sid, 'messages.json')
        if os.path.isdir(os.path.join(sessions_dir, sid)):
            msgs = []
            if os.path.exists(msgs_path):
                try: msgs = json.loads(open(msgs_path, encoding='utf-8').read())
                except: pass
            meta = {}
            if os.path.exists(meta_path):
                try: meta = json.loads(open(meta_path, encoding='utf-8').read())
                except: pass
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
        import shutil
        shutil.rmtree(sdir)

def get_session_messages(proj_id, session_id):
    """Return messages list for a session."""
    path = os.path.join(get_project_sessions_dir(proj_id), session_id, 'messages.json')
    if os.path.exists(path):
        try: return json.loads(open(path, encoding='utf-8').read())
        except: pass
    return []

def append_session_message(proj_id, session_id, role, content, ops=None):
    """Append a message to a session."""
    msgs = get_session_messages(proj_id, session_id)
    msg = {'role': role, 'content': content, 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    if ops:
        msg['ops'] = ops
    msgs.append(msg)
    sdir = os.path.join(get_project_sessions_dir(proj_id), session_id)
    os.makedirs(sdir, exist_ok=True)
    path = os.path.join(sdir, 'messages.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(msgs, f, ensure_ascii=False, indent=2)
    return msgs

def build_system_prompt(proj_id):
    """构建系统提示，使用新的 [op] 格式模板。"""
    topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
    nodes = topo.get('nodes', [])
    edges = topo.get('edges', [])
    # Build compact topology JSON snippet
    topo_snippets = []
    for n in nodes:
        avail = n.get('availablePorts', [])
        used = n.get('usedPorts', [])
        topo_snippets.append(
            f"  设备：{n.get('label','?')} [ID={n.get('id','')}] 类型={n.get('type','?')} IP={n.get('ip','') or '-'}"
            + (f" 已用端口: {', '.join(used)}" if used else "")
            + (f" 可用端口: {', '.join(avail[:6])}" if avail else "")
        )
    for e in edges:
        topo_snippets.append(f"  连线：{e.get('fromLabel','?')} --{e.get('srcPort','?')}→ {e.get('toLabel','?')} [{e.get('tgtPort','?')}]")
    topology_json = '\n'.join(topo_snippets) if topo_snippets else "（空拓扑）"

    return SYSTEM_PROMPT.format(
        project_name=proj_id,
        node_count=len(nodes),
        topology_json=topology_json
    )

def generate_project_index(proj_name):
    """Generate index.html for a project with name injected."""
    idx_path = os.path.join(BASE_DIR, 'index.html')
    if not os.path.exists(idx_path):
        return b'<html><body><h1>NetOps</h1><p>index.html not found</p></body></html>'
    with open(idx_path, 'r', encoding='utf-8', errors='replace') as f:
        html = f.read()
    inj = "window._projId = " + json.dumps(proj_name) + ";\n  currentProjectId = " + json.dumps(proj_name) + ";"
    html = html.replace("window._projId = params.get('proj') || null;", inj)
    html = html.replace(
        "var currentProjectId = window._projId || null;",
        "var currentProjectId = " + json.dumps(proj_name) + ";"
    )
    return html


def load_project_file(proj_id, fname, default=None):
    path = os.path.join(PROJECTS_DIR, proj_id, fname)
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except: pass
    return default

def save_project_file(proj_id, fname, data):
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    os.makedirs(proj_dir, exist_ok=True)
    path = os.path.join(proj_dir, fname)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    if fname == 'topo.json' and WS_AVAILABLE:
        ws_notify_topo_change(proj_id, data)


def call_llm_chat(api_url, api_key, model, messages, temperature=0.7, max_tokens=8192):
    """Proxy chat request to LLM provider."""
    base = api_url.rstrip('/')
    if '/anthropic' in base:
        url = base + '/v1/messages'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_key,
            'anthropic-version': '2023-06-01'
        }
        anthropic_messages = []
        for m in messages:
            if m.get('role') == 'system':
                anthropic_messages.append({'role': 'user', 'content': '[系统提示]\n' + m.get('content', '')})
            else:
                anthropic_messages.append({'role': m.get('role', 'user'), 'content': m.get('content', '')})
        payload = {
            'model': model,
            'messages': anthropic_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        req = urllib.request.Request(url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST')
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                text_parts = []
                for block in result.get('content', []):
                    if block.get('type') == 'text':
                        text_parts.append(block.get('text', ''))
                return '\n'.join(text_parts) if text_parts else '(无内容)'
        except TimeoutError:
            return f'⚠️ AI 响应超时（>{120}秒），请尝试简化问题或减少拓扑规模。'
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            return f'LLM调用失败: HTTP {e.code} {e.reason} | 详情: {body[:500]}'
        except Exception as e:
            return f'LLM调用失败: {str(e)}'
    else:
        url = base + '/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_key
        }
        payload = {
            'model': model,
            'messages': messages,
            'stream': False,
            'max_tokens': max_tokens
        }
        req = urllib.request.Request(url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST')
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except TimeoutError:
            return f'⚠️ AI 响应超时（>{120}秒），请尝试简化问题或减少拓扑规模。'
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            return f'LLM调用失败: HTTP {e.code} {e.reason} | 详情: {body[:500]}'
        except Exception as e:
            return f'LLM调用失败: {str(e)}'


# ============================================================
# HTTP Handler
# ============================================================
class H(BaseHTTPRequestHandler):
    def _cors(self, code=200):
        self.send_response(code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Session-Token')
        if code != 204: self.send_header('Content-Type', 'application/json')

    def _json(self, data, code=200):
        try:
            self._cors(code)
            self.end_headers()
            if code != 204:
                self.wfile.write(json.dumps(data).encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _send_login_resp(self, token, username, role, project_id, message):
        """发送登录响应，同时设置 netool_session cookie（供 Portal SSO 使用）"""
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

    def _auth(self, project_id=None):
        """Extract and validate session token from request.
        Returns (session_dict, error_response).
        If error_response is not None, send it and return (None, error_response).
        If project_id is given, also verify project access.
        In OPEN_MODE, always return a default super admin session.
        """
        if OPEN_MODE:
            return {'username': 'admin', 'role': 'super', 'project_id': project_id}, None
        token = None
        if hasattr(self, 'headers'):
            token = self.headers.get('X-Session-Token', '')
            cookie_str = self.headers.get('Cookie', '')
            if not token:
                # Try to extract from Cookie header
                for part in cookie_str.split(';'):
                    part = part.strip()
                    if part.startswith('netops_session='):
                        token = part.split('=', 1)[1].strip(' "\'')
                        break
        if not token:
            return None, {'error': '未登录，请先登录'}, 401
        s = _get_session(token)
        if not s:
            return None, {'error': '会话已过期，请重新登录'}, 401
        if project_id is not None and not _check_project_access(token, project_id):
            return None, {'error': '无权访问此项目'}, 403
        return s, None

    def _auth_super(self):
        """Require super admin session."""
        if OPEN_MODE:
            return {'username': 'admin', 'role': 'super'}, None
        token = self.headers.get('X-Session-Token', '')
        cookie_str = self.headers.get('Cookie', '')
        if not token:
            for part in cookie_str.split(';'):
                part = part.strip()
                if part.startswith('netops_session='):
                    token = part.split('=', 1)[1].strip(' "\'')
                    break
        if not token:
            return None, {'error': '未登录'}, 401
        s = _get_session(token)
        if not s or s.get('role') != 'super':
            return None, {'error': '需要超级管理员权限'}, 403
        return s, None

    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self._cors(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        path, qs = urllib.parse.unquote(parsed.path), urllib.parse.unquote(parsed.query)
        # GET /api/term/sessions - list sessions (FIXED: in do_GET)
        if path == '/api/term/sessions' and self.command == 'GET':
            with _term_sessions_lock:
                sessions_list = []
                for sid, info in _term_sessions.items():
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

        params = urllib.parse.parse_qs(qs)

        # GET /api/auth/verify?token=xxx — 验证 session token，返回用户信息
        if path == '/api/auth/verify':
            token = params.get('token', [None])[0]
            if not token:
                self._json({'valid': False, 'error': 'token 参数不能为空'}, 400); return
            s = _get_session(token)
            if s:
                self._json({
                    'valid': True,
                    'username': s['username'],
                    'role': s['role'],
                    'project_id': s.get('project_id'),
                })
            else:
                self._json({'valid': False, 'error': '会话已过期或不存在'})
            return

        # Auth check: session status
        if path == '/api/auth/status':
            token = self.headers.get('X-Session-Token', '')
            cookie_str = self.headers.get('Cookie', '')
            if not token:
                for part in cookie_str.split(';'):
                    part = part.strip()
                    if part.startswith('netops_session='):
                        token = part.split('=', 1)[1].strip(' "\'')
                        break
            s = _get_session(token)
            if s:
                self._json({
                    'logged_in': True,
                    'username': s['username'],
                    'role': s['role'],
                    'project_id': s.get('project_id'),
                })
            else:
                self._json({'logged_in': False})
            return

        if path == '/api/llm/settings':
            settings = load_llm_settings()
            self._json(settings)
            return

        if path == '/api/project/current':
            self._json({'id': 'default', 'name': '默认项目'})
            return
        if path == '/api/topology':
            self._json({})
            return
        if path.startswith('/api/topo'):
            project = params.get('projectId', ['default'])[0]
            topo = load_topo(project, project)
            self._json(topo)
            return
        if path == '/api/pending':
            self._json([])
            return
        if path == '/api/analysis-result':
            self._json(None)
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
                cmd = ['ping', '-c', '4', '-W', '3', ip]
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

        # GET /api/projects/ - list all projects (public, no auth needed)
        if path == '/api/projects/' or path == '/api/projects':
            self._json(get_all_projects())
            return

        # GET /api/projects/<id>/users - list users (auth required)
        m = re.match(r'^/api/projects/([^/]+)/users$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            users = list_project_users(proj_id)
            self._json({'users': users})
            return

        # GET /api/projects/<id>/topo - load topology (auth required)
        m = re.match(r'^/api/projects/([^/]+)/topo$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            self._json(topo)
            return
        # GET /api/projects/<id>/chat - load chat
        m = re.match(r'^/api/projects/([^/]+)/chat$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            chat = load_project_file(proj_id, 'chat.json', [])
            self._json(chat)
            return
        # GET /api/projects/<id>/oplog - load op log
        m = re.match(r'^/api/projects/([^/]+)/oplog$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            oplog = load_project_file(proj_id, 'oplog.json', [])
            self._json(oplog)
            return
        # GET /api/projects/<id>/meta - get project metadata
        m = re.match(r'^/api/projects/([^/]+)/meta$', path)
        if m:
            meta = get_project(m.group(1))
            if meta:
                self._json(meta)
            else:
                self._json({'error': 'not found'}, 404)
            return
        # GET /api/projects/<id>/sessions - list sessions
        m = re.match(r'^/api/projects/([^/]+)/sessions$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            sessions = get_all_sessions(proj_id)
            self._json(sessions)
            return
        # GET /api/projects/<id>/sessions/<sid>/messages
        m = re.match(r'^/api/projects/([^/]+)/sessions/([^/]+)/messages$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            msgs = get_session_messages(proj_id, m.group(2))
            self._json(msgs)
            return

        # GET /api/projects/<id>/files - list files in file_AIScreen/
        m = re.match(r'^/api/projects/([^/]+)/files$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            files_dir = os.path.join(PROJECTS_DIR, proj_id, 'file_AIScreen')
            if not os.path.exists(files_dir):
                self._json([]); return
            files = []
            for fname in os.listdir(files_dir):
                fpath = os.path.join(files_dir, fname)
                if os.path.isfile(fpath):
                    files.append({'name': fname, 'size': os.path.getsize(fpath)})
            self._json(files)
            return

        # GET /api/projects/<id>/files/<filename> - read file content
        m = re.match(r'^/api/projects/([^/]+)/files/(.+)$', path)
        if m:
            proj_id = m.group(1)
            fname = os.path.basename(m.group(2))
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            fpath = os.path.join(PROJECTS_DIR, proj_id, 'file_AIScreen', fname)
            if not os.path.exists(fpath):
                self._json({'error': '文件不存在'}, 404); return
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self._json({'name': fname, 'content': content})
            return

        # Project-aware routing
        if path in ('/', ''):
            if 'proj=' in qs:
                proj_name = params.get('proj', [''])[0]
                self.send_response(302)
                self.send_header('Location', '/' + proj_name)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            if not os.path.isdir(os.path.join(PROJECTS_DIR, 'Admin')):
                create_project('Admin', 'Admin')
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
            with open(fpath, 'rb') as f: self.wfile.write(f.read())
            return

        # Project sub-path: /<proj_name>/...
        path_parts = path.split('/')
        decoded_parts = [urllib.parse.unquote(p) for p in path_parts]
        if len(decoded_parts) >= 2 and decoded_parts[1] and decoded_parts[1] not in ('api', 'icons', 'webfonts', 'tools', 'data', 'css', 'js', 'fonts', 'uploads'):
            proj_name = decoded_parts[1]
            proj_dir = os.path.join(PROJECTS_DIR, proj_name)
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
                    content = generate_project_index(proj_name)
                    self.wfile.write(content.encode('utf-8'))
                else:
                    with open(fpath, 'rb') as f: self.wfile.write(f.read())
                return
            else:
                # File not found in project dir — try BASE_DIR (for shared libs like cytoscape.min.js)
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
                    with open(base_fpath, 'rb') as f: self.wfile.write(f.read())
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
            with open(fpath, 'rb') as f: self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<html><body><h1>404 Not Found</h1><p>文件不存在</p><a href="/projects.html">返回项目列表</a></body></html>'.encode('utf-8'))

    def do_DELETE(self):
        path = urllib.parse.unquote(self.path)
        # DELETE /api/projects/<proj> - delete project
        m = re.match(r'^/api/projects/([^/]+)$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            if s['role'] not in ('owner', 'super'):
                self._json({'error': '只有项目所有者或超级管理员可以删除项目'}, 403); return
            delete_project(proj_id)
            self._json({'status': 'ok'})
            return
        # DELETE /api/projects/<proj>/sessions/<sid>
        m = re.match(r'^/api/projects/([^/]+)/sessions/([^/]+)$', path)
        if m:
            proj_id = m.group(1)
            session_id = m.group(2)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            delete_session(proj_id, session_id)
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

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = urllib.parse.unquote(parsed.path), urllib.parse.unquote(parsed.query)
        params = urllib.parse.parse_qs(qs)
        length = int(self.headers.get('Content-Length', 0) or 0)
        body = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else '{}'
        try: parsed_body = json.loads(body); payload = parsed_body if isinstance(parsed_body, dict) else {}
        except: payload = {}

        # ── Auth: POST /api/projects/<id>/login ──────────────────────
        # Login disabled - auto-login as super admin for all requests
        m = re.match(r'^/api/projects/([^/]+)/login$', path)
        if m:
            proj_id = m.group(1)
            username = payload.get('username', '').strip() or 'admin'
            token = _new_session('admin', 'super', project_id=proj_id)
            self._send_login_resp(token, 'admin', 'super', proj_id, '登录成功（认证已禁用）')
            return

        # ── Auth: POST /api/projects/<id>/logout ──────────────────────
        m = re.match(r'^/api/projects/([^/]+)/logout$', path)
        if m:
            token = self.headers.get('X-Session-Token', '')
            if token:
                _del_session(token)
            self._json({'status': 'ok', 'message': '已退出登录'})
            return

        # ── Auth: POST /api/projects/<id>/register ────────────────────
        m = re.match(r'^/api/projects/([^/]+)/register$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            # Only owner or super can register
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
            add_project_user(proj_id, username, password, role)
            self._json({'status': 'ok', 'message': f'用户 {username} 已添加'})
            return

        # ── Auth: POST /api/projects/<id>/users/<username> DELETE ─────
        m = re.match(r'^/api/projects/([^/]+)/users/([^/]+)$', path)
        if m and self.command == 'DELETE':
            proj_id = m.group(1)
            target_user = m.group(2)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            if s['role'] not in ('owner', 'super'):
                self._json({'error': '只有项目所有者或超级管理员可以删除成员'}, 403); return
            if remove_project_user(proj_id, target_user):
                self._json({'status': 'ok', 'message': f'用户 {target_user} 已删除'})
            else:
                self._json({'error': '用户不存在'}, 404)
            return

        # ── Super Admin: GET /api/super/users ─────────────────────────
        if path == '/api/super/users':
            s, err = self._auth_super()
            if err:
                self._json(err, err.get('_code', 401)); return
            # List all users across all projects
            result = []
            if os.path.exists(PROJECTS_DIR):
                for name in os.listdir(PROJECTS_DIR):
                    proj_dir = os.path.join(PROJECTS_DIR, name)
                    if os.path.isdir(proj_dir):
                        users = get_project_users(name)
                        proj_users = []
                        if users.get("owner"):
                            proj_users.append({"username": users["owner"]["username"], "role": users["owner"]["role"]})
                        proj_users.extend([{"username": u["username"], "role": u["role"]} for u in users.get("members", [])])
                        result.append({"project_id": name, "project_name": get_project(name).get("name", name) if get_project(name) else name, "users": proj_users})
            self._json({"projects": result})
            return

        # ── Super Admin: GET /api/super/sessions ───────────────────────
        if path == '/api/super/sessions':
            s, err = self._auth_super()
            if err:
                self._json(err, err.get('_code', 401)); return
            with _session_lock:
                sessions = [{"token": k, "username": v["username"], "role": v["role"], "project_id": v.get("project_id"), "created": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(v["created_at"]))} for k, v in _session_store.items()]
            self._json({"sessions": sessions})
            return

        # ── Super Admin: DELETE /api/super/sessions/<token> ───────────
        m = re.match(r'^/api/super/sessions/([^/]+)$', path)
        if m and self.command == 'DELETE':
            s, err = self._auth_super()
            if err:
                self._json(err, err.get('_code', 401)); return
            token_to_del = m.group(1)
            _del_session(token_to_del)
            self._json({'status': 'ok'})
            return

        # ── Project Management: POST /api/projects/ ───────────────────
        if path == '/api/projects/' or path == '/api/projects':
            proj_name = payload.get('name', '')
            owner_username = payload.get('username', '').strip()
            owner_password = payload.get('password', '')
            if not proj_name:
                self._json({'error': '项目名称不能为空'}, 400); return
            import re as re_module
            safe_proj_id = re_module.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', proj_name)
            if not safe_proj_id:
                self._json({'error': '项目名称无效'}, 400); return
            if os.path.isdir(os.path.join(PROJECTS_DIR, safe_proj_id)):
                self._json({'error': '项目已存在'}, 409); return
            create_project(safe_proj_id, proj_name, owner_username, owner_password)
            self._json({'status': 'ok', 'id': safe_proj_id, 'name': proj_name, 'redirect': '/' + safe_proj_id})
            return

        # ── Project DELETE ────────────────────────────────────────────
        if path.startswith('/api/projects/') and (self.command == 'DELETE' or payload.get('_method') == 'delete'):
            m = re.match(r'^/api/projects/([^/]+)$', path)
            if m:
                proj_id = m.group(1)
                s, err = self._auth(proj_id)
                if err:
                    self._json(err, err.get('_code', 401)); return
                if s['role'] not in ('owner', 'super'):
                    self._json({'error': '只有项目所有者或超级管理员可以删除项目'}, 403); return
                delete_project(proj_id)
                self._json({'status': 'ok'})
                return

        # ── POST /api/projects/<proj>/sessions ───────────────────────
        m = re.match(r'^/api/projects/([^/]+)/sessions$', path)
        if m and self.command == 'POST':
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            session_name = payload.get('name')
            sid = create_session(proj_id, session_name)
            self._json({'status': 'ok', 'id': sid, 'name': session_name or 'default'})
            return

        # ── POST /api/projects/<id>/sessions/<sid>/messages ──────────
        m = re.match(r'^/api/projects/([^/]+)/sessions/([^/]+)/messages$', path)
        if m and self.command == 'POST':
            proj_id, session_id = m.group(1), m.group(2)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            role = payload.get('role', 'user')
            msg_content = payload.get('content', '')
            ops = payload.get('ops')
            append_session_message(proj_id, session_id, role, msg_content, ops)
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/topo ─────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/topo$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            topo_data = payload.get('data', payload)
            save_project_file(proj_id, 'topo.json', topo_data)
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/chat ─────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/chat$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            chat = payload.get('messages', payload)
            save_project_file(proj_id, 'chat.json', chat)
            self._json({'status': 'ok'})
            return

        # ── POST /api/projects/<id>/oplog ────────────────────────────
        m = re.match(r'^/api/projects/([^/]+)/oplog$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            oplog = payload.get('oplog', {}) if isinstance(payload, dict) else payload
            save_project_file(proj_id, 'oplog.json', oplog)
            self._json({'status': 'ok'})
            return

        # POST /api/projects/<id>/files - upload file to file_AIScreen/
        m = re.match(r'^/api/projects/([^/]+)/files$', path)
        if m:
            proj_id = m.group(1)
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            files_dir = os.path.join(PROJECTS_DIR, proj_id, 'file_AIScreen')
            os.makedirs(files_dir, exist_ok=True)
            filename = payload.get('name', 'untitled.txt')
            # 安全：只取 basename，防止路径穿越
            filename = os.path.basename(filename)
            content = payload.get('content', '')
            fpath = os.path.join(files_dir, filename)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            self._json({'ok': True, 'name': filename, 'size': len(content)})
            return

        # DELETE /api/projects/<id>/files/<filename>
        m = re.match(r'^/api/projects/([^/]+)/files/(.+)$', path)
        if m and self.command == 'DELETE':
            proj_id = m.group(1)
            fname = os.path.basename(m.group(2))
            s, err = self._auth(proj_id)
            if err:
                self._json(err, err.get('_code', 401)); return
            fpath = os.path.join(PROJECTS_DIR, proj_id, 'file_AIScreen', fname)
            if os.path.exists(fpath):
                os.remove(fpath)
            self._json({'ok': True})
            return

        # ── LLM Settings ─────────────────────────────────────────────
        if path == '/api/llm/settings':
            save_llm_settings(payload)
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
            reply = call_llm_chat(test_url, test_key, test_model, messages)
            if reply.startswith('LLM调用失败'):
                self._json({'ok': False, 'error': reply})
            else:
                self._json({'ok': True, 'reply': reply})
            return

        # ── Chat: proxy to LLM ────────────────────────────────────────
        if path == '/api/chat/send':
            settings = load_llm_settings()
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
                self._json({'reply': '请先在 AI设置 中配置 API Key 或 Access Token'}); return

            proj_id = payload.get('projectId', 'default')
            session_id = payload.get('sessionId', 'default')
            user_text = payload.get('text', '')
            if len(user_text) > 10000:
                self._json({'reply': '消息过长，请缩短内容后重试。', 'operations': []}); return
            topo_info = payload.get('topology', {})
            with_topo = payload.get('withTopo', False)
            topo_mode = payload.get('topoMode', 'detail')

            sys_prompt = build_system_prompt(proj_id)
            msgs_history = get_session_messages(proj_id, session_id)
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
                        if used: lines.append(f"    已用端口: {', '.join(used)}")
                        if avail: lines.append(f"    可用端口: {', '.join(avail[:6])}")
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
                if role not in ('user', 'assistant'): role = 'user'
                content = h.get('content', '')
                if content: messages.append({'role': role, 'content': content})
            attachment = payload.get('attachment', '')
            attachment_name = payload.get('attachmentName', '文档')
            if attachment:
                user_content = f"[用户上传了文档：{attachment_name}]\n[文档内容如下]\n{'='*40}\n{attachment}\n{'='*40}\n[文档内容结束]\n\n{user_content}"
            messages.append({'role': 'user', 'content': user_content})

            reply = call_llm_chat(api_url, api_key, model, messages, temperature, max_tokens_cfg)

            append_session_message(proj_id, session_id, 'user', user_content)
            append_session_message(proj_id, session_id, 'assistant', reply)

            # ── [op] 格式校验：如果 LLM 返回了 [op]，先校验格式 ──
            if '[op]' in reply:
                # 找出所有 [op] 行，逐条校验
                op_lines = []
                for line in reply.split('\n'):
                    if '[op]' in line:
                        op_lines.append(line.strip())
                invalid_lines = []
                for line in op_lines:
                    if parse_op(line) is None:
                        invalid_lines.append(line)
                if invalid_lines:
                    # 格式错误，要求 LLM 重新生成
                    correction_msg = (
                        "你的操作格式有误，正确格式示例：\n"
                        "[op] add:type=router,ip=192.168.1.1\n"
                        "[op] delete:node_id=node_001\n"
                        "[op] update:node_id=node_001,ip=10.0.0.1\n"
                        "[op] ping:ip=192.168.1.1\n"
                        "[op] terminal:ip=192.168.1.1,method=ssh,port=22\n"
                        "[op] backup:ip=192.168.1.1\n"
                        "[op] get_topology\n"
                        "请重新生成，格式必须严格符合上述规范。"
                    )
                    correction_messages = messages + [{'role': 'assistant', 'content': reply}, {'role': 'user', 'content': correction_msg}]
                    reply = call_llm_chat(api_url, api_key, model, correction_messages, temperature, max_tokens_cfg)
                    append_session_message(proj_id, session_id, 'user', correction_msg)
                    append_session_message(proj_id, session_id, 'assistant', reply)

            ops = []
            parts = re.split(r'\[op\]', reply)
            for part in parts[1:]:
                part = part.strip()
                m = re.match(r'^(\w+)[:：]\s*(.+)', part, re.DOTALL)
                if not m: continue
                action = m.group(1).strip()
                params_str = m.group(2).strip()
                params = {}
                for kv in re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)=([^+,\]]+)', params_str):
                    val = kv[1].strip().split('\n')[0].strip()
                    params[kv[0].strip()] = val
                for kv in re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*):\s*([^+,\]]+)', params_str):
                    key = kv[0].strip()
                    val = kv[1].strip().split('\n')[0].strip()
                    if key not in params:
                        params[key] = val
                if not params: continue
                if action == 'add':
                    def infer_device_type(device_id):
                        if not device_id: return 'switch'
                        d = device_id.lower()
                        if any(k in d for k in ['fw', 'firewall', '防火墙']): return 'firewall'
                        if any(k in d for k in ['rt', 'router', '边界路由']): return 'router'
                        if any(k in d for k in ['core-rt', 'corert', '核心路由']): return 'router_core'
                        if any(k in d for k in ['core-sw', 'coresw', 'coreswitch', '核心交换']): return 'switch_core'
                        if any(k in d for k in ['sw', 'switch', '交换机']): return 'switch'
                        if any(k in d for k in ['sv', 'server', '服务器']): return 'server'
                        if any(k in d for k in ['pc', 'host', '工作站']): return 'PC'
                        if any(k in d for k in ['cloud', 'internet', '云']): return 'cloud'
                        if any(k in d for k in ['wan', '广域网']): return 'wan'
                        return 'switch'
                    device_id = params.get('id', '') or ''
                    inferred_type = params.get('type', '')
                    if not inferred_type:
                        inferred_type = infer_device_type(device_id)
                    ops.append({
                        'action': 'add', 'type': inferred_type,
                        'id': params.get('id') or None,
                        'x': int(params.get('x', 200)), 'y': int(params.get('y', 200)),
                        'label': params.get('label') or params.get('id') or None
                    })
                elif action in ('delete', 'del'):
                    ops.append({'action': 'delete', 'id': params.get('id') or params.get('name') or params.get('label') or ''})
                elif action in ('add_edge', 'connect', 'add_connection'):
                    def clean(s):
                        if not s: return ''
                        s = str(s).strip()
                        idx = s.find('\n')
                        if idx >= 0: s = s[:idx]
                        idx = s.find('---')
                        if idx >= 0: s = s[:idx]
                        return s.strip()
                    ops.append({
                        'action': 'add_edge',
                        'from': clean(params.get('from', '')), 'to': clean(params.get('to', '')),
                        'srcPort': clean(params.get('src_port', '') or params.get('src', '') or params.get('from_port', '')),
                        'tgtPort': clean(params.get('tgt_port', '') or params.get('tgt', '') or params.get('to_port', ''))
                    })
                elif action == 'remove_edge':
                    ops.append({'action': 'remove_edge', 'from': params.get('from', ''), 'to': params.get('to', '')})
                elif action in ('update', 'update_node'):
                    ops.append({'action': 'update_node', 'id': params.get('id') or '',
                        'label': params.get('label') or '', 'ip': params.get('ip') or '',
                        'mac': params.get('mac') or '', 'desc': params.get('desc') or '',
                        'port': params.get('port') or '', 'bandwidth': params.get('bandwidth') or ''})
                elif action == 'rename':
                    ops.append({'action': 'rename', 'from': params.get('from', ''), 'to': params.get('to', '')})
                elif action == 'move':
                    ops.append({'action': 'move_node', 'id': params.get('id') or '', 'x': int(params.get('x', 300)), 'y': int(params.get('y', 200))})
                elif action == 'update_edge':
                    ops.append({'action': 'update_edge', 'from': params.get('from', ''), 'to': params.get('to', ''),
                        'src_port': params.get('src_port', ''), 'tgt_port': params.get('tgt_port', ''),
                        'bandwidth': params.get('bandwidth', ''), 'label': params.get('label', '')})
                elif action in ('add_shape', 'add_rect', 'add_ellipse'):
                    ops.append({'action': 'add_shape', 'id': params.get('id', ''),
                        'type': params.get('type', 'rect'), 'x': int(params.get('x', 300)), 'y': int(params.get('y', 200)),
                        'width': int(params.get('width', params.get('w', 180))), 'height': int(params.get('height', params.get('h', 100))),
                        'label': params.get('label', ''), 'color': params.get('color', '#ef4444'),
                        'bg': params.get('bg', 'transparent'), 'fg': params.get('fg', '#1f2937')})
                elif action == 'update_shape':
                    ops.append({'action': 'update_shape', 'id': params.get('id', ''),
                        'label': params.get('label', ''), 'color': params.get('color', ''),
                        'bg': params.get('bg', ''), 'fg': params.get('fg', '')})
                elif action == 'delete_shape':
                    ops.append({'action': 'delete_shape', 'id': params.get('id', '')})
                elif action == 'add_textbox':
                    ops.append({'action': 'add_textbox', 'content': params.get('content', params.get('text', params.get('label', '文本'))),
                        'x': int(params.get('x', 300)), 'y': int(params.get('y', 200)),
                        'bg': params.get('bg', '#fff7ed'), 'color': params.get('color', '#1f2937')})

            self._json({'reply': reply, 'operations': ops, '_debug_ops_count': len(ops)})
            return

        # Legacy topology save
        if path.startswith('/api/save') or path.startswith('/api/topo'):
            project = params.get('projectId', [payload.get('project', 'default')])[0]
            if path.startswith('/api/topo'):
                save_topo(project, project, {'nodes': payload.get('nodes', []), 'edges': payload.get('edges', [])})
            else:
                save_topo(payload.get('username', 'default'), payload.get('project', 'default'), payload.get('data', {}))
            self._json({'status': 'ok'})
            return

        # ── Terminal: POST /api/term/sessions ───────────────────────────
        if path == '/api/term/sessions' and self.command == 'POST':
            stype = payload.get('type', 'shell')
            ip = payload.get('ip', '')
            port = payload.get('port', '')
            user = payload.get('user', '')
            password = payload.get('password', '')
            sid = str(uuid.uuid4())
            try:
                _term_session_queue.put(('create', (sid, stype, ip, str(port), user, password)))
                # Brief wait for session creation
                for _ in range(20):
                    with _term_sessions_lock:
                        if sid in _term_sessions:
                            break
                    time.sleep(0.05)
                self._json({'id': sid, 'ws_port': TERM_WS_PORT}, 201)
            except Exception as e:
                self._json({'error': str(e)}, 400)
            return

        # ── Terminal: DELETE /api/term/sessions/<sid> ────────────────────
        m = re.match(r'^/api/term/sessions/([\w-]+)$', path)
        if m and self.command == 'DELETE':
            sid = m.group(1)
            _term_session_queue.put(('kill', sid))
            time.sleep(0.1)
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            return

        # ── Terminal: GET /api/term/sessions ────────────────────────────
        if path == '/api/term/sessions' and self.command == 'GET':
            with _term_sessions_lock:
                self._json({'sessions': list(_term_sessions.keys())})
            return

        self._json({'error': 'not found'}, 404)


class T(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# ============================================================
# WebSocket Server
# ============================================================
WS_PORT = int(os.environ.get('NETOPS_WS_PORT', 9002))
ws_clients = set()
ws_topo_lock = threading.Lock()
ws_latest_topo = {}

def ws_broadcast(msg):
    if not WS_AVAILABLE or not ws_clients:
        return
    def _do_send():
        async def _send_all():
            msg_bytes = json.dumps(msg).encode('utf-8')
            for client in list(ws_clients):
                try:
                    await client.send(msg_bytes)
                except Exception:
                    ws_clients.discard(client)
        try:
            asyncio.run(_send_all())
        except Exception:
            pass
    t = threading.Thread(target=_do_send, daemon=True)
    t.start()

def ws_notify_topo_change(proj_id, topo):
    if not WS_AVAILABLE:
        return
    with ws_topo_lock:
        ws_latest_topo[proj_id] = topo
    ws_broadcast({'type': 'topo_update', 'project': proj_id, 'topo': topo})

async def ws_handler(websocket):
    ws_clients.add(websocket)
    proj_id = None
    try:
        try:
            path = websocket.request.path
        except AttributeError:
            path = str(websocket.path) if hasattr(websocket, 'path') else '/'
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[0] == 'ws' and parts[1] == 'topo':
            proj_id = parts[2]
        with ws_topo_lock:
            current = ws_latest_topo.get(proj_id, {})
        await websocket.send(json.dumps({'type': 'init', 'project': proj_id, 'topo': current}))
        async for msg in websocket:
            try:
                data = json.loads(msg)
                if data.get('type') == 'subscribe':
                    proj_id = data.get('project', proj_id)
                    with ws_topo_lock:
                        current = ws_latest_topo.get(proj_id, {})
                    await websocket.send(json.dumps({'type': 'init', 'project': proj_id, 'topo': current}))
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    finally:
        ws_clients.discard(websocket)

def start_ws_server():
    if not WS_AVAILABLE:
        return
    async def run():
        try:
            async with websockets.serve(ws_handler, '0.0.0.0', WS_PORT):
                print(f'[WebSocket] Real-time sync server running on ws://0.0.0.0:{WS_PORT}')
                await asyncio.Future()
        except Exception as e:
            print(f'[WebSocket] Server error: {e}')
    def _runner():
        try:
            asyncio.run(run())
        except Exception as e:
            print(f'[WebSocket] Runner error: {e}')
    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    print(f'[WebSocket] Starting real-time sync server on port {WS_PORT}...')


# ============================================================
# Terminal PTY Session Management
# ============================================================
TERM_WS_PORT = 9011
_term_sessions = {}       # sid -> {'pid': int, 'master_fd': int}
_term_active_ws = {}      # sid -> [websocket]
_term_sessions_lock = threading.Lock()
_term_session_queue = _queue.Queue()

def _term_session_manager_thread():
    """Background thread that creates/manages PTY sessions (avoids forkpty deadlock in multi-threaded context)."""
    while True:
        task = _term_session_queue.get()
        if task is None:
            break
        action, data = task
        if action == 'create':
            sid, stype, ip, port, user, password = data
            _do_term_create_session(sid, stype, ip, port, user, password)
        elif action == 'kill':
            sid = data
            _do_term_kill_session(sid)

def _do_term_create_session(sid, stype, ip, port, user, password):
    """Create PTY session using forkpty."""
    try:
        m, s = pty.openpty()
        pid = os.fork()
        if pid == 0:
            os.close(m)
            try:
                import tty
                tty.setcontrollingterm(s)
            except Exception:
                pass
            os.setsid()
            try:
                fcntl.ioctl(s, termios.TIOCSCTTY, 0)
            except Exception:
                pass
            os.dup2(s, 0)
            os.dup2(s, 1)
            os.dup2(s, 2)
            if s > 2:
                os.close(s)
            env = dict(os.environ, TERM='xterm-256color', PS1='$ ')
            if stype == 'shell':
                os.execvpe('bash', ['bash', '-i'], env)
            elif stype == 'ssh':
                cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                if password and shutil.which('sshpass'):
                    cmd = ['sshpass', '-p', password] + cmd
                if user:
                    cmd += ['-l', user]
                if port and str(port) not in ('22', ''):
                    cmd += ['-p', str(port)]
                cmd.append(ip)
                os.execvpe(cmd[0], cmd, env)
            elif stype == 'telnet':
                os.execvpe('sh', ['sh', '-c', f'telnet {ip} {port}'], env)
            else:
                os._exit(127)
        os.close(s)
        with _term_sessions_lock:
            _term_sessions[sid] = {'pid': pid, 'master_fd': m, 'ip': ip, 'port': str(port), 'protocol': stype, 'user': user, 'created_at': time.time()}

        def reader():
            try:
                while True:
                    try:
                        res = os.waitpid(pid, os.WNOHANG)
                        if res[0] != 0:
                            while True:
                                r, _, _ = select.select([m], [], [], 0.1)
                                if not r:
                                    break
                                d = os.read(m, 4096)
                                if not d:
                                    break
                                _term_broadcast(sid, d)
                            break
                    except ChildProcessError:
                        break
                    r, _, _ = select.select([m], [], [], 0.5)
                    if r:
                        d = os.read(m, 4096)
                        if not d:
                            break
                        _term_broadcast(sid, d)
            except Exception:
                pass
            finally:
                try:
                    os.close(m)
                except Exception:
                    pass
                with _term_sessions_lock:
                    _term_sessions.pop(sid, None)
                    _term_active_ws.pop(sid, None)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
    except Exception as e:
        print(f'[Terminal] Failed to create session: {e}')

def _term_broadcast(sid, data):
    """Broadcast bytes to all WebSocket clients of a terminal session."""
    try:
        text = data.decode('utf-8', 'replace')
        msg = json.dumps({'type': 'output', 'data': text})
        ws_list = _term_active_ws.get(sid, [])
        for ws in list(ws_list):
            try:
                asyncio.run(ws.send(msg))
            except Exception:
                pass
    except Exception:
        pass

def _do_term_kill_session(sid):
    with _term_sessions_lock:
        info = _term_sessions.get(sid)
    if not info:
        return
    try:
        os.close(info['master_fd'])
    except Exception:
        pass
    try:
        os.kill(info['pid'], signal.SIGTERM)
        os.waitpid(info['pid'], 0)
    except Exception:
        pass
    with _term_sessions_lock:
        _term_sessions.pop(sid, None)
        _term_active_ws.pop(sid, None)

async def term_ws_handler(websocket):
    """Handle terminal WebSocket connections at /ws/<sid>."""
    try:
        path = websocket.request.path
    except AttributeError:
        path = str(websocket.path) if hasattr(websocket, 'path') else '/'
    sid = path.lstrip('/')
    if sid.startswith('ws/'):
        sid = sid[3:]

    with _term_sessions_lock:
        if sid not in _term_sessions:
            try:
                await websocket.send(json.dumps({'type': 'error', 'data': 'Session not found'}))
                await websocket.close()
            except Exception:
                pass
            return
        if sid not in _term_active_ws:
            _term_active_ws[sid] = []
        _term_active_ws[sid].append(websocket)

    try:
        async for msg in websocket:
            try:
                m = json.loads(msg)
            except Exception:
                continue
            with _term_sessions_lock:
                info = _term_sessions.get(sid)
            if not info:
                break
            if m.get('type') == 'input':
                data = m.get('data', '')
                if data:
                    try:
                        os.write(info['master_fd'], data.encode('utf-8'))
                    except Exception:
                        pass
            elif m.get('type') == 'resize':
                try:
                    fcntl.ioctl(info['master_fd'], termios.TIOCSWINSZ,
                                struct.pack('HHHH', m.get('rows', 24), m.get('cols', 80), 0, 0))
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        with _term_sessions_lock:
            if sid in _term_active_ws and websocket in _term_active_ws[sid]:
                _term_active_ws[sid].remove(websocket)

def start_term_ws_server():
    """Start the terminal WebSocket server on port 9011."""
    async def run():
        try:
            async with websockets.serve(term_ws_handler, '0.0.0.0', TERM_WS_PORT,
                                        extra_headers={
                                            'Access-Control-Allow-Origin': '*',
                                            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                                            'Access-Control-Allow-Headers': 'Content-Type',
                                        }):
                print(f'[Terminal] WebSocket server running on ws://0.0.0.0:{TERM_WS_PORT}')
                await asyncio.Future()
        except Exception as e:
            print(f'[Terminal] WebSocket server error: {e}')
    def _runner():
        try:
            asyncio.run(run())
        except Exception as e:
            print(f'[Terminal] WebSocket runner error: {e}')
    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    print(f'[Terminal] Starting WebSocket server on port {TERM_WS_PORT}...')

# Start terminal session manager thread (imports already done at module level)
_term_mgr_t = threading.Thread(target=_term_session_manager_thread, daemon=True)
_term_mgr_t.start()
print('[Terminal] Session manager thread started')
# Start terminal WebSocket server
start_term_ws_server()
print(f'[Terminal] WebSocket server started on port {TERM_WS_PORT}')

if __name__ == '__main__':
    # Migrate existing projects to have users.json
    _migrate_all_projects()
    # Disable WebSocket by default
    WS_AVAILABLE = False
    print(f'NetOps: http://192.168.32.72:{PORT}')
    T(('0.0.0.0', PORT), H).serve_forever()
