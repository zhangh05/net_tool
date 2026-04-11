# modules/llm.py - LLM API proxy, chat, async tasks, system prompt builder
import os, json, threading, time, random, re, urllib.request, urllib.error

# ─── Path globals (set by server.py) ─────────────────────────────────────────
AI_SOUL_FILE = None
AI_SOUL_TEMPLATE = None
AI_SYSTEM_PROMPT_FILE = None
AI_SKILLS_FILE = None
LLM_SETTINGS_FILE = None

def _init_paths(ai_soul_file, ai_soul_template, ai_system_prompt_file, ai_skills_file, llm_settings_file):
    global AI_SOUL_FILE, AI_SOUL_TEMPLATE, AI_SYSTEM_PROMPT_FILE, AI_SKILLS_FILE, LLM_SETTINGS_FILE
    AI_SOUL_FILE = ai_soul_file
    AI_SOUL_TEMPLATE = ai_soul_template
    AI_SYSTEM_PROMPT_FILE = ai_system_prompt_file
    AI_SKILLS_FILE = ai_skills_file
    LLM_SETTINGS_FILE = llm_settings_file

# ─── LLM Settings ────────────────────────────────────────────────────────────
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
            except:
                pass
        return {}

def save_llm_settings(data):
    with _llm_lock:
        existing = {}
        if os.path.exists(LLM_SETTINGS_FILE):
            try:
                with open(LLM_SETTINGS_FILE) as f:
                    existing = json.load(f)
            except:
                pass
        existing.update(data)
        with open(LLM_SETTINGS_FILE, 'w') as f:
            json.dump(existing, f, indent=2)

# ─── LLM Chat ────────────────────────────────────────────────────────────────
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

# ─── Async Topology Analysis Infrastructure ──────────────────────────────────
PENDING_ANALYSIS = {'pending': False, 'result': None}

def set_analysis_pending(val):
    PENDING_ANALYSIS['pending'] = val

def set_analysis_result(val):
    PENDING_ANALYSIS['result'] = val

def get_analysis_pending():
    return PENDING_ANALYSIS.get('pending', False)

def get_analysis_result():
    return PENDING_ANALYSIS.get('result')

def async_analyze_topology(task_id, topo_data, api_url, api_key, model, temperature, max_tokens_cfg):
    """Background thread: analyze topology and store result."""
    try:
        # Build analysis prompt from topology data
        nodes = topo_data.get('nodes', [])
        edges = topo_data.get('edges', [])
        summary = topo_data.get('summary', {})

        device_types = summary.get('deviceTypes', {})
        device_count = summary.get('deviceCount', len(nodes))
        connection_count = summary.get('connectionCount', len(edges))

        # Build node/edge listing
        lines = []
        for n in nodes:
            lines.append(f"  设备: {n.get('label', n.get('id', '?'))} [ID={n.get('id','')}, type={n.get('type','?')}, IP={n.get('ip','')}]")
        for e in edges:
            lines.append(f"  连线: {e.get('fromLabel', e.get('source', '?'))} --{e.get('srcPort','?')}→ {e.get('toLabel', e.get('target', '?'))} [{e.get('tgtPort','?')}]")

        topo_context = '\n'.join(lines) if lines else '  （空拓扑）'

        analysis_prompt = f"""请分析以下网络拓扑，提供专业的技术建议：

## 拓扑概览
- 设备数量：{device_count} 台
- 连线数量：{connection_count} 条
- 设备类型：{json.dumps(device_types, ensure_ascii=False)}

## 拓扑详情
{topo_context}

请从以下角度进行分析：
1. 拓扑结构是否合理（核心层、汇聚层、接入层设计）
2. 潜在的单点故障风险
3. IP地址规划是否合理
4. 端口利用率是否均衡
5. 安全隐患和优化建议

请用中文回复，结构清晰，适合网络运维工程师阅读。"""

        messages = [{'role': 'user', 'content': analysis_prompt}]
        reply = call_llm_chat(api_url, api_key, model, messages, temperature, max_tokens_cfg)
        set_analysis_result(reply)
        set_analysis_pending(False)
    except Exception as e:
        set_analysis_result(f'分析失败: {str(e)}')
        set_analysis_pending(False)

# ─── Async Chat Task Infrastructure ──────────────────────────────────────────
PENDING_TASKS = {}   # {task_id: {'status': 'pending'|'done'|'error', 'reply': '', 'ops': [], 'error': ''}}

def create_task():
    task_id = 't' + str(int(time.time() * 1000)) + str(random.randint(100, 999))
    PENDING_TASKS[task_id] = {'status': 'pending', 'reply': '', 'ops': [], 'error': ''}
    return task_id

def complete_task(task_id, status, reply='', ops=None, error=''):
    if task_id in PENDING_TASKS:
        PENDING_TASKS[task_id]['status'] = status
        PENDING_TASKS[task_id]['reply'] = reply
        PENDING_TASKS[task_id]['ops'] = ops or []
        PENDING_TASKS[task_id]['error'] = error

def get_task(task_id):
    return PENDING_TASKS.get(task_id)

def extract_ops_from_reply(reply):
    """Extract ops from LLM reply text — returns list of op dicts."""
    # Lazy import to avoid circular
    from . import topology
    ops = []
    for line in reply.split('\n'):
        if '[op]' in line:
            op = topology.parse_op(line.strip())
            if op:
                ops.append(op)
    json_ops = topology.extract_json_ops(reply)
    seen = set()
    for op in json_ops:
        key = op.get('action', '') + ':' + (op.get('id', '') or op.get('from', '') or '')
        seen.add(key)
    for op in list(ops):
        key = op.get('action', '') + ':' + (op.get('id', '') or op.get('from', '') or '')
        if key not in seen:
            json_ops.append(op)
            seen.add(key)
    return json_ops

def execute_op(op, topo_data, proj_id):
    """Execute a topology op from AI reply and save result."""
    from . import topology
    action = op.get('action', '')
    params = op.get('params', {})
    nodes = topo_data.setdefault('nodes', [])
    edges = topo_data.setdefault('edges', [])
    res = topology.execute_single_action(action, params, nodes, edges)
    if res.get('ok'):
        topology.save_project_file(proj_id, 'topo.json', topo_data)
    return res.get('error') or f"{action}: OK"

def async_chat(task_id, messages, api_url, api_key, model, temperature, max_tokens_cfg, proj_id, session_id, user_text, topo_data):
    """Background thread: call LLM, store reply, mark task done."""
    from . import topology
    try:
        if topology.append_session_message(proj_id, session_id, 'user', user_text) is None:
            complete_task(task_id, 'error', error='project not found: ' + proj_id)
            return
        reply = call_llm_chat(api_url, api_key, model, messages, temperature, max_tokens_cfg)
        ops = extract_ops_from_reply(reply)
        topology.append_session_message(proj_id, session_id, 'assistant', reply, ops=ops)
        if ops:
            for op in ops:
                try:
                    r = execute_op(op, topo_data, proj_id)
                except Exception as e:
                    r = "异常: " + str(e)
                if r:
                    topology.append_session_message(proj_id, session_id, 'system', "[%s] %s" % (op.get('action', '?'), r))
        complete_task(task_id, 'done', reply=reply, ops=ops)
    except Exception as e:
        complete_task(task_id, 'error', error=str(e))

# ─── System Prompt Builder ────────────────────────────────────────────────────
def build_system_prompt(proj_id):
    """从外部文件构建 AI System Prompt（分层结构）。"""
    from . import topology as _topo

    # 1. Load topology
    topo = _topo.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
    nodes = topo.get('nodes', [])
    edges = topo.get('edges', [])

    # 2. Build topology context (human-readable format)
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

    # 3. Read ai_soul.json
    soul_data = {"name": "NetOps AI", "persona": "", "capabilities": [], "safety": {}}
    try:
        with open(AI_SOUL_FILE, 'r', encoding='utf-8') as f:
            soul_data = json.load(f)
    except Exception:
        pass

    soul_name = soul_data.get("name", "NetOps AI")
    soul_persona = soul_data.get("persona", "")
    capabilities = soul_data.get("capabilities", [])

    # 4. Read ai_system_prompt.txt
    rules_content = ""
    try:
        with open(AI_SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
            rules_content = f.read()
    except Exception:
        rules_content = "（规则文件读取失败）"

    # 5. Read ai-skills.txt
    skills_content = ""
    try:
        with open(AI_SKILLS_FILE, 'r', encoding='utf-8') as f:
            skills_content = f.read()
    except Exception:
        skills_content = "（技能文件读取失败）"

    # 6. Replace placeholders
    rules_content = rules_content.replace("{topology_context}", topo_context)
    rules_content = rules_content.replace("{skills_content}", skills_content)

    # 7. Build tone parts
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


def build_plan_system_prompt(proj_id):
    """构建规划模式 system prompt — 基于拓扑生成 [plan] 块。"""
    from . import topology as _topo

    # 1. Load topology
    topo = _topo.load_project_file(proj_id, 'topo.json', {'nodes': [], 'edges': []})
    nodes = topo.get('nodes', [])
    edges = topo.get('edges', [])

    # 2. Build topology context
    topo_parts = [f"当前拓扑：共 {len(nodes)} 台设备，{len(edges)} 条连线"]
    if nodes:
        dev_list = []
        for n in nodes:
            dev_list.append(f"{n.get('label','?')}（ID={n.get('id','?')}，类型={n.get('type','?')}）")
        topo_parts.append("设备列表：" + "; ".join(dev_list))
    if edges:
        edge_list = []
        for e in edges:
            src = next((n.get('label','?') for n in nodes if n.get('id') == e.get('from')), '?')
            tgt = next((n.get('label','?') for n in nodes if n.get('id') == e.get('to')), '?')
            edge_list.append(f"{src} → {tgt}")
        topo_parts.append("连线列表：" + "; ".join(edge_list))
    topo_context = "\n".join(topo_parts)

    # 3. Read ai_soul.json
    soul_data = {"name": "NetOps AI", "persona": "网络规划助手"}
    try:
        with open(AI_SOUL_FILE, 'r', encoding='utf-8') as f:
            soul_data = json.load(f)
    except Exception:
        pass
    name = soul_data.get("name", "NetOps AI")
    role = soul_data.get("role", "网络规划助手")

    return f"""你是 {name}，{role}。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输出规则（最高优先级）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你只输出 [plan] 块。不要输出任何解释、思考过程、确认提示。
禁止说"等待确认"、"请确认"、"是否继续"。
禁止输出 [plan] 块以外的任何内容。

格式（只有这一种）：
[plan]
[op] <action>:<key=val,...>
[/plan]

示例1 - 添加设备：
用户：添加一台交换机
回复：
[plan]
[op] add:id=SW01,type=switch,label=交换机
[/plan]

示例2 - 连接已有设备：
用户：连接两台已有交换机
回复：
[plan]
[op] connect:from=SW01,to=SW02,srcPort=GE0/0/1,tgtPort=GE0/0/1,desc=交换机互联
[/plan]

示例3 - 一次完成添加+连接（优先互相连接）：
用户：添加两台交换机并连线
回复：
[plan]
[op] add:id=SW01,type=switch,label=交换机1
[op] add:id=SW02,type=switch,label=交换机2
[op] connect:from=SW01,to=SW02,srcPort=GE0/0/1,tgtPort=GE0/0/1,desc=交换机互联
[/plan]

如果用户提到"连接"已有设备，明确说明连接哪两个已有设备，不要自行选择。
如果用户没有指定目标，"连线"默认指将本次添加的设备互相连接。
禁止将新设备连接到拓扑中已有的设备（除非用户明确要求"接入现有网络"）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【操作指令格式】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

设备操作：
[op] add:id=<ID>,type=<类型>,label=<名称>,ip=<IP>,desc=<描述>
[op] delete:id=<ID>
[op] modify:id=<ID>,label=<新名称>,ip=<新IP>,desc=<新描述>
[op] move:id=<ID>,x=<横坐标>,y=<纵坐标>

连线操作：
[op] connect:from=<源ID>,to=<目标ID>,srcPort=<端口号>,tgtPort=<端口号>,desc=<描述>
[op] disconnect:from=<源ID>,to=<目标ID>

设备类型：router | switch | firewall | server | PC | cloud | internet

**端口号必须使用 GE0/0/X 格式**，例如：GE0/0/1、GE0/0/2、GE0/1/1（第一位=插槽号，第二位=子卡号，第三位=端口号）。禁止使用纯数字如 1、2，必须带 GE 前缀。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【关键规则】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 严格按用户要求的**数量**执行，不要多做
2. 每个 ID 在整个 plan 中只能出现一次（禁止重复 add 同一 ID）
3. connect/disconnect 只操作拓扑中已存在的设备和连线
4. 如果拓扑为空，只能 add 新设备，不能 connect
5. "连线"默认指连接本次 plan 中新添加的设备（from 和 to 都是在同一个 plan 中 add 过的设备 ID）
6. 除非用户明确要求，不要将新设备连接到已有设备
7. 不要生成任何多余内容，只输出 [plan] 块
8. **端口分配（强制规则）**：所有设备的端口必须严格递增分配，不允许重复。
   - 格式统一为 GE0/0/X（三段），例如 GE0/0/1、GE0/0/2、GE0/0/3...
   - 同一设备：已用 GE0/0/1 → 下个必须用 GE0/0/2（不能回头用 GE0/0/1）
   - 新设备：从 GE0/0/1 开始
   - 禁止为同一设备分配已用过的端口（哪怕该端口后来空闲了也不允许）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【当前拓扑状态】
{topo_context}
"""


def load_goal_system_prompt():
    """Load the goal-mode system prompt."""
    global AI_SYSTEM_PROMPT_FILE
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
