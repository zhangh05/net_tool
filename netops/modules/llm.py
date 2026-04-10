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
