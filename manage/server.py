#!/usr/bin/env python3
import os, json, urllib.request, urllib.parse, time, re, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

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

def build_manage_system_prompt(topo_info="", session_context=""):
    soul = load_ai_soul()
    name = soul.get("name", "阿维")
    role = soul.get("role", "统筹平台 AI 助手")
    persona = soul.get("persona", "")
    boundaries = "\n".join(["- " + b for b in soul.get("boundaries", [])])
    tone_do = "\n".join(["- " + t for t in soul.get("tone", {}).get("do", [])])
    deerflow_principles = "\n".join(["- " + p for p in soul.get("deerflow_inspired", {}).get("principles", [])])

    # NetOps API 端点说明
    api_lines = ["【NetOps API 端点】（Manage 调用 NetOps 的实际路径）"]
    for ep in soul.get("netops_api", {}).get("endpoints", []):
        auto_str = "自动执行" if ep.get("auto") else "需确认"
        api_lines.append(f"- {ep.get('name', ep.get('when',''))} | {ep.get('method','')} {ep.get('path','')} | {auto_str}")
    netops_api_desc = "\n".join(api_lines)

    # 设备类型说明
    dt_lines = ["【设备类型参考】（拓扑中的 type 字段含义）"]
    for dtype, dinfo in soul.get("device_types", {}).items():
        dt_lines.append(f"- {dinfo.get('icon','')} {dtype}: {dinfo.get('label','')} — {dinfo.get('role','')}")
    device_types_desc = "\n".join(dt_lines)

    # 输出规范
    output_std = soul.get("output_standards", {})
    report_format = output_std.get("report_format", "").replace('\\n', '\n')
    table_rule = output_std.get("table_rule", "")
    emoji_usage = output_std.get("emoji_usage", "")

    # 工作流
    workflow = soul.get("workflow", {})
    workflow_priority = workflow.get("priority", "澄清 → 规划 → 确认 → 执行 → 汇报")
    workflow_steps = []
    for step in workflow.get("steps", []):
        workflow_steps.append(f"{step.get('phase','')}：{step.get('description','')}")
    workflow_desc = "\n".join([f"{i+1}. {s}" for i, s in enumerate(workflow_steps)])

    agents_desc = _format_agents_for_prompt()

    prompt = f"""你是 {name}，{role}。你是一个专业的网络运维工程师 AI，负责统筹协调 NetOps Agent 完成复杂任务。

【个人风格】
{persona}

【行为边界】
{boundaries}

【表达规范】
{tone_do}

【DeerFlow 设计原则】
{deerflow_principles}

【核心工作流】{workflow_priority}
{workflow_desc}

{netops_api_desc}

【可用 Agent 及能力】
{agents_desc}

【NetOps 拓扑数据格式】（用于解读 NetOps 返回的拓扑）
- nodes: [{{id, label, type, ip, x, y, availablePorts[], usedPorts[]}}]
- edges: [{{from, fromLabel, srcPort, to, toLabel, tgtPort}}]

{device_types_desc}

【结果汇报规范】
{report_format}

{table_rule}

【emoji 用法】
{emoji_usage}

【步骤输出格式】（NetOps 会自动计算具体参数，你只需输出目标描述）

**强制规则**：
- 如果用户需求明确（设备类型 + 连接关系 + IP）→ 必须立即输出【任务目标】JSON
- 如果用户需求不明确 → 先追问，不输出 JSON
- 禁止输出 Markdown 表格来描述执行计划，必须用【任务目标】JSON
- 禁止在 goal 里写坐标、端口、具体 IP，NetOps 会自动计算

【任务目标格式】
**强制规则**：
- 如果用户需求明确（设备类型 + 连接关系 + IP）→ 必须立即输出【任务目标】JSON
- 如果用户需求不明确 → 先追问，不输出 JSON
- 禁止输出 Markdown 表格来描述执行计划，必须用【任务目标】JSON
- 禁止在 goal 里写坐标、端口、具体 IP，NetOps 会自动计算

【任务目标格式】（必须严格遵循）

当用户需求已明确时，在回复末尾输出：

```text
【任务目标】
{{"goal": "在R1路由器下方新增一台接入交换机"}}
```

**goal 字段填写规则**：
- 设备关系：如「连接R1」「在R1下方」「与SW1相连」
- 设备类型：如「接入交换机」「路由器」「防火墙」
- 设备命名：如「命名为SW-New-1」（如有）
- IP：如用户指定了固定IP则填入，否则不填

**goal 示例**：

```text
用户：在R1下面加一台交换机，IP用192.168.1.100

好的，我来添加。

【任务目标】
{{"goal": "在R1路由器下方新增一台接入交换机，IP固定为192.168.1.100"}}
```

```text
用户：帮我把SW1和R1连接起来

好的，我来建立这条连线。

【任务目标】
{{"goal": "在SW1和R1之间建立连线"}}
```

```text
用户：添加一台防火墙到拓扑里

好的，但需要确认：防火墙连接在哪台设备上？比如连接R1？还是作为独立设备？

（等待用户确认后，再输出【任务目标】）
```

**错误示例（禁止）**：

❌ 用 Markdown 表格描述执行计划
❌ 输出 【任务步骤】 而不是 【任务目标】
❌ 在 goal 里写 "x=400, y=300"
❌ 在 goal 里写 "ge0/0/1"

【当前拓扑上下文】
{topo_info or "（暂无拓扑数据）"}

【会话上下文】
{session_context or "（暂无历史）"}
"""
    return prompt


REPORTER_PROMPT = """你是一个专业的运维汇报助手。根据下面提供的执行结果，生成一份结构化汇报。

**规则**：
- 只输出一段汇报内容，不要多余的开场白
- 用 Markdown 格式
- 重点说明：做了什么、结果如何、下一步
- 禁止重复原始 JSON 数据
- 禁止说"根据执行结果"这种模糊表述，要给出具体信息

**执行结果**：
{results}
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


def parse_goal_from_reply(reply_text):
    """Extract goal JSON from AI reply text.

    Looks for the 【任务目标】 marker and extracts the JSON inside.
    Returns (goal_dict, reply_before_marker) or (None, reply_text) if not found.
    """
    marker = "【任务目标】"
    idx = reply_text.find(marker)
    if idx == -1:
        return None, reply_text
    json_str = reply_text[idx + len(marker):].strip()
    start = json_str.find("{")
    if start == -1:
        return None, reply_text
    # Find matching close brace
    depth = 0
    end = start
    for i, c in enumerate(json_str[start:]):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = start + i + 1
                break
    json_str = json_str[start:end]
    try:
        goal_data = json.loads(json_str)
        if isinstance(goal_data, dict) and "goal" in goal_data:
            reply_before = reply_text[:idx].rstrip()
            return goal_data, reply_before
    except:
        pass
    return None, reply_text


def parse_steps_from_reply(reply_text):
    """Extract JSON steps from AI reply text."""
    marker = "【任务步骤】"
    idx = reply_text.find(marker)
    if idx == -1:
        return None, reply_text
    json_str = reply_text[idx + len(marker):].strip()
    start = json_str.find("[")
    if start == -1:
        return None, reply_text
    depth = 0
    end = start
    for i, c in enumerate(json_str[start:]):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = start + i + 1
                break
    json_str = json_str[start:end]
    try:
        steps = json.loads(json_str)
        if isinstance(steps, list) and all(
            isinstance(s, dict) and "step" in s and "agent" in s and "action" in s
            for s in steps
        ):
            reply_before = reply_text[:idx].rstrip()
            return steps, reply_before
    except:
        pass
    return None, reply_text


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
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(up).query))

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
            proj_id = params.get("project_id", "default")
            topo_data = np_get("/api/agent/topology?project_id=" + urllib.parse.quote(proj_id))
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
            proj_id = params.get("project_id", "default")
            msgs_data = np_get("/api/projects/" + urllib.parse.quote(proj_id) + "/sessions/default/messages")
            messages = msgs_data if msgs_data and isinstance(msgs_data, list) else []
            self.send_json({"messages": messages[-20:]})
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

            # 写用户消息到 NetOps
            np_post("/api/projects/" + urllib.parse.quote(project_id) + "/sessions/default/messages",
                     {"role": "user", "content": user_text})

            # 读取会话历史
            msgs_data = np_get("/api/projects/" + urllib.parse.quote(project_id) + "/sessions/default/messages")
            session_msgs = msgs_data if msgs_data and isinstance(msgs_data, list) else []

            # 读取拓扑
            topo_info = ""
            topo_data = np_get("/api/agent/topology?project_id=" + urllib.parse.quote(project_id))
            if topo_data and topo_data.get("ok"):
                topo = topo_data.get("topology", {})
                nodes = topo.get("nodes", [])
                edges = topo.get("edges", [])
                if nodes or edges:
                    lines = ["【当前拓扑】"]
                    lines.append("项目 " + project_id + "：共 " + str(len(nodes)) + " 个设备，" + str(len(edges)) + " 条连线")
                    for n in nodes[:10]:
                        ports_info = ""
                        if n.get("usedPorts"):
                            ports_info = " 已用端口:" + ",".join(n.get("usedPorts", [])[:4])
                        lines.append("  [" + n.get("type", "?") + "] " + n.get("label", "?") + " (ID=" + n.get("id", "") + ") IP=" + (n.get("ip") or "-") + ports_info)
                    for e in edges:
                        lines.append("  " + e.get("fromLabel", "?") + " --" + e.get("srcPort", "?") + "--> " + e.get("toLabel", "?") + " [" + e.get("tgtPort", "") + "]")
                    if len(nodes) > 10:
                        lines.append("  ...等共 " + str(len(nodes)) + " 个设备")
                    topo_info = "\n".join(lines)

            # 会话上下文（最近 6 条）
            session_context = ""
            if session_msgs:
                lines = []
                for msg in session_msgs[-6:]:
                    role = "用户" if msg.get("role") == "user" else "AI"
                    lines.append(role + ": " + msg.get("content", "")[:120])
                session_context = "\n".join(lines)

            # 构建 system prompt
            system = build_manage_system_prompt(topo_info, session_context)
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user_text}]

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

                req = urllib.request.Request(url, data=json.dumps(rd).encode("utf-8"), headers=headers, method="POST")
                with _NO_PROXY.open(req, timeout=120) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    if "/anthropic" in api_url:
                        text_parts = []
                        for block in resp_data.get("content", []):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        reply = "\n".join(text_parts) if text_parts else "(无内容)"
                    else:
                        reply = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")

                # 写 AI 消息到 NetOps
                np_post("/api/projects/" + urllib.parse.quote(project_id) + "/sessions/default/messages",
                         {"role": "assistant", "content": reply})

                # ── 解析目标（优先）──
                goal_data, reply_text = parse_goal_from_reply(reply)
                steps = None  # 默认无步骤

                if goal_data and goal_data.get("goal"):
                    # 有目标 → 调用 NetOps Goal API 获取执行计划
                    goal_text = goal_data["goal"]
                    goal_res = np_post("/api/agent/goal", {
                        "goal": goal_text,
                        "project_id": project_id
                    }, timeout=180)
                    if goal_res and goal_res.get("ok"):
                        exec_plan = goal_res.get("execution_plan", [])
                        if exec_plan:
                            # 格式化 NetOps 的 plan 为 Manage 的 steps 格式
                            steps = []
                            for item in exec_plan:
                                steps.append({
                                    "step": item.get("step", 0),
                                    "agent": "netops",
                                    "action": item.get("action", ""),
                                    "label": "[{agent}] {action}: {reason}".format(
                                        agent="netops",
                                        action=item.get("action", ""),
                                        reason=(item.get("reason", "")[:40] or item.get("params", {}).get("id", ""))
                                    ),
                                    "params": item.get("params", {}),
                                    "confirm": True,  # Goal 模式全部需要确认
                                    "goal_mode": True,
                                    "goal_summary": goal_res.get("goal_summary", goal_text),
                                    "topology_change": goal_res.get("topology_change", {}),
                                    "risk_note": goal_res.get("risk_note")
                                })
                            # 写入 NetOps 会话
                            topo_change = goal_res.get("topology_change", {})
                            np_post("/api/projects/" + urllib.parse.quote(project_id) + "/sessions/default/messages", {
                                "role": "system",
                                "content": "【执行计划】" + json.dumps(exec_plan, ensure_ascii=False)
                            })
                            self.send_json({
                                "ok": True,
                                "reply": reply_text,
                                "steps": steps,
                                "auto_exec": False,
                                "summary": None,
                                "goal_summary": goal_res.get("goal_summary", goal_text),
                                "topology_change": topo_change
                            })
                            return
                        else:
                            # Goal 找到了但 NetOps 没返回计划，当普通回复处理
                            pass
                    else:
                        # NetOps Goal API 失败，当普通回复
                        goal_err = goal_res.get("error", "未知错误") if goal_res else "NetOps 无响应"
                        self.send_json({
                            "ok": True,
                            "reply": reply_text + "\n\n⚠️ NetOps 执行计划生成失败：" + goal_err,
                            "steps": None,
                            "auto_exec": False,
                            "summary": None
                        })
                        return

                # ── 解析传统步骤（兼容旧格式）──
                steps, reply_text = parse_steps_from_reply(reply)

                if steps:
                    has_confirm = any(s.get("confirm", False) for s in steps)
                    if has_confirm:
                        # 有需要确认的步骤，只返回 steps 让用户确认
                        self.send_json({
                            "ok": True,
                            "reply": reply_text,
                            "steps": steps,
                            "auto_exec": False,
                            "summary": None
                        })
                    else:
                        # 全部自动执行
                        results = []
                        agents_data = load_agents()
                        for s in sorted(steps, key=lambda x: x.get("step", 0)):
                            agent_id = s.get("agent", "")
                            action = s.get("action", "")
                            params = s.get("params", {})
                            step_result = {"step": s.get("step"), "agent": agent_id, "action": action, "ok": False, "result": None, "error": None}
                            if agent_id in agents_data and action in agents_data[agent_id].get("actions", {}):
                                try:
                                    action_cfg = agents_data[agent_id]["actions"][action]
                                    method = action_cfg["method"]
                                    endpoint = action_cfg["endpoint"]
                                    endpoint = endpoint.replace("{project_id}", urllib.parse.quote(project_id))
                                    endpoint = endpoint.replace("{ip}", urllib.parse.quote(params.get("ip", "")))
                                    if method == "GET":
                                        res = np_get(endpoint)
                                        # Bug 4 fix: 失败时 res=None，需要正确设置 ok 标记
                                        if res is None:
                                            step_result["ok"] = False
                                            step_result["error"] = f"NetOps GET {endpoint} 失败"
                                        elif action == "get_topology" and isinstance(res, dict):
                                            res = {"ok": True, "topology": normalize_netops_topo(res)}
                                            step_result["ok"] = True
                                            step_result["result"] = res
                                        else:
                                            step_result["ok"] = True
                                            step_result["result"] = res
                                    elif method == "POST":
                                        post_payload = dict(params)
                                        post_payload["action"] = action
                                        post_payload["project_id"] = project_id
                                        res = np_post(endpoint, post_payload)
                                        if res is None:
                                            step_result["ok"] = False
                                            step_result["error"] = f"NetOps POST {endpoint} 失败"
                                        else:
                                            if isinstance(res, dict) and res.get("topology"):
                                                res = dict(res)
                                                res["topology"] = normalize_netops_topo(res)
                                            step_result["ok"] = True
                                            step_result["result"] = res
                                    else:
                                        step_result["ok"] = False
                                        step_result["error"] = f"unsupported method: {method}"
                                except Exception as ex:
                                    step_result["ok"] = False
                                    step_result["error"] = str(ex)
                            else:
                                step_result["error"] = f"unknown agent/action: {agent_id}/{action}"
                            results.append(step_result)
                        # 生成结构化汇报（Reporter 层）
                        summary = generate_summary(results, user_text, settings)
                        self.send_json({
                            "ok": True,
                            "reply": reply_text,
                            "steps": steps,
                            "auto_exec": True,
                            "results": results,
                            "summary": summary
                        })
                else:
                    self.send_json({"ok": True, "reply": reply, "steps": None})

            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        if pp == "/api/manage/summary":
            results = payload.get("results", [])
            project_id = payload.get("project_id", "default")
            settings = load_llm_settings()
            summary = generate_summary(results, "", settings)
            self.send_json({"summary": summary or "（无汇报内容）"})
            return

        # ── Goal Execute: POST /api/manage/goal/execute ──────────────────────
        # 用户确认后，执行 NetOps 返回的执行计划
        if pp == "/api/manage/goal/execute":
            project_id = payload.get("project_id", "default")
            plan = payload.get("plan", [])  # list of steps from NetOps goal API
            if not plan:
                self.send_json({"ok": False, "error": "缺少 plan"})
                return
            # 转发给 NetOps 执行
            res = np_post("/api/agent/goal/execute", {
                "project_id": project_id,
                "plan": plan
            })
            if not res:
                self.send_json({"ok": False, "error": "NetOps 执行请求失败"})
                return
            if not res.get("ok"):
                self.send_json({"ok": False, "error": res.get("error", "执行失败"), "results": res.get("results", [])})
                return
            # 格式化结果
            results = res.get("results", [])
            # 写执行结果到 NetOps 会话
            for r in results:
                status = "✅" if r.get("ok") else "❌"
                np_post("/api/projects/" + urllib.parse.quote(project_id) + "/sessions/default/messages", {
                    "role": "system",
                    "content": f"[{r.get('action','')}] {status} {r.get('message','')}"
                })
            self.send_json({"ok": True, "results": results, "topology": res.get("topology", {})})
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
    srv = T(("0.0.0.0", PORT), H)
    print("Manage running on :" + str(PORT))
    srv.serve_forever()
