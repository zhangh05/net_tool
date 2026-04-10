#!/usr/bin/env python3
import os, json, datetime, urllib.request, urllib.parse, time, re, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# WebSocket server for real-time progress
try:
    from websocket_server import broadcast_token, broadcast_stage, broadcast_done, broadcast_layer_stage, broadcast_plan, start_server_thread
    _ws_enabled = True
    print("[WS] WebSocket module loaded")
except ImportError:
    _ws_enabled = False
    print("[WS] WebSocket module not available")

# Task queue for multi-agent orchestration
try:
    from task_queue import create_task, get_task, update_task, list_tasks
    _task_queue_enabled = True
except ImportError:
    _task_queue_enabled = False
    def create_task(*a, **k): return None
    def get_task(*a, **k): return None
    def update_task(*a, **k): pass
    def list_tasks(*a, **k): return []

# Records directory for sessions and operations
RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "records")
SESSIONS_DIR = os.path.join(RECORDS_DIR, "sessions")
OPS_DIR = os.path.join(RECORDS_DIR, "ops")
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(OPS_DIR, exist_ok=True)



def _safe_filename(name):
    return re.sub(r'[^\w\-\.]', '_', str(name))

def save_session_message(project_id, session_id, role, content):
    """Save a message to session file"""
    try:
        session_file = os.path.join(SESSIONS_DIR, _safe_filename(project_id) + ".json")
        if os.path.exists(session_file):
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
        else:
            session_data = {"project_id": project_id, "sessions": {}}
        
        if session_id not in session_data["sessions"]:
            session_data["sessions"][session_id] = {"id": session_id, "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "messages": []}
        
        session_data["sessions"][session_id]["messages"].append({"role": role, "content": content, "time": datetime.datetime.now().strftime("%H:%M:%S")})
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[save_session] Error: " + str(e))


def load_session_messages(project_id, session_id="AI"):
    """Load messages from local session file."""
    try:
        session_file = os.path.join(SESSIONS_DIR, _safe_filename(project_id) + ".json")
        if not os.path.exists(session_file):
            return []
        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        sessions = session_data.get("sessions", {})
        sess = sessions.get(session_id, {})
        return sess.get("messages", [])
    except Exception as e:
        print("[load_session] Error: " + str(e))
        return []


def clear_session_messages(project_id, session_id="AI"):
    """Clear messages for a session."""
    try:
        session_file = os.path.join(SESSIONS_DIR, _safe_filename(project_id) + ".json")
        if not os.path.exists(session_file):
            return True
        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        if session_id in session_data.get("sessions", {}):
            session_data["sessions"][session_id]["messages"] = []
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("[clear_session] Error: " + str(e))
        return False


def save_operation(project_id, action, target, result, details=None):
    """Save an operation to ops file"""
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        ops_file = os.path.join(OPS_DIR, _safe_filename(project_id) + "_" + today + ".json")
        if os.path.exists(ops_file):
            with open(ops_file, 'r', encoding='utf-8') as f:
                ops_data = json.load(f)
        else:
            ops_data = {"project_id": project_id, "date": today, "operations": []}
        
        ops_data["operations"].append({"time": datetime.datetime.now().strftime("%H:%M:%S"), "action": action, "target": target, "result": result, "details": details or {}})
        
        with open(ops_file, 'w', encoding='utf-8') as f:
            json.dump(ops_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[save_op] Error: " + str(e))

PORT = 8999
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_FILE = os.path.join(BASE_DIR, "AI_sys_prompt", "agents.json")

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def load_agents():
    if os.path.exists(AGENTS_FILE):
        try:
            with open(AGENTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def np_get(path):
    url = "http://127.0.0.1:9000" + path
    try:
        req = urllib.request.Request(url, method="GET")
        with _NO_PROXY.open(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[np_get ERROR] GET {path}: {e}")
        return None

def np_post(path, payload, timeout=30):
    url = "http://127.0.0.1:9000" + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _NO_PROXY.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[np_post ERROR] POST {path}: {e}")
        return None

def np_put(path, payload=None):
    url = "http://127.0.0.1:9000" + path
    data = json.dumps(payload or {}).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with _NO_PROXY.open(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[np_put ERROR] PUT {path}: {e}")
        return None

def np_delete(path, payload=None):
    url = "http://127.0.0.1:9000" + path
    data = json.dumps(payload or {}).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="DELETE")
    try:
        with _NO_PROXY.open(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[np_delete ERROR] DELETE {path}: {e}")
        return None

def load_llm_settings():
    p = os.path.join(BASE_DIR, "llm_settings.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"api_url": "", "api_key": "", "model": "MiniMax-M2.5-highspeed", "temperature": 0.7, "max_tokens": 8192}

def save_llm_settings(data):
    p = os.path.join(BASE_DIR, "llm_settings.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_ai_soul():
    p = os.path.join(BASE_DIR, "AI_sys_prompt", "ai_soul.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}

def normalize_netops_topo(raw):
    """将 NetOps 拓扑格式转换为前端 SVG 渲染器期望的格式。
    NetOps:  nodes=[{data:{id,type,label,ip,position:{x,y}}}], edges=[{data:{source,target,srcPort,tgtPort}}]
    Frontend: nodes=[{id,type,label,ip,x,y,availablePorts[],usedPorts[]}], edges=[{from,to,fromLabel,toLabel,srcPort,tgtPort}]
    """
    if not isinstance(raw, dict):
        return {"nodes": [], "edges": []}
    topo = raw.get("topology", raw)
    nodes_out = []
    for n in topo.get("nodes", []):
        d = n.get("data", n)
        pos = n.get("position", {})
        nodes_out.append({
            "id": d.get("id", ""),
            "label": d.get("label", d.get("id", "")),
            "type": d.get("type", "default"),
            "ip": d.get("ip", ""),
            "x": pos.get("x", 200),
            "y": pos.get("y", 200),
            "availablePorts": d.get("availablePorts", []),
            "usedPorts": d.get("usedPorts", []),
        })
    edges_out = []
    for e in topo.get("edges", []):
        d = e.get("data", e)
        edges_out.append({
            "from": d.get("source", ""),
            "to": d.get("target", ""),
            "fromLabel": d.get("source", ""),
            "toLabel": d.get("target", ""),
            "srcPort": d.get("srcPort", ""),
            "tgtPort": d.get("tgtPort", ""),
        })
    return {"nodes": nodes_out, "edges": edges_out}

def _format_agents_for_prompt():
    """Build a readable description of all agents and their actions."""
    agents = load_agents()
    lines = []
    for aid, a in agents.items():
        lines.append(f"【Agent: {a['name']} ({aid})】")
        lines.append(f"  执行方式：{a.get('description', '通过 AI 协调执行')}")
        lines.append("  可执行操作：")
        for aname, action in a.get("actions", {}).items():
            params_str = ", ".join(action.get("params", [])) or "无"
            confirm_str = "（需用户确认）" if action.get("confirm") else "（自动执行）"
            desc = action.get("description", "")
            lines.append(f"    - {action['label']} ({aname}): {desc} {confirm_str}")
            lines.append(f"      参数: {params_str}")
        lines.append("")
    return "\n".join(lines)

# ── 流式 API 调用 ────────────────────────────────────────
def call_minimax_streaming(messages, settings, on_token_callback):
    """
    流式调用 MiniMax API，边收边回调
    messages: [{role, content}, ...]
    settings: {api_key, api_url, model, max_tokens}
    on_token_callback: 收到token时的回调函数(token_str)
    """
    import http.client, ssl
    from urllib.parse import urlparse
    
    ak = settings.get("api_key", "").strip()
    api_url = settings.get("api_url", "https://api.minimaxi.com/anthropic").rstrip("/")
    model = settings.get("model", "MiniMax-M2.7")
    max_tokens = int(settings.get("max_tokens", 8192))
    
    if "/anthropic" not in api_url:
        # 非流式调用
        return None
    
    url = api_url + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + ak,
        "anthropic-version": "2023-06-01"
    }
    
    anthropic_msgs = []
    for m in messages:
        anthropic_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    
    rd = {
        "model": model,
        "messages": anthropic_msgs,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": True
    }
    
    body = json.dumps(rd).encode("utf-8")
    parsed = urlparse(url)
    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.netloc, context=context, timeout=120)
    
    try:
        conn.request("POST", parsed.path, body=body, headers=headers)
        resp = conn.getresponse()
        
        if resp.status != 200:
            return None
        
        full_text = ""
        while True:
            line = resp.readline().decode("utf-8")
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                continue
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        full_text += text
                        if on_token_callback:
                            on_token_callback(text)
                except:
                    pass
        return full_text
    except:
        return None
    finally:
        conn.close()



def build_manage_system_prompt():
    """构建薄协调层 system prompt — 只做意图分类和路由"""
    soul = load_ai_soul()
    name = soul.get("name", "阿维")
    role = soul.get("role", "统筹平台 AI 助手")

    return f"""你是 {name}，{role}，一个轻量的 AI 协调层。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【核心职责：薄协调，只路由】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你不执行任何实际操作，只负责：
  1. 理解用户需求
  2. 判断应该由哪个 Agent 处理
  3. 把任务转交出去，汇总结果返回给用户

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【可用 Agent】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

当前只有一个 Agent 可用，未来会扩展：

## NetOps（netops）
职责：网络拓扑的构建、修改、查询
能力：添加/删除/修改设备和连线，拓扑规划，设备配置建议
判断依据：用户提到"画拓扑"、"设计网络"、"添加设备"、"改拓扑"、"三层网络"、"交换机/路由器/防火墙"等

## NetKnowledge（netknowledge）（未来）
职责：网络知识库
能力：协议原理、厂家差异、故障排查、设计合理性审查
判断依据：用户问"是什么"、"有什么区别"、"怎么配"、"为什么"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输出格式】非常重要，请严格遵守
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你的回复必须由两部分组成：

第一部分：[ROUTE_TO=agent_id]  或  [ROUTE_TO=none]
  - 如果需要 NetOps 处理：[ROUTE_TO=netops]
  - 如果需要 NetKnowledge 处理：[ROUTE_TO=netknowledge]
  - 如果只是闲聊或无法归类：[ROUTE_TO=none]

第二部分：对这个路由决定的简短解释（1-2句话），然后是你的回复。

【正确示例】
[ROUTE_TO=netops] 需要在拓扑中添加相关设备。
好的，我来帮您设计一个三层网络架构。我会把需求转交给 NetOps 来执行。

【正确示例 - 闲聊】
[ROUTE_TO=none] 这是一个一般性闲聊。
你好！有什么网络相关的需求我可以帮您协调处理吗？

【错误示例 - 写了 action:】
[ROUTE_TO=netops] （不要这样写）
action: add_node
id: R1
type: router
...
← 你不需要写 action，只管路由！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【重要规则】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 你只输出路由决定 + 自然语言回复，不要生成任何 action: / 操作指令
2. 操作指令是 Agent 的职责，不是你的
3. 对用户保持简洁友好的语言，不要暴露内部架构细节
4. 如果不确定用户需求属于哪个 Agent，宁可路由到 netops（更通用）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【对话历史】已在 messages 中传入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

def build_summary_prompt(results, user_question):
    """Build the summary generation prompt."""
    # 格式化执行结果
    lines = []
    for r in results:
        action = r.get("step", "?")
        label = r.get("label", r.get("action", "?"))
        ok = r.get("ok", False)
        result_data = r.get("result", {})
        status = "✅ 成功" if ok else "❌ 失败"
        lines.append(f"步骤 {action} [{label}]：{status}")
        if result_data:
            # 提取有用信息
            if result_data.get("topology"):
                t = result_data["topology"]
                nc = len(t.get("nodes", []))
                ec = len(t.get("edges", []))
                lines.append(f"  → 返回拓扑：{nc}台设备，{ec}条连线")
            elif result_data.get("action"):
                lines.append(f"  → 操作：{result_data.get('action')}，设备：{result_data.get('node', result_data.get('id', '-'))}")
            elif isinstance(result_data, dict):
                # 提取顶层有用字段
                useful = {k: v for k, v in result_data.items() if k not in ("ok", "message") and v}
                for k, v in useful.items():
                    if isinstance(v, str) and len(v) < 100:
                        lines.append(f"  → {k}: {v}")
    results_str = "\n".join(lines) if lines else str(results)

    prompt = REPORTER_PROMPT.format(results=results_str)
    if user_question:
        prompt = f"用户的问题是：{user_question}\n\n" + prompt
    return prompt

def generate_summary(results, user_question, settings):
    """Generate a structured summary from execution results via MiniMax."""
    ak = settings.get("api_key", "").strip()
    au = settings.get("api_url", "https://api.minimaxi.com/anthropic").rstrip("/")
    model = settings.get("model", "MiniMax-M2.5-highspeed")
    if not ak:
        return None
    try:
        prompt_text = build_summary_prompt(results, user_question)
        url = au + "/v1/messages"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + ak, "anthropic-version": "2023-06-01"}
        rd = {"model": model, "messages": [{"role": "user", "content": prompt_text}], "max_tokens": 600, "temperature": 0.3}
        req = urllib.request.Request(url, data=json.dumps(rd).encode("utf-8"), headers=headers, method="POST")
        with _NO_PROXY.open(req, timeout=20) as resp:
            rd2 = json.loads(resp.read().decode("utf-8"))
            text_parts = []
            for block in rd2.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            summary = "\n".join(text_parts).strip()
            return summary if summary else None
    except:
        return None


class H(BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def read_body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n == 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self):
        up = urllib.parse.unquote(self.path)
        pp = urllib.parse.urlparse(up).path
        params = urllib.parse.parse_qs(urllib.parse.urlparse(up).query)

        if pp == "/" or pp == "/index.html":
            fp = os.path.join(BASE_DIR, "index.html")
            if os.path.exists(fp):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
            return

        ext_map = {".css": "text/css", ".js": "application/javascript", ".png": "image/png"}
        ext = os.path.splitext(pp)[1].lower()
        if ext in ext_map:
            # Support /css/ and /js/ paths (new modular structure)
            if pp.startswith("/css/"):
                fp = os.path.join(BASE_DIR, "css", os.path.basename(pp))
            elif pp.startswith("/js/"):
                fp = os.path.join(BASE_DIR, "js", os.path.basename(pp))
            elif pp.startswith("/static/"):
                fp = os.path.join(BASE_DIR, "static", os.path.basename(pp))
            else:
                fp = os.path.join(BASE_DIR, "static", os.path.basename(pp))
            if os.path.exists(fp):
                self.send_response(200)
                self.send_header("Content-Type", ext_map[ext])
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
            return

        if pp == "/api/agents":
            agents = load_agents()
            # Bug 3 fix: 只在 NetOps 时查一次在线状态
            netops_online = bool(np_get("/api/projects/"))
            ags = []
            for aid, a in agents.items():
                online = netops_online if aid == "netops" else False
                ags.append({
                    "id": aid,
                    "name": a.get("name", aid),
                    "url": a.get("url", ""),
                    "online": online,
                    "actions": a.get("actions", {})
                })
            self.send_json({"agents": ags})
            return

        if pp == "/api/settings":
            s = load_llm_settings()
            self.send_json({"api_url": s.get("api_url", ""), "api_key": s.get("api_key", ""), "model": s.get("model", ""), "temperature": s.get("temperature", 0.7)})
            return

        if pp == "/api/netops/projects":
            r = np_get("/api/projects/")
            if isinstance(r, list):
                r = [p for p in r if p.get("created", "")]
            self.send_json(r if r else [])
            return

        if pp == "/api/manage/projects":
            # 从 NetOps 获取项目列表
            projects = np_get("/api/projects/")
            if projects and isinstance(projects, list):
                self.send_json({"projects": projects})
            else:
                self.send_json({"projects": []})
            return

        if pp == "/api/manage/topology":
            # 获取 NetOps 拓扑快照
            proj_id = params.get("project_id", ["default"])[0]
            topo_data = np_get("/api/agent/topology?project_id=" + urllib.parse.quote(str(proj_id)))
            if topo_data and topo_data.get("ok"):
                self.send_json({
                    "project": proj_id,
                    "nodeCount": len(topo_data.get("topology", {}).get("nodes", [])),
                    "edgeCount": len(topo_data.get("topology", {}).get("edges", [])),
                    "topology": topo_data.get("topology")
                })
            else:
                self.send_json({"project": proj_id, "nodeCount": 0, "edgeCount": 0, "topology": None})
            return

        if pp == "/api/manage/history":
            proj_id = params.get("project_id", ["default"])[0]
            # 优先从本地读取
            messages = load_session_messages(proj_id, "AI")
            self.send_json({"messages": messages[-50:]})  # 最近 50 条
            return

        # GET /api/manage/sessions?project_id=xxx - list sessions
        if pp == "/api/manage/sessions":
            proj_id = params.get("project_id", ["default"])[0]
            session_file = os.path.join(SESSIONS_DIR, _safe_filename(proj_id) + ".json")
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.send_json(data)
            else:
                self.send_json({"project_id": proj_id, "sessions": {}})
            return

        # GET /api/manage/ops?project_id=xxx&date=xxx - list operations
        if pp == "/api/manage/ops":
            proj_id = params.get("project_id", ["default"])[0]
            date = params.get("date", [datetime.date.today().strftime("%Y-%m-%d")])[0]
            ops_file = os.path.join(OPS_DIR, _safe_filename(proj_id) + "_" + date + ".json")
            if os.path.exists(ops_file):
                with open(ops_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.send_json(data)
            else:
                self.send_json({"project_id": proj_id, "date": date, "operations": []})
            return

        # GET /api/manage/ops/dates?project_id=xxx - list operation dates
        if pp == "/api/manage/ops/dates":
            proj_id = params.get("project_id", ["default"])[0]
            prefix = _safe_filename(proj_id) + "_"
            dates = []
            if os.path.exists(OPS_DIR):
                for fname in os.listdir(OPS_DIR):
                    if fname.startswith(prefix) and fname.endswith(".json"):
                        dates.append(fname[len(prefix):-5])
            self.send_json({"dates": sorted(dates, reverse=True)})
            return

        # GET /api/manage/snapshots?project_id=xxx - list snapshots
        if pp == "/api/manage/snapshots":
            proj_id = params.get("project_id", ["default"])[0]
            res = np_get("/api/agent/snapshots?project_id=" + urllib.parse.quote(proj_id))
            self.send_json(res if res else {"snapshots": []})
            return

        # GET /api/manage/export?project_id=xxx&format=json|yaml|png
        if pp == "/api/manage/export":
            proj_id = params.get("project_id", ["default"])[0]
            fmt = params.get("format", ["json"])[0]
            res = np_get("/api/agent/export?project_id=" + urllib.parse.quote(proj_id) + "&format=" + fmt)
            self.send_json(res if res else {"ok": False, "error": "导出失败"})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        up = urllib.parse.unquote(self.path)
        pp = urllib.parse.urlparse(up).path
        payload = self.read_body()

        if pp == "/api/settings":
            save_llm_settings(payload)
            self.send_json({"status": "ok"})
            return

        if pp == "/api/settings/test":
            ak = payload.get("api_key", "").strip()
            au = payload.get("api_url", "").strip() or "https://api.minimaxi.com/anthropic"
            model = payload.get("model", "").strip() or "MiniMax-M2.5-highspeed"
            if not ak:
                self.send_json({"ok": False, "error": "no api key"})
                return
            try:
                base = au.rstrip("/")
                if "/anthropic" in base:
                    url = base + "/v1/messages"
                    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + ak, "anthropic-version": "2023-06-01"}
                    rd = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
                else:
                    url = base + "/v1/text/chatcompletion_v2"
                    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + ak}
                    rd = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
                req = urllib.request.Request(url, data=json.dumps(rd).encode("utf-8"), headers=headers, method="POST")
                with _NO_PROXY.open(req, timeout=120) as resp:
                    json.loads(resp.read().decode())
                self.send_json({"ok": True, "message": "ok"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        if pp == "/api/agent/execute":
            agent_id = payload.get("agent", "")
            action = payload.get("action", "")
            project_id = payload.get("project_id", "default")
            params = payload.get("params", {})
            agents_data = load_agents()
            if agent_id not in agents_data:
                self.send_json({"ok": False, "error": f"unknown agent: {agent_id}"})
                return
            agent_cfg = agents_data[agent_id]
            if action not in agent_cfg.get("actions", {}):
                self.send_json({"ok": False, "error": f"unknown action: {action}"})
                return
            action_cfg = agent_cfg["actions"][action]
            method = action_cfg["method"]
            endpoint = action_cfg["endpoint"]

            try:
                if method == "GET":
                    # get_topology: 直接调用 NetOps HTTP API
                    endpoint = endpoint.replace("{project_id}", urllib.parse.quote(project_id))
                    result = np_get(endpoint)
                    if isinstance(result, dict):
                        result = {"ok": True, "topology": normalize_netops_topo(result)}
                    self.send_json({"ok": True, "result": result})

                elif method == "POST":
                    # add_node / add_edge / delete_node 等: 调用 NetOps /api/agent/execute
                    post_payload = dict(params)
                    post_payload["action"] = action
                    post_payload["project_id"] = project_id
                    net_result = np_post(endpoint, post_payload)
                    # 归一化返回的拓扑（如果包含拓扑数据）
                    if isinstance(net_result, dict) and net_result.get("topology"):
                        net_result = dict(net_result)
                        net_result["topology"] = normalize_netops_topo(net_result)
                    self.send_json({"ok": True, "result": net_result})

                else:
                    self.send_json({"ok": False, "error": f"unsupported method: {method}"})

            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return


        # POST /api/manage/snapshot - create snapshot
        if pp == "/api/manage/snapshot":
            proj_id = payload.get("project_id", "default")
            name = payload.get("name", "快照 " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            res = np_post("/api/agent/snapshot", {"project_id": proj_id, "name": name})
            self.send_json(res if res else {"ok": False, "error": "NetOps 快照失败"})
            return

        # POST /api/manage/restore/{snap_id} - restore snapshot
        if pp.startswith("/api/manage/restore/"):
            snap_id = pp.replace("/api/manage/restore/", "")
            proj_id = payload.get("project_id", "default")
            res = np_post("/api/agent/restore/" + snap_id, {"project_id": proj_id})
            self.send_json(res if res else {"ok": False, "error": "NetOps 恢复失败"})
            return

        if pp == "/api/manage/chat":
            user_text = payload.get("message", "")
            project_id = payload.get("project_id", "default")
            if not user_text:
                self.send_json({"ok": False, "error": "empty"})
                return

            settings = load_llm_settings()
            ak = settings.get("api_key", "").strip()
            if not ak:
                self.send_json({"ok": False, "error": "no api key"})
                return

            # 写用户消息到本地（不再写 NetOps）
            save_session_message(project_id, "AI", "user", user_text)

            # WebSocket: 协调层理解 + 规划
            if _ws_enabled:
                broadcast_layer_stage("coord", "understanding", 10, "🔍 协调层正在理解需求...")
                broadcast_layer_stage("coord", "planning", 30, "🤔 协调层正在规划...")

            # 读取完整会话历史（从本地）
            session_msgs = load_session_messages(project_id, "AI")

            # 构建 system prompt（协调层只做路由，不需要拓扑详情）
            system = build_manage_system_prompt()

            # 构建完整消息上下文（最近 50 条历史）
            messages = [{"role": "system", "content": system}]
            for msg in session_msgs[-50:]:
                role = msg.get("role", "user")
                if role == "bot":
                    role = "assistant"
                messages.append({"role": role, "content": msg.get("content", "")})
            messages.append({"role": "user", "content": user_text})

            try:
                api_url = settings.get("api_url", "https://api.minimaxi.com/anthropic").rstrip("/")
                model_name = settings.get("model", "MiniMax-M2.5-highspeed")
                temperature = float(settings.get("temperature", 0.7))
                max_tokens = int(settings.get("max_tokens", 8192))

                if "/anthropic" in api_url:
                    url = api_url + "/v1/messages"
                    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + ak, "anthropic-version": "2023-06-01"}
                    anthropic_msgs = []
                    for m in messages:
                        # Bug 2 fix: Anthropic API 原生支持 system 消息，不要转成 user
                        anthropic_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
                    rd = {"model": model_name, "messages": anthropic_msgs, "max_tokens": max_tokens, "temperature": temperature}
                else:
                    url = api_url + "/v1/text/chatcompletion_v2"
                    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + ak}
                    rd = {"model": model_name, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}

                # 流式调用：边收token边推送
                reply = ""
                def stream_token(token):
                    nonlocal reply
                    reply += token
                    if _ws_enabled:
                        broadcast_token(token)
                
                stream_result = call_minimax_streaming(messages, settings, stream_token)
                
                # 流式完成后发送完成信号
                if _ws_enabled:
                    broadcast_done()
                
                if not reply:
                    reply = "(无内容)"


                # Save AI reply to local session
                save_session_message(project_id, "AI", "bot", reply)

                # ── 薄协调层：解析 [ROUTE_TO=xxx] 并转发 ──
                import re as _re
                route_match = _re.search(r'\[ROUTE_TO=(\w+)\]', reply)
                route_target = route_match.group(1) if route_match else "none"

                # 去掉 [ROUTE_TO=xxx] 行，保留后面的自然语言回复
                reply_text = _re.sub(r'\[ROUTE_TO=\w+\][^\n]*\n?', '', reply).strip()

                if route_target == "netops":
                    # 转发到 NetOps（传递完整对话上下文）
                    if _ws_enabled:
                        broadcast_layer_stage("coord", "dispatching", 40, "📡 转发请求到 NetOps...")
                    net_res = np_post("/api/agent/chat", {
                        "message": user_text,
                        "history": session_msgs[-20:] if session_msgs else [],
                        "project_id": project_id
                    }, timeout=60)
                    if net_res and net_res.get("ok"):
                        agent_reply = net_res.get("reply", "(NetOps 无内容返回)")
                        final_reply = reply_text + "\n\n" + agent_reply if reply_text else agent_reply
                    else:
                        final_reply = reply_text + "\n\n⚠️ NetOps 执行失败：" + (net_res.get("error", "未知错误") if net_res else "无响应")
                    if _ws_enabled:
                        broadcast_layer_stage("coord", "reporting", 100, "✅ 处理完成")
                        broadcast_done()
                    save_session_message(project_id, "AI", "bot", final_reply)
                    self.send_json({"ok": True, "reply": final_reply, "steps": None})

                elif route_target == "netknowledge":
                    # NetKnowledge 未来实现
                    if _ws_enabled:
                        broadcast_layer_stage("coord", "reporting", 100, "✅ 处理完成")
                        broadcast_done()
                    not_impl = "NetKnowledge（知识库 Agent）尚未部署，当前仅支持 NetOps 网络拓扑操作。"
                    final_reply = reply_text + "\n\n" + not_impl if reply_text else not_impl
                    save_session_message(project_id, "AI", "bot", final_reply)
                    self.send_json({"ok": True, "reply": final_reply, "steps": None})

                else:
                    # 闲聊或无法归类，直接返回 LLM 回复
                    if _ws_enabled:
                        broadcast_layer_stage("coord", "reporting", 100, "✅ 处理完成")
                        broadcast_done()
                    save_session_message(project_id, "AI", "bot", reply_text)
                    self.send_json({"ok": True, "reply": reply_text, "steps": None})

            except Exception as e:
                # 发生错误
                if _ws_enabled:
                    broadcast_layer_stage("coord", "reporting", 100, "❌ 处理失败: " + str(e))
                    broadcast_done()
                self.send_json({"ok": False, "error": str(e)})
            return

        # POST /api/manage/clear_history - 清空聊天历史
        if pp == "/api/manage/clear_history":
            proj_id = payload.get("project_id", "default")
            ok = clear_session_messages(proj_id, "AI")
            self.send_json({"ok": ok})
            return

        if pp == "/api/manage/summary":
            results = payload.get("results", [])
            project_id = payload.get("project_id", "default")
            settings = load_llm_settings()
            summary = generate_summary(results, "", settings)
            self.send_json({"summary": summary or "（无汇报内容）"})
            return

        # ── Goal Execute: POST /api/manage/goal/execute ──────────────────────
        # 用户确认后，执行 NetOps 返回的执行计划，然后由 MiniMax 分析结果
        if pp == "/api/manage/goal/execute":
            project_id = payload.get("project_id", "default")
            plan = payload.get("plan", [])
            if not plan:
                self.send_json({"ok": False, "error": "缺少 plan"})
                return

            # 创建任务追踪
            task_id = None
            if _task_queue_enabled:
                task_id = create_task(project_id, "goal_execute", plan)
                update_task(task_id, status="running")

            # WebSocket: 实施层正在执行
            if _ws_enabled:
                broadcast_layer_stage("netops", "executing", 70, "⚙️ NetOps 正在执行操作...")

            # 带重试的执行（最多2次）
            res = None
            for attempt in range(3):
                res = np_post("/api/agent/goal/execute", {
                    "project_id": project_id,
                    "plan": plan
                }, timeout=45)
                if res and res.get("ok"):
                    break
                if _task_queue_enabled and task_id:
                    update_task(task_id, retry_count=attempt+1)

            if not res:
                if _task_queue_enabled and task_id:
                    update_task(task_id, status="failed", error="NetOps 请求失败")
                self.send_json({"ok": False, "error": "NetOps 执行请求失败"})
                return
            if not res.get("ok"):
                if _task_queue_enabled and task_id:
                    update_task(task_id, status="failed", error=res.get("error", "执行失败"))
                self.send_json({"ok": False, "error": res.get("error", "执行失败"), "results": res.get("results", [])})
                return

            results = res.get("results", [])
            topo_after = res.get("topology", {})

            if _ws_enabled:
                broadcast_layer_stage("coord", "analyzing", 80, "🧠 协调层正在分析执行结果...")

            # ── MiniMax 分析执行结果 ──
            topo_nodes = topo_after.get("nodes", [])
            topo_edges = topo_after.get("edges", [])
            result_lines = [f"{'✅' if r.get('ok') else '❌'} {r.get('message', '')}" for r in results]
            result_summary = "\n".join(result_lines) if result_lines else "无"
            topology_desc = f"共 {len(topo_nodes)} 个设备，{len(topo_edges)} 条连线"
            device_list = "、".join([n.get("label", n.get("id", "?")) for n in topo_nodes[:10]])
            if len(topo_nodes) > 10:
                device_list += f"（等共{len(topo_nodes)}个）"

            analysis_system = f"你是一个专业的网络运维协调助手，刚刚帮助用户完成了一次网络拓扑操作。\n\n【执行结果】\n{result_summary}\n\n【操作后拓扑】\n{topology_desc}\n设备列表：{device_list}\n\n请用简洁、友好的语言汇报给用户，说明操作是否成功、具体做了什么、当前拓扑状态。不要暴露内部技术细节。"

            ai_reply = None
            try:
                settings = load_llm_settings()
                ak = settings.get("api_key", "").strip()
                api_url = settings.get("api_url", "").strip() or "https://api.minimaxi.com/anthropic"
                model = settings.get("model", "").strip() or "MiniMax-M2.5-highspeed"
                if settings.get("oauth_token"):
                    ak = settings.get("oauth_token")
                    api_url = "https://api.minimaxi.com/anthropic"

                req_data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": analysis_system},
                        {"role": "user", "content": "请分析执行结果并汇报给用户"}
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.5
                }
                req = urllib.request.Request(
                    api_url + "/v1/messages",
                    data=json.dumps(req_data).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + ak, "anthropic-version": "2023-06-01"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    rd = json.loads(resp.read().decode("utf-8"))
                    text_parts = [b.get("text", "") for b in rd.get("content", []) if b.get("type") == "text"]
                    ai_reply = "\n".join(text_parts).strip()
            except Exception as e:
                print(f"[MiniMax analysis error: {e}]")

            if not ai_reply:
                ai_reply = f"操作已完成。\n\n{result_summary}\n\n当前拓扑：{topology_desc}"

            # 写结果到 NetOps 会话
            save_session_message(project_id, "AI", "bot", ai_reply)

            if _task_queue_enabled and task_id:
                update_task(task_id, status="completed", result=ai_reply)

            # WebSocket: 协调层汇报完成
            if _ws_enabled:
                broadcast_layer_stage("coord", "reporting", 100, "✅ " + ai_reply[:50])
                broadcast_done()

            self.send_json({
                "ok": True,
                "reply": ai_reply,
                "results": results,
                "topology": topo_after,
                "task_id": task_id
            })
            return

        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        self.send_response(404)
        self.end_headers()


class T(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    # 启动 WebSocket 服务器
    if _ws_enabled:
        start_server_thread(9012)
    srv = T(("0.0.0.0", PORT), H)
    print("Manage running on :" + str(PORT))
    srv.serve_forever()
