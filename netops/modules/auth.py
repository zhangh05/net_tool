# modules/auth.py - Authentication, sessions, project user management
import os, json, hashlib, threading, time, uuid, shutil

# ─── Path globals (set by server.py) ─────────────────────────────────────────
PROJECTS_DIR = None

def _init_paths(projects_dir):
    global PROJECTS_DIR
    PROJECTS_DIR = projects_dir

# ─── Super Admin ─────────────────────────────────────────────────────────────
SUPER_ADMIN = {
    "username": "admin",
    "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
    "role": "super"
}

# ─── Session Store ────────────────────────────────────────────────────────────
_session_store = {}          # token -> session dict
_session_lock = threading.Lock()
SESSION_TTL = 86400 * 7     # 7 days

def _gen_token():
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]

def _hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

def new_session(username, role, project_id=None):
    """Create a new session, return (token, session_dict)."""
    token = _gen_token()
    with _session_lock:
        _session_store[token] = {
            "username": username,
            "role": role,          # 'super' | 'owner' | 'member'
            "project_id": project_id,
            "created_at": time.time(),
            "expire_at": time.time() + SESSION_TTL,
        }
    return token

def get_session(token):
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

def del_session(token):
    with _session_lock:
        _session_store.pop(token, None)

def check_super(token):
    """Check if session token belongs to super admin."""
    s = get_session(token)
    return s is not None and s.get("role") == "super"

def check_project_access(token, project_id):
    """Check if session allows access to the given project.
    Super admin can access any project. Others must match project_id.
    """
    s = get_session(token)
    if not s:
        return False
    if s.get("role") == "super":
        return True
    return s.get("project_id") == project_id

# ─── Project-level user management ───────────────────────────────────────────
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

def migrate_all_projects():
    """Migrate all existing projects on startup."""
    if not os.path.exists(PROJECTS_DIR):
        return
    for name in os.listdir(PROJECTS_DIR):
        proj_dir = os.path.join(PROJECTS_DIR, name)
        if os.path.isdir(proj_dir):
            migrate_project_users(name)
