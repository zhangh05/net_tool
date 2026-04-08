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


def extract_json_ops(text: str):
    """Extract operations from JSON blocks in AI reply text (e.g. ```json [...] ```)."""
    ops = []
    # 匹配 JSON 数组或对象
    json_re = re.compile(r'\[\s*\{"action"[^{}]*\}\s*\]|\{\s*"action"[^}]+\}', re.DOTALL)
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


def _execute_single_action(action, params, nodes, edges):
    """Execute a single topology action. Returns dict with action, ok, and result fields.
    Used by both single-action and batch modes of /api/agent/execute.
    Modifies nodes/edges in place.
    """
    result = {'action': action, 'ok': False, 'error': None}

    def find_node(nid):
        for n in nodes:
            if n.get('id') == nid or n.get('label', '').lower() == str(nid).lower(): return n
        return None

    def find_edge(src, tgt):
        for e in edges:
            if (e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt): return e
            if (e.get('source') == tgt or e.get('from') == tgt) and (e.get('target') == src or e.get('to') == src): return e
        return None

    try:
        if action == 'add_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'add_node 需要 id 参数'; return result
            if find_node(nid):
                result['error'] = f'设备 {nid} 已存在'; return result
            ntype = params.get('type', 'switch')
            nip = params.get('ip', '')
            nlabel = params.get('label', nid)
            if params.get('x') is not None and params.get('y') is not None:
                nx, ny = int(params.get('x')), int(params.get('y'))
            else:
                nx, ny = _next_grid_pos()
            nodes.append({'id': nid, 'type': ntype, 'label': nlabel, 'ip': nip, '_x': nx, '_y': ny, 'availablePorts': params.get('availablePorts', []), 'usedPorts': params.get('usedPorts', [])})
            result['ok'] = True
            result['id'] = nid
            result['node'] = nid

        elif action == 'add_edge':
            src = params.get('from') or params.get('from_node') or params.get('src', '')
            tgt = params.get('to') or params.get('to_node') or params.get('tgt', '')
            if not src or not tgt:
                result['error'] = 'add_edge 需要 from 和 to'; return result
            sn = find_node(src); tn = find_node(tgt)
            if not sn:
                result['error'] = f'源设备 {src} 不存在'; return result
            if not tn:
                result['error'] = f'目标设备 {tgt} 不存在'; return result
            if find_edge(src, tgt):
                result['error'] = f'{src} 和 {tgt} 之间已有连线'; return result
            sp = params.get('srcPort', ''); tp = params.get('tgtPort', '')
            # 端口冲突检测
            used_ports_src = sn.get('usedPorts', [])
            used_ports_tgt = tn.get('usedPorts', [])
            if sp and sp in used_ports_src:
                result['error'] = f'{src} 的端口 {sp} 已被占用，请换一个端口（如 GE0/0/2）'; return result
            if tp and tp in used_ports_tgt:
                result['error'] = f'{tgt} 的端口 {tp} 已被占用，请换一个端口（如 GE0/0/2）'; return result
            # 更新 usedPorts
            if sp:
                sn['usedPorts'] = used_ports_src + [sp]
            if tp:
                tn['usedPorts'] = used_ports_tgt + [tp]
            edges.append({'source': sn['id'], 'target': tn['id'], 'from': sn['id'], 'to': tn['id'], 'fromLabel': sn.get('label', sn['id']), 'toLabel': tn.get('label', tn['id']), 'srcPort': sp, 'tgtPort': tp, 'edgeStyle': 'solid', 'edgeColor': '#374151', 'edgeWidth': 2})
            result['ok'] = True
            result['edge'] = src + ' -> ' + tgt

        elif action == 'delete_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'delete_node 需要 id'; return result
            nn = find_node(nid)
            if not nn:
                result['error'] = f'设备 {nid} 不存在'; return result
            nid_r = nn.get('id')
            # 删除连接该节点的所有边时，释放另一端的端口
            remaining_edges = []
            for e in edges:
                if e.get('source') == nid_r or e.get('from') == nid_r or e.get('target') == nid_r or e.get('to') == nid_r:
                    # 释放另一端节点的端口
                    other_id = e.get('target') or e.get('to')
                    if other_id == nid_r:
                        other_id = e.get('source') or e.get('from')
                    other_node = find_node(other_id)
                    if other_node:
                        sp = e.get('srcPort', '')
                        tp = e.get('tgtPort', '')
                        # 判断方向，释放对应的端口
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
                result['error'] = 'delete_edge 需要 from 和 to'; return result
            sn = find_node(src); tn = find_node(tgt)
            removed = False
            for i, e in enumerate(edges):
                if (e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt):
                    # 释放端口
                    sp = e.get('srcPort', '')
                    tp = e.get('tgtPort', '')
                    if sp and sn and sp in sn.get('usedPorts', []):
                        sn['usedPorts'].remove(sp)
                    if tp and tn and tp in tn.get('usedPorts', []):
                        tn['usedPorts'].remove(tp)
                    edges.pop(i); removed = True; break
                if (e.get('source') == tgt or e.get('from') == tgt) and (e.get('target') == src or e.get('to') == src):
                    # 释放端口（方向反过来）
                    sp = e.get('srcPort', '')
                    tp = e.get('tgtPort', '')
                    if sp and tn and sp in tn.get('usedPorts', []):
                        tn['usedPorts'].remove(sp)
                    if tp and sn and tp in sn.get('usedPorts', []):
                        sn['usedPorts'].remove(tp)
                    edges.pop(i); removed = True; break
            if not removed:
                result['error'] = f'连线 {src} <-> {tgt} 不存在'; return result
            result['ok'] = True
            result['deleted'] = src + ' <-> ' + tgt

        elif action == 'modify_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'modify_node 需要 id'; return result
            nn = find_node(nid)
            if not nn:
                result['error'] = f'设备 {nid} 不存在'; return result
            if 'label' in params: nn['label'] = params['label']
            if 'ip' in params: nn['ip'] = params['ip']
            if 'type' in params: nn['type'] = params['type']
            result['ok'] = True
            result['updated'] = nid

        elif action == 'move_node':
            nid = params.get('id')
            if not nid:
                result['error'] = 'move_node 需要 id'; return result
            nn = find_node(nid)
            if not nn:
                result['error'] = f'设备 {nid} 不存在'; return result
            nn['_x'] = int(params.get('x', 300))
            nn['_y'] = int(params.get('y', 200))
            result['ok'] = True
            result['moved'] = nid

        else:
            result['error'] = f'未知 action: {action}'

    except Exception as e:
        result['error'] = str(e)

    return result


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
[{{"action":"操作类型", "参数1":"值", ...}}]
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
[{{"action":"add_node","id":"Router-1","type":"router","x":300,"y":200,"ip":"192.168.1.1"}}]
```

**添加连线示例：**
```json
[{{"action":"add_edge","from":"Router-1","to":"Switch-1","srcPort":"ge0/0/1","tgtPort":"ge0/0/1"}}]
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
[{{"action":"device_connect","protocol":"telnet","ip":"192.168.32.227","port":30007}}]
```

**发送命令示例：**
```json
[{{"action":"device_send","session_id":"{{{{session_id}}}}","cmd":"display version"}}]
```

**完整流程示例（查看设备版本）：**
```json
[
  {{"action":"device_connect","protocol":"telnet","ip":"192.168.32.227","port":30007}},
  {{"action":"device_send","session_id":"{{{{sid}}}}","cmd":"display version"}},
  {{"action":"device_close","session_id":"{{{{sid}}}}"}}
]
```

---

### 查询操作（直接执行，不需要用户确认）

| action | 说明 |
|--------|------|
| ping | 检测连通性，{{ip:"IP"}} |
| get_topology_summary | 获取拓扑概览 |
| get_node_ip | 获取设备 IP，{{id:"设备ID"}} |
| select_node | 选中设备，{{id:"设备ID"}} |
| fit_view | 缩放视图适应全部 |
| toast | 提示消息，{{message:"内容"}} |
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

# 全局批量添加位置计数器（跨请求持久）
_GLOBAL_BATCH_POS = {'count': 0}

def _next_grid_pos():
    """为批量添加的节点分配网格位置，避免重叠。"""
    cols = 4
    spacing_x, spacing_y = 200, 160
    row = _GLOBAL_BATCH_POS['count'] // cols
    col = _GLOBAL_BATCH_POS['count'] % cols
    x = 200 + col * spacing_x
    y = 200 + row * spacing_y
    _GLOBAL_BATCH_POS['count'] += 1
    return x, y
UPLOADS_DIR = os.path.join(DATA_DIR, 'uploads')
CONFIG_DIR = os.environ.get('NETOPS_CONFIG_DIR') or os.path.join(APP_DIR, 'config')

# Create data directory on first run
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# LLM settings: use data/ai_soul.json (user data), fallback to config template
AI_SOUL_FILE = os.path.join(APP_DIR, 'AI_sys_prompt', 'ai_soul.json')
AI_SOUL_TEMPLATE = os.path.join(APP_DIR, 'AI_sys_prompt', 'ai_soul_template.json')
AI_SYSTEM_PROMPT_FILE = os.path.join(APP_DIR, 'AI_sys_prompt', 'ai_system_prompt.txt')
AI_SKILLS_FILE = os.path.join(APP_DIR, 'AI_sys_prompt', 'ai-skills.txt')
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
        # FIX: when u == p (project topo), read from projects/{id}/topo.json
        # this matches the path used by save_topo
        if u == p:
            path = os.path.join(PROJECTS_DIR, u, 'topo.json')
        else:
            path = os.path.join(DATA_DIR, k + ".json")
        if os.path.exists(path):
            with open(path) as f: topo_store[k] = json.load(f)
            return topo_store[k]
        return None

def save_topo(u, p, data):
    k = _key(u, p)
    with _lock:
        topo_store[k] = data
        # FIX: when u == p (project topo), save to projects/{id}/topo.json
        # this matches the path used by save_project_file / load_project_file
        if u == p:
            proj_dir = os.path.join(PROJECTS_DIR, u)
            os.makedirs(proj_dir, exist_ok=True)
            # Ensure all project files exist (fix for auto-created projects missing meta.json, index.html, etc.)
            _ensure_project_files(proj_dir, u)
            path = os.path.join(proj_dir, 'topo.json')
        else:
            path = os.path.join(DATA_DIR, k + ".json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f: json.dump(data, f)
    if WS_AVAILABLE:
        proj_id = p if p != 'default' else u
        ws_notify_topo_change(proj_id, data)

def _ensure_project_files(proj_dir, proj_id):
    """Ensure all necessary project files exist. Call when creating/accessing a project."""
    import hashlib
    import time as time_module
    
    # meta.json
    meta_file = os.path.join(proj_dir, 'meta.json')
    if not os.path.exists(meta_file):
        meta = {'id': proj_id, 'name': proj_id, 'created': time_module.strftime('%Y-%m-%d %H:%M:%S')}
        with open(meta_file, 'w') as f:
            json.dump(meta, f, indent=2)
    
    # topo.json (empty if not exists)
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
    
    # users.json (owner only, no password - auto-created projects don't need login)
    users_file = os.path.join(proj_dir, 'users.json')
    if not os.path.exists(users_file):
        users = {
            "owner": {
                "username": "owner",
                "password_hash": hashlib.sha256(b"auto-created").hexdigest()[:16],
                "role": "owner"
            },
            "members": []
        }
        with open(users_file, 'w') as f:
            json.dump(users, f, indent=2)
    
    # index.html (copy from template if not exists)
    index_file = os.path.join(proj_dir, 'index.html')
    if not os.path.exists(index_file):
        template_index = os.path.join(os.path.dirname(__file__), 'index.html')
        if os.path.exists(template_index):
            import shutil
            shutil.copy(template_index, index_file)
    
    # sessions/default (create default session if not exists)
    sessions_dir = os.path.join(proj_dir, 'sessions')
    os.makedirs(sessions_dir, exist_ok=True)
    default_session_dir = os.path.join(sessions_dir, 'default')
    if not os.path.exists(default_session_dir):
        os.makedirs(default_session_dir, exist_ok=True)
        with open(os.path.join(default_session_dir, 'meta.json'), 'w') as f:
            json.dump({'id': 'default', 'name': 'default'}, f)
        with open(os.path.join(default_session_dir, 'messages.json'), 'w') as f:
            json.dump([], f)

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
        # Check if auto-created: owner username is 'owner' and password_hash matches auto-created hash
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
    proj_dir = os.path.join(PROJECTS_DIR, proj_id)
    # 不自动创建父级项目目录，只在项目已存在时创建 sessions
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
    sessions_dir = get_project_sessions_dir(proj_id)
    if not sessions_dir:
        return []
    path = os.path.join(sessions_dir, session_id, 'messages.json')
    if os.path.exists(path):
        try: return json.loads(open(path, encoding='utf-8').read())
        except: pass
    return []

def append_session_message(proj_id, session_id, role, content, ops=None):
    """Append a message to a session."""
    sessions_dir = get_project_sessions_dir(proj_id)
    if not sessions_dir:
        return None  # 项目不存在，拒绝写入
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
# ──────────────────────────────────────────────
# Async Chat Task Infrastructure
# ──────────────────────────────────────────────
import threading as _threading
PENDING_TASKS = {}   # {task_id: {'status': 'pending'|'done'|'error', 'reply': '', 'ops': [], 'error': ''}}
def _create_task():
    task_id = 't' + str(int(time.time() * 1000)) + str(random.randint(100, 999))
    PENDING_TASKS[task_id] = {'status': 'pending', 'reply': '', 'ops': [], 'error': ''}
    return task_id
def _complete_task(task_id, status, reply='', ops=None, error=''):
    if task_id in PENDING_TASKS:
        PENDING_TASKS[task_id]['status'] = status
        PENDING_TASKS[task_id]['reply'] = reply
        PENDING_TASKS[task_id]['ops'] = ops or []
        PENDING_TASKS[task_id]['error'] = error
def _get_task(task_id):
    return PENDING_TASKS.get(task_id)
def _extract_ops_from_reply(reply):
    """Extract ops from LLM reply text — returns list of op dicts."""
    ops = []
    for line in reply.split('\n'):
        if '[op]' in line:
            op = parse_op(line.strip())
            if op: ops.append(op)
    json_ops = extract_json_ops(reply)
    seen = set()
    for op in json_ops:
        key = op.get('action','') + ':' + (op.get('id','') or op.get('from','') or '')
        seen.add(key)
    for op in list(ops):
        key = op.get('action','') + ':' + (op.get('id','') or op.get('from','') or '')
        if key not in seen:
            json_ops.append(op)
            seen.add(key)
    return json_ops
def _async_chat(task_id, messages, api_url, api_key, model, temperature, max_tokens_cfg, proj_id, session_id, user_text, topo_data):
    """Background thread: call LLM, store reply, mark task done."""
    try:
        if append_session_message(proj_id, session_id, 'user', user_text) is None:
            _complete_task(task_id, 'error', error='project not found: ' + proj_id)
            return
        reply = call_llm_chat(api_url, api_key, model, messages, temperature, max_tokens_cfg)
        ops = _extract_ops_from_reply(reply)
        append_session_message(proj_id, session_id, 'assistant', reply, ops=ops)
        if ops:
            for op in ops:
                try:
                    r = execute_op(op, topo_data, proj_id)
                except Exception as e:
                    r = "异常: " + str(e)
                if r:
                    append_session_message(proj_id, session_id, 'system', "[%s] %s" % (op.get('action','?'), r))
        _complete_task(task_id, 'done', reply=reply, ops=ops)
    except Exception as e:
        _complete_task(task_id, 'error', error=str(e))
def build_system_prompt(proj_id):
    """从外部文件构建 AI System Prompt（分层结构）。"""
    import json as _json

    # 1. 加载拓扑
    topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
    nodes = topo.get('nodes', [])
    edges = topo.get('edges', [])

    # 2. 构建拓扑上下文（人类可读格式）
    topo_lines = []
    topo_lines.append(f"  项目：{proj_id}（共 {len(nodes)} 个设备，{len(edges)} 条连线）")
    for n in nodes:
        avail = n.get('availablePorts', [])
        used = n.get('usedPorts', [])
        topo_lines.append(
            f"  设备：{n.get('label','?')} [ID={n.get('id','')}] 类型={n.get('type','?')} IP={n.get('ip','') or '-'}"
            + (f" 已用端口: {', '.join(used)}" if used else "")
            + (f" 可用端口: {', '.join(avail[:6])}" if avail else "")
        )
    for e in edges:
        topo_lines.append(f"  连线：{e.get('fromLabel','?')} --{e.get('srcPort','?')}→ {e.get('toLabel','?')} [{e.get('tgtPort','?')}]")
    topo_context = '\n'.join(topo_lines) if topo_lines else "  （空拓扑）"

    # 3. 读取 ai_soul.json
    soul_data = {"name": "NetOps AI", "persona": "", "capabilities": [], "safety": {}}
    try:
        with open(AI_SOUL_FILE, 'r', encoding='utf-8') as f:
            soul_data = _json.load(f)
    except Exception:
        pass

    soul_name = soul_data.get("name", "NetOps AI")
    soul_persona = soul_data.get("persona", "")
    capabilities = soul_data.get("capabilities", [])

    # 4. 读取 ai_system_prompt.txt（包含 {topology_context} 和 {skills_content} 占位符）
    rules_content = ""
    try:
        with open(AI_SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
            rules_content = f.read()
    except Exception:
        rules_content = "（规则文件读取失败）"

    # 5. 读取 ai-skills.txt
    skills_content = ""
    try:
        with open(AI_SKILLS_FILE, 'r', encoding='utf-8') as f:
            skills_content = f.read()
    except Exception:
        skills_content = "（技能文件读取失败）"

    # 6. 替换 ai_system_prompt.txt 中的占位符
    rules_content = rules_content.replace("{topology_context}", topo_context)
    rules_content = rules_content.replace("{skills_content}", skills_content)

    # 7. 组装完整 System Prompt
    # 构建语气部分
    tone_do = soul_data.get("tone", {}).get("do", [])
    tone_avoid = soul_data.get("tone", {}).get("avoid", [])
    tone_parts = []
    if tone_do:
        tone_parts.append("  说：" + "、".join(tone_do))
    if tone_avoid:
        tone_parts.append("  避免：" + "、".join(tone_avoid))

    sys_parts = [
        f"你是 {soul_name}，{soul_persona}",
        "",
        "【语气】",
    ]
    if tone_parts:
        sys_parts.extend(tone_parts)
    else:
        sys_parts.append("（无特殊语气要求）")

    sys_parts.extend([
        "",
        "## 当前拓扑状态",
        topo_context,
        "",
        rules_content,
    ])

    return '\n'.join(sys_parts)



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


def _load_goal_system_prompt():
    """Load the goal-mode system prompt.
    
    Prepends agent_system_prompt.txt (role definition) then reads GOAL MODE section
    from ai_system_prompt.txt.
    """
    parts = []
    # 1. Agent role definition
    agent_prompt_file = os.path.join(os.path.dirname(AI_SYSTEM_PROMPT_FILE), 'agent_system_prompt.txt')
    try:
        with open(agent_prompt_file, 'r', encoding='utf-8') as f:
            agent_role = f.read().strip()
            if agent_role:
                parts.append(agent_role + '\n')
    except Exception:
        pass
    # 2. Goal mode section from main prompt
    try:
        with open(AI_SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        if '================================================================================' in content:
            goal_sections = content.split('================================================================================')
            for section in goal_sections[1:]:
                parts.append(section.strip())
    except Exception:
        pass
    return '\n\n'.join(parts)


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
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                text_parts = []
                for block in result.get('content', []):
                    if block.get('type') == 'text':
                        text_parts.append(block.get('text', ''))
                return '\n'.join(text_parts) if text_parts else '(无内容)'
        except TimeoutError:
            return f'⚠️ AI 响应超时（>60秒），请重试。'
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except TimeoutError:
            return f'⚠️ AI 响应超时（>60秒），请重试。'
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
        if path == '/api/topology' and self.command == 'GET':
            project = params.get('projectId', [params.get('project_id', ['default'])])
            project = project[0] if isinstance(project, list) else project
            topo = load_topo(project, project)
            self._json(topo if topo else {'nodes': [], 'edges': []})
            return
        if path == '/api/topology' and self.command == 'POST':
            # AI analysis endpoint: accept topology data, store for analysis
            goal_data = payload.get('goal', '')
            topo_data = payload.get('topology', payload.get('data', {}))
            # Store in analysis cache (simple in-memory)
            import threading
            with threading.Lock():
                _analysis_cache = getattr(server, '_analysis_cache', {})
                _analysis_cache['latest'] = {'goal': goal_data, 'topology': topo_data, 'time': time.time()}
                server._analysis_cache = _analysis_cache
            self._json({'ok': True, 'message': '拓扑已接收，正在分析...'})
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
                # FIX: if proj= already in query string, just serve index.html (no redirect to avoid loop)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, must-revalidate')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(os.path.join(BASE_DIR, 'index.html'), 'rb') as f:
                    self.wfile.write(f.read())
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
        # ── Agent API: GET /api/agent/topology?project_id=xxx ────────
        if path == '/api/agent/topology':
            proj_id = params.get('project_id', ['default'])[0]
            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            self._json({'ok': True, 'project_id': proj_id, 'topology': topo})
            return
        # ── Agent API: GET /api/agent/resource_pool?project_id=xxx ──
        if path == '/api/agent/resource_pool':
            proj_id = params.get('project_id', ['default'])[0]
            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            # 汇总所有资源的占用情况
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])
            device_ids = set(n.get('id') for n in nodes)
            port_map = {}  # device_id -> set of used ports
            for n in nodes:
                port_map[n.get('id')] = set(n.get('usedPorts') or [])
            edge_ids = set()
            for e in edges:
                eid = e.get('id', '')
                if eid:
                    edge_ids.add(eid)
            self._json({'ok': True, 'project_id': proj_id, 'device_ids': list(device_ids), 'port_map': {k: list(v) for k, v in port_map.items()}, 'edge_ids': list(edge_ids), 'edge_count': len(edges)})
            return
        # ── Agent API: GET /api/agent/export?project_id=xxx&format=json|yaml|png ──
        if path == '/api/agent/export':
            proj_id = params.get('project_id', ['default'])[0]
            fmt = params.get('format', ['json'])[0].lower()
            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
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
                    svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><text x="10" y="20">拓扑: {proj_id}</text><text x="10" y="40">节点: {len(topo.get("nodes", []))}</text><text x="10" y="60">连线: {len(topo.get("edges", []))}</text></svg>'
                    png_b64 = base64.b64encode(svg_content.encode('utf-8')).decode('ascii')
                    self._json({'ok': True, 'format': 'png', 'project_id': proj_id, 'image': png_b64, 'note': 'SVG格式，前端负责渲染'})
                except Exception as e:
                    self._json({'ok': False, 'error': f'PNG 生成失败: {str(e)}'})
            else:
                self._json({'ok': False, 'error': f'不支持的格式: {fmt}，支持 json/yaml/png'})
            return
        # ── Agent API: GET /api/agent/snapshots?project_id=xxx ──
        if path == '/api/agent/snapshots':
            proj_id = params.get('project_id', ['default'])[0]
            snaps_file = os.path.join(PROJECTS_DIR, proj_id, 'snapshots.json')
            snaps = []
            if os.path.exists(snaps_file):
                try:
                    with open(snaps_file) as f: snaps = json.load(f)
                except: pass
            brief = []
            for s in snaps:
                brief.append({'id': s.get('id'), 'name': s.get('name'), 'created': s.get('created'), 'nodeCount': len(s.get('topology', {}).get('nodes', [])), 'edgeCount': len(s.get('topology', {}).get('edges', []))})
            self._json({'ok': True, 'snapshots': brief})
            return
        # GET /api/chat/poll/<task_id> — poll for async chat result
        m = re.match(r'^/api/chat/poll/([\w-]+)$', path)
        if m and self.command == 'GET':
            task_id = m.group(1)
            task = _get_task(task_id)
            if not task:
                self._json({'status': 'error', 'error': 'Task not found'}, 404); return
            self._json({'status': task['status'], 'reply': task.get('reply',''), 'ops': task.get('ops',[]), 'error': task.get('error','')})
            return
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<html><body><h1>404 Not Found</h1><p>文件不存在</p><a href="/projects.html">返回项目列表</a></body></html>'.encode('utf-8'))
            return
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
        return

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
            if not isinstance(payload, dict):
                self._json({'error': 'Invalid request body'}, status=400); return
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
            if append_session_message(proj_id, session_id, role, msg_content, ops) is None:
                self._json({'error': 'project not found'}, 404); return
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
                self._json({'reply': '请先在 AI设置 中配置 API Key'}); return

            proj_id = payload.get('projectId', 'default')
            session_id = payload.get('sessionId', 'default')
            user_text = payload.get('text', '')
            if len(user_text) > 10000:
                self._json({'reply': '消息过长'}); return
            topo_info = payload.get('topology', {})
            with_topo = payload.get('withTopo', False)
            topo_mode = payload.get('topoMode', 'detail')

            sys_prompt = build_system_prompt(proj_id)
            settings2 = load_llm_settings()
            custom_sys = settings2.get('system_prompt', '').strip()
            if custom_sys:
                sys_prompt = sys_prompt + '\n\n' + custom_sys

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

            topo_data = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            task_id = _create_task()
            t = _threading.Thread(target=_async_chat, args=(task_id, messages, api_url, api_key, model, temperature, max_tokens_cfg, proj_id, session_id, user_text, topo_data))
            t.daemon = True
            t.start()
            self._json({'status': 'ok', 'task_id': task_id})
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

        # Agent API: POST /api/agent/execute (supports single action + batch actions)
        if path == '/api/agent/execute':
            proj_id = payload.get('project_id', 'default')
            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])

            def find_node(nid):
                for n in nodes:
                    if n.get('id') == nid or n.get('label', '').lower() == str(nid).lower(): return n
                return None
            def find_edge(src, tgt):
                for e in edges:
                    if (e.get('source') == src or e.get('from') == src) and (e.get('target') == tgt or e.get('to') == tgt): return e
                    if (e.get('source') == tgt or e.get('from') == tgt) and (e.get('target') == src or e.get('to') == src): return e
                return None

            # Batch actions support
            actions_list = payload.get('actions', None)
            if actions_list is not None:
                # Batch mode: process array of {action, params}
                results = []
                all_ok = True
                for item in actions_list:
                    if not isinstance(item, dict):
                        results.append({'action': 'unknown', 'ok': False, 'error': 'invalid action item'})
                        all_ok = False
                        continue
                    batch_action = item.get('action', '')
                    params = item.get('params', {})
                    # Merge project_id if not in params
                    if 'project_id' not in params:
                        params['project_id'] = proj_id
                    res = _execute_single_action(batch_action, params, nodes, edges)
                    results.append(res)
                    if not res.get('ok', False):
                        all_ok = False
                topo['nodes'] = nodes
                topo['edges'] = edges
                save_project_file(proj_id, 'topo.json', topo)
                self._json({'ok': all_ok, 'results': results})
                return

            # Single action mode (backward compatible)
            action = payload.get('action', '')
            if not action:
                self._json({'ok': False, 'error': '缺少 action 参数'}); return
            res = _execute_single_action(action, payload, nodes, edges)
            topo['nodes'] = nodes
            topo['edges'] = edges
            save_project_file(proj_id, 'topo.json', topo)
            self._json(res)
            return

        # Agent API: POST /api/agent/chat
        if path == '/api/agent/chat':
            settings = load_llm_settings()
            api_key = settings.get('api_key', '').strip()
            oauth_token = settings.get('oauth_token', '').strip()
            api_url = settings.get('api_url', '').strip()
            model = settings.get('model', '').strip() or settings.get('oauth_model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = float(settings.get('temperature', 0.7))
            max_tokens_cfg = int(settings.get('max_tokens', 8192))
            if oauth_token:
                api_key = oauth_token; api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key: self._json({'ok': False, 'error': '请先配置 API Key'}); return
            proj_id = payload.get('project_id', 'default')
            user_text = payload.get('message', '')
            if not user_text: self._json({'ok': False, 'error': '缺少 message 参数'}); return
            sys_prompt = build_system_prompt(proj_id)
            messages = [{'role': 'system', 'content': sys_prompt}]
            topo_data = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo_data.get('nodes', []); edges = topo_data.get('edges', [])
            brief = [f'当前拓扑（共 {len(nodes)} 个设备，{len(edges)} 条连线）']
            if nodes:
                kn = [n.get('label', '?') for n in nodes[:10]]
                brief.append(f'关键设备：{", ".join(kn)}' + (' 等（更多设备略）' if len(nodes) > 10 else ''))
            messages.append({'role': 'user', 'content': user_text + chr(10) + chr(10) + chr(10).join(brief)})
            try:
                # MiniMax /anthropic 使用 /v1/messages（Anthropic 兼容格式）
                req_data = {'model': model, 'messages': messages, 'max_tokens': max_tokens_cfg, 'temperature': temperature}
                req = urllib.request.Request(
                    api_url + '/v1/messages',
                    data=json.dumps(req_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_key, 'anthropic-version': '2023-06-01'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    rd = json.loads(resp.read().decode('utf-8'))
                    # Anthropic/MiniMax /v1/messages 响应格式
                    text_parts = []
                    for block in rd.get('content', []):
                        if block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    reply = '\n'.join(text_parts) if text_parts else ''
                    ops = []
                    # 方式1: 解析 [op] add_node:key=value 格式
                    for m in re.finditer(r'\[op\]\s*(\w+)(?:[:：](.+))?', reply):
                        act = m.group(1).strip(); args = m.group(2) or ''; op = {'action': act}
                        for pair in args.split(','):
                            pair = pair.strip()
                            if not pair: continue
                            if '=' in pair:
                                k, v = pair.split('=', 1); op[k.strip()] = v.strip()
                        if op not in ops: ops.append(op)
                    # 方式2: 解析 JSON 数组格式（AI 直接输出 JSON）
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

        # ── Agent API: POST /api/agent/snapshot ──────────────────────
        # 创建拓扑快照
        if path == '/api/agent/snapshot' and self.command == 'POST':
            proj_id = payload.get('project_id', 'default')
            name = payload.get('name', time.strftime('%Y-%m-%d %H:%M:%S'))
            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            snap_id = 'snap_' + str(int(time.time() * 1000)) + str(random.randint(100, 999))
            snap = {
                'id': snap_id,
                'name': name,
                'created': time.strftime('%Y-%m-%d %H:%M:%S'),
                'topology': topo
            }
            # Load existing snapshots
            snaps_file = os.path.join(PROJECTS_DIR, proj_id, 'snapshots.json')
            snaps = []
            if os.path.exists(snaps_file):
                try:
                    with open(snaps_file) as f: snaps = json.load(f)
                except: pass
            snaps.append(snap)
            with open(snaps_file, 'w') as f:
                json.dump(snaps, f, ensure_ascii=False, indent=2)
            self._json({'ok': True, 'snapshot': snap})
            return

        # ── Agent API: POST /api/agent/restore/{snapshot_id} ─────────
        # 恢复快照
        m = re.match(r'^/api/agent/restore/([^/]+)$', path)
        if m and self.command == 'POST':
            snap_id = m.group(1)
            proj_id = payload.get('project_id', 'default')
            snaps_file = os.path.join(PROJECTS_DIR, proj_id, 'snapshots.json')
            if not os.path.exists(snaps_file):
                self._json({'ok': False, 'error': '快照文件不存在'}); return
            try:
                with open(snaps_file) as f: snaps = json.load(f)
            except:
                self._json({'ok': False, 'error': '快照文件读取失败'}); return
            target = None
            for s in snaps:
                if s.get('id') == snap_id:
                    target = s; break
            if not target:
                self._json({'ok': False, 'error': f'快照 {snap_id} 不存在'}); return
            topo = target.get('topology', {'nodes': [], 'edges': []})
            save_project_file(proj_id, 'topo.json', topo)
            self._json({'ok': True, 'message': f'已恢复到快照: {target.get("name", snap_id)}', 'topology': topo})
            return

        # ── Agent API: POST /api/agent/goal ───────────────────────────
        # 接收高层目标，返回执行计划（由 LLM 翻译为目标→步骤）
        if path == '/api/agent/goal':
            settings = load_llm_settings()
            api_key = settings.get('api_key', '').strip()
            oauth_token = settings.get('oauth_token', '').strip()
            api_url = settings.get('api_url', '').strip()
            model = settings.get('model', '').strip() or settings.get('oauth_model', '').strip() or 'MiniMax-M2.5-highspeed'
            temperature = float(settings.get('temperature', 0.7))
            max_tokens_cfg = int(settings.get('max_tokens', 8192))
            if oauth_token:
                api_key = oauth_token; api_url = 'https://api.minimaxi.com/anthropic'
            if not api_key: self._json({'ok': False, 'error': '请先配置 API Key'}); return

            proj_id = payload.get('project_id', 'default')
            goal = payload.get('goal', '').strip()
            if not goal: self._json({'ok': False, 'error': '缺少 goal 参数'}); return

            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', []); edges = topo.get('edges', [])

            # 构建拓扑上下文（供 LLM 参考）
            topo_lines = [f'当前拓扑（共 {len(nodes)} 个设备，{len(edges)} 条连线）：']
            for n in nodes:
                avail = n.get('availablePorts', [])
                used = n.get('usedPorts', [])
                topo_lines.append(
                    f'  设备：{n.get("label","?")} [ID={n.get("id","")}] 类型={n.get("type","?")} '
                    f'IP={n.get("ip","") or "-"}'
                    + (f' 已用端口={','.join(used)}' if used else '')
                    + (f' 可用端口={','.join(avail[:6])}' if avail else ' 可用端口=无')
                )
            for e in edges:
                topo_lines.append(
                    f'  连线：{e.get("fromLabel",e.get("source","?"))} --{e.get("srcPort","?")}→ '
                    f'{e.get("toLabel",e.get("target","?"))} [{e.get("tgtPort","?")}]'
                )
            topo_context = '\n'.join(topo_lines) or '  （空拓扑）'

            # 读取 goal 专用 system prompt
            goal_rules = _load_goal_system_prompt()

            prompt = f"""你是 NetOps 执行规划 Agent。收到高层目标后，自动规划具体执行步骤。

【拓扑上下文】
{topo_context}

【你的任务】
用户目标：{goal}

请根据拓扑上下文，分析目标并生成执行计划：
{goal_rules}"""

            messages = [{'role': 'user', 'content': prompt}]
            try:
                req_data = {
                    'model': model,
                    'messages': messages,
                    'max_tokens': max_tokens_cfg,
                    'temperature': temperature
                }
                req = urllib.request.Request(
                    api_url + '/v1/messages',
                    data=json.dumps(req_data).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + api_key,
                        'anthropic-version': '2023-06-01'
                    },
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    rd = json.loads(resp.read().decode('utf-8'))
                    text_parts = []
                    for block in rd.get('content', []):
                        if block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    llm_reply = '\n'.join(text_parts) if text_parts else ''

                # 解析 JSON 执行计划
                import re as re_module
                plan_data = None
                json_blocks = re_module.findall(r'```json\s*([\s\S]*?)\s*```', llm_reply)
                for jb in json_blocks:
                    try:
                        plan_data = json.loads(jb.strip())
                        break
                    except json.JSONDecodeError:
                        pass
                # 也尝试直接匹配 JSON 对象
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
                        'ok': True,
                        'goal': goal,
                        'goal_summary': plan_data.get('goal_summary', goal),
                        'execution_plan': plan_data.get('execution_plan', []),
                        'topology_change': plan_data.get('topology_change', {}),
                        'risk_note': plan_data.get('risk_note'),
                        'llm_raw': llm_reply[:500]  # 保留原始输出供调试
                    })
                else:
                    # LLM 没返回合法 JSON，返回原始回复
                    self._json({
                        'ok': False,
                        'error': '执行计划解析失败',
                        'llm_reply': llm_reply[:1000]
                    })
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # ── Agent API: POST /api/agent/goal/execute ──────────────────
        # 执行已确认的 execution_plan
        if path == '/api/agent/goal/execute':
            proj_id = payload.get('project_id', 'default')
            plan = payload.get('plan', [])  # list of execution steps
            if not plan: self._json({'ok': False, 'error': '缺少 plan 参数'}); return

            topo = load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])

            def _find_node(nid):
                for n in nodes:
                    if n.get('id') == nid or n.get('label', '').lower() == str(nid).lower(): return n
                return None
            def _find_edge(src, tgt):
                for e in edges:
                    if (e.get('source') == src or e.get('from') == src) and \
                       (e.get('target') == tgt or e.get('to') == tgt): return e
                    if (e.get('source') == tgt or e.get('from') == tgt) and \
                       (e.get('target') == src or e.get('to') == src): return e
                return None

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
                            if not nid: raise ValueError('add_node 需要 id 参数')
                            if _find_node(nid): raise ValueError(f'设备 {nid} 已存在')
                            ntype = params.get('type', 'switch')
                            nip = params.get('ip', '')
                            nlabel = params.get('label', nid)
                            # 优先使用显式坐标，否则自动网格分配（避免重叠）
                            if params.get('x') is not None and params.get('y') is not None:
                                nx = int(params.get('x'))
                                ny = int(params.get('y'))
                            else:
                                nx, ny = _next_grid_pos()
                            nodes.append({
                                'id': nid, 'type': ntype, 'label': nlabel,
                                'ip': nip, '_x': nx, '_y': ny,
                                'availablePorts': params.get('availablePorts', []),
                                'usedPorts': params.get('usedPorts', [])
                            })
                            msg = f'添加设备 {nlabel} [{ntype}]'

                        elif action == 'add_edge':
                            src = params.get('from') or params.get('src', '')
                            tgt = params.get('to') or params.get('tgt', '')
                            if not src or not tgt: raise ValueError('add_edge 需要 from 和 to')
                            sn = _find_node(src); tn = _find_node(tgt)
                            if not sn:
                                # Auto-create missing source node
                                if params.get('fromX') is not None and params.get('fromY') is not None:
                                    sx, sy = int(params.get('fromX')), int(params.get('fromY'))
                                else:
                                    sx, sy = _next_grid_pos()
                                nodes.append({'id': src, 'type': params.get('fromType', 'switch'), 'label': params.get('fromLabel', src), 'ip': params.get('fromIp', ''), '_x': sx, '_y': sy, 'availablePorts': [], 'usedPorts': []})
                                sn = _find_node(src)
                                msg += f' [auto-add:{src}]'
                            if not tn:
                                # Auto-create missing target node
                                if params.get('toX') is not None and params.get('toY') is not None:
                                    tx, ty = int(params.get('toX')), int(params.get('toY'))
                                else:
                                    tx, ty = _next_grid_pos()
                                nodes.append({'id': tgt, 'type': params.get('toType', 'switch'), 'label': params.get('toLabel', tgt), 'ip': params.get('toIp', ''), '_x': tx, '_y': ty, 'availablePorts': [], 'usedPorts': []})
                                tn = _find_node(tgt)
                                msg += f' [auto-add:{tgt}]'
                            if _find_edge(src, tgt): raise ValueError(f'{src} 和 {tgt} 之间已有连线')
                            sp = params.get('srcPort', ''); tp = params.get('tgtPort', '')
                            edges.append({
                                'source': sn['id'], 'target': tn['id'],
                                'from': sn['id'], 'to': tn['id'],
                                'fromLabel': sn.get('label', sn['id']),
                                'toLabel': tn.get('label', tn['id']),
                                'srcPort': sp, 'tgtPort': tp,
                                'edgeStyle': 'solid', 'edgeColor': '#374151', 'edgeWidth': 2
                            })
                            msg = f'添加连线 {src} → {tgt}'

                        elif action == 'delete_node':
                            nid = params.get('id')
                            if not nid: raise ValueError('delete_node 需要 id')
                            nn = _find_node(nid)
                            if not nn: raise ValueError(f'设备 {nid} 不存在')
                            nid_r = nn.get('id')
                            edges[:] = [e for e in edges
                                        if e.get('source') != nid_r and e.get('from') != nid_r
                                        and e.get('target') != nid_r and e.get('to') != nid_r]
                            nodes[:] = [n for n in nodes if n.get('id') != nid_r]
                            msg = f'删除设备 {nid} 及相关连线'

                        elif action == 'delete_edge':
                            src = params.get('from') or params.get('src', '')
                            tgt = params.get('to') or params.get('tgt', '')
                            if not src or not tgt: raise ValueError('delete_edge 需要 from 和 to')
                            removed = False
                            for i, e in enumerate(edges):
                                if (e.get('source') == src or e.get('from') == src) and \
                                   (e.get('target') == tgt or e.get('to') == tgt):
                                    edges.pop(i); removed = True; break
                                if (e.get('source') == tgt or e.get('from') == tgt) and \
                                   (e.get('target') == src or e.get('to') == src):
                                    edges.pop(i); removed = True; break
                            if not removed: raise ValueError(f'连线 {src} ↔ {tgt} 不存在')
                            msg = f'删除连线 {src} ↔ {tgt}'

                        elif action == 'modify_node':
                            nid = params.get('id')
                            if not nid: raise ValueError('modify_node 需要 id')
                            nn = _find_node(nid)
                            if not nn: raise ValueError(f'设备 {nid} 不存在')
                            if 'label' in params: nn['label'] = params['label']
                            if 'ip' in params: nn['ip'] = params['ip']
                            if 'type' in params: nn['type'] = params['type']
                            msg = f'修改设备 {nid}'

                        elif action == 'move_node':
                            nid = params.get('id')
                            if not nid: raise ValueError('move_node 需要 id')
                            nn = _find_node(nid)
                            if not nn: raise ValueError(f'设备 {nid} 不存在')
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
                save_project_file(proj_id, 'topo.json', topo)
                self._json({'ok': all_ok, 'results': results, 'topology': topo})

            except Exception as e:
                self._json({'ok': False, 'error': str(e), 'results': results})
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
