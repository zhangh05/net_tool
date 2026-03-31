"""
NetTool 认证模块
支持 cookie-based SSO，所有子应用共享同一认证
"""
import hashlib
import secrets
import time
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DIR = os.path.join(BASE_DIR, 'shared')
USERS_FILE = os.path.join(SHARED_DIR, 'users.json')
COOKIE_SECRET = 'netool_sso_secret_v1'  # 后续可改为环境变量
COOKIE_NAME = 'netool_session'
SESSION_TTL = 86400 * 7  # 7天过期

_sessions = {}  # session_id -> {user_id, username, role, expire}


def _hash_pwd(password: str) -> str:
    return hashlib.sha256((password + COOKIE_SECRET).encode()).hexdigest()


def _load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, encoding='utf-8') as f:
            return json.load(f).get('users', [])
    except:
        return []


def _save_users(users):
    os.makedirs(SHARED_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': users}, f, indent=2, ensure_ascii=False)


def verify_login(username: str, password: str) -> dict | None:
    """验证登录，返回用户信息或None"""
    users = _load_users()
    pwd_hash = _hash_pwd(password)
    for u in users:
        if u['username'] == username and u.get('password_hash', _hash_pwd(u.get('password', ''))) == pwd_hash:
            return {'id': u['id'], 'username': u['username'], 'role': u.get('role', 'user')}
    return None


def create_session(user_info: dict) -> str:
    """创建会话，返回 session_id"""
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        'user_id': user_info['id'],
        'username': user_info['username'],
        'role': user_info.get('role', 'user'),
        'expire': time.time() + SESSION_TTL
    }
    return session_id


def get_session(session_id: str) -> dict | None:
    """验证并返回会话信息"""
    if not session_id or session_id not in _sessions:
        return None
    s = _sessions[session_id]
    if time.time() > s['expire']:
        del _sessions[session_id]
        return None
    return s


def delete_session(session_id: str):
    """删除会话（登出）"""
    if session_id in _sessions:
        del _sessions[session_id]


def make_cookie(session_id: str) -> dict:
    """生成 Set-Cookie 头"""
    import http.cookies
    c = http.cookies.SimpleCookie()
    c[COOKIE_NAME] = session_id
    c[COOKIE_NAME]['path'] = '/'
    c[COOKIE_NAME]['max-age'] = SESSION_TTL
    c[COOKIE_NAME]['httponly'] = True
    # c[COOKIE_NAME]['samesite'] = 'Lax'
    return c[COOKIE_NAME].OutputString()


def parse_session_from_env(environ: dict) -> dict | None:
    """从 WSGI environ 解析 session"""
    cookie_str = environ.get('HTTP_COOKIE', '')
    if not cookie_str:
        return None
    for part in cookie_str.split(';'):
        k, _, v = part.strip().partition('=')
        if k == COOKIE_NAME:
            return get_session(v)
    return None


# ── 用户管理 API ────────────────────────────────────────────────────────────

def list_users() -> list:
    users = _load_users()
    return [{'id': u['id'], 'username': u['username'], 'role': u.get('role', 'user'),
             'created_at': u.get('created_at', '')} for u in users]


def get_user(user_id: str) -> dict | None:
    users = _load_users()
    for u in users:
        if u['id'] == user_id:
            return {'id': u['id'], 'username': u['username'], 'role': u.get('role', 'user'),
                    'created_at': u.get('created_at', '')}
    return None


def create_user(username: str, password: str, role: str = 'user') -> dict:
    users = _load_users()
    new_id = secrets.token_urlsafe(8)
    import datetime
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    users.append({
        'id': new_id,
        'username': username,
        'password_hash': _hash_pwd(password),
        'role': role,
        'created_at': now
    })
    _save_users(users)
    return {'id': new_id, 'username': username, 'role': role, 'created_at': now}


def delete_user(user_id: str) -> bool:
    users = _load_users()
    for i, u in enumerate(users):
        if u['id'] == user_id:
            if u['username'] == 'root':
                return False  # 禁止删除 root
            users.pop(i)
            _save_users(users)
            return True
    return False


def update_user(user_id: str, password: str = None, role: str = None) -> bool:
    users = _load_users()
    for u in users:
        if u['id'] == user_id:
            if password:
                u['password_hash'] = _hash_pwd(password)
            if role and u['username'] != 'root':  # root 不能改角色
                u['role'] = role
            _save_users(users)
            return True
    return False
