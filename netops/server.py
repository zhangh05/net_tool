#!/usr/bin/env python3
"""
NetTool Server - 重构版
将原 2929 行 server.py 拆分为 modules/ 子模块
"""
import os, sys, time, signal

# ═══════════════════════════════════════════════════════════════════
# 路径配置
# ═══════════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('NETTOOL_DATA', '/root/nettooldata')
PROJECTS_DIR = os.path.join(DATA_DIR, 'projects')
UPLOADS_DIR = os.environ.get('NETTOOL_UPLOADS', '/tmp/netool_uploads')
CONFIG_DIR = os.path.join(DATA_DIR, 'config')
AI_SOUL_FILE = os.path.join(CONFIG_DIR, 'ai_soul.json')
AI_SOUL_TEMPLATE = os.path.join(BASE_DIR, 'templates', 'ai_soul.template.json')
AI_SYSTEM_PROMPT_FILE = os.path.join(CONFIG_DIR, 'ai_system_prompt.txt')
AI_SKILLS_FILE = os.path.join(CONFIG_DIR, 'ai-skills.txt')
LLM_SETTINGS_FILE = os.path.join(CONFIG_DIR, 'llm_settings.json')

# ═══════════════════════════════════════════════════════════════════
# 依赖库检查
# ═══════════════════════════════════════════════════════════════════
MISSING = []
try:
    import bcrypt
except ImportError:
    MISSING.append('bcrypt')
try:
    import yaml
except ImportError:
    MISSING.append('pyyaml')

if MISSING:
    print(f"[警告] 缺少可选依赖: {', '.join(MISSING)}。使用 pip install {' '.join(MISSING)} 安装以启用完整功能。")

# ═══════════════════════════════════════════════════════════════════
# 模块初始化
# ═══════════════════════════════════════════════════════════════════
from modules import topology, auth, llm, terminal, websocket, http_handler

# 初始化拓扑模块路径
topology._init_paths(BASE_DIR, DATA_DIR, PROJECTS_DIR, UPLOADS_DIR, CONFIG_DIR)

# 初始化认证模块路径
auth._init_paths(PROJECTS_DIR)

# 初始化 LLM 模块路径
llm._init_paths(AI_SOUL_FILE, AI_SOUL_TEMPLATE, AI_SYSTEM_PROMPT_FILE, AI_SKILLS_FILE, LLM_SETTINGS_FILE)

# 初始化 HTTP Handler 模块
http_handler._init(auth, llm, topology, terminal, websocket)
http_handler._init_paths(int(os.environ.get('PORT', '3000')), BASE_DIR, os.environ.get('NETTOOL_OPEN_MODE', 'false').lower() == 'true')

# 设置拓扑的 WebSocket 回调
topology.WS_AVAILABLE = True
topology._notify_ws_topo_change = websocket.ws_notify_topo_change

# ═══════════════════════════════════════════════════════════════════
# 启动时的初始化
# ═══════════════════════════════════════════════════════════════════
def _bootstrap():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # 创建默认 AI 配置文件
    if not os.path.exists(AI_SOUL_FILE):
        default_soul = {
            "name": "NetOps AI",
            "persona": "你是一个可靠的网络运维助手，精通网络架构设计和配置管理。",
            "capabilities": ["网络拓扑设计", "设备配置", "故障排查"],
            "tone": {"do": ["清晰解释", "主动建议"], "avoid": ["过度技术术语"]},
            "safety": {"confirm_critical": True, "require_double_confirm": ["delete", "shutdown"]}
        }
        with open(AI_SOUL_FILE, 'w', encoding='utf-8') as f:
            import json
            json.dump(default_soul, f, indent=2, ensure_ascii=False)

    if not os.path.exists(AI_SYSTEM_PROMPT_FILE):
        with open(AI_SYSTEM_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write("""## AI 行为规范

### 语气
- 说：清晰解释、主动建议、分步骤说明
- 避免：过度技术术语、不确认就操作

### 拓扑操作规则
1. 所有拓扑变更必须用 [op] 格式
2. 禁止自动连线，必须用户确认
3. 删除操作需二次确认
4. 每次最多添加 5 个设备

### 格式要求
- 添加设备：[op] add:id=设备ID,type=类型,label=名称
- 添加连线：[op] add_edge:from=源ID,to=目标ID
- 删除设备：[op] del:id=设备ID
""")

    if not os.path.exists(AI_SKILLS_FILE):
        with open(AI_SKILLS_FILE, 'w', encoding='utf-8') as f:
            f.write("""# NetOps AI 技能库

## 网络设备配置
- Cisco IOS 配置
- 华为 VRP 配置
- 交换机 VLAN 配置
- 路由器 OSPF/BGP 配置

## 故障排查
- ping/tracepath 诊断
- 端口连通性测试
- 路由表检查
""")

    # 迁移所有现有项目（添加 users.json）
    auth.migrate_all_projects()

    # 确保默认项目存在
    if not os.path.isdir(os.path.join(PROJECTS_DIR, 'Admin')):
        topology.create_project('Admin', 'Admin', 'admin', os.environ.get('NETTOOL_ADMIN_PASS', 'admin'))

_bootstrap()

# ═══════════════════════════════════════════════════════════════════
# 信号处理
# ═══════════════════════════════════════════════════════════════════
def _signal_handler(signum, frame):
    print(f"\n[Server] Received signal {signum}, shutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ═══════════════════════════════════════════════════════════════════
# 启动服务器
# ═══════════════════════════════════════════════════════════════════
PORT = int(os.environ.get('PORT', '3000'))
OPEN_MODE = os.environ.get('NETTOOL_OPEN_MODE', 'false').lower() == 'true'

# 启动 WebSocket 实时同步服务器
websocket.start_ws_server()
time.sleep(0.5)

# 启动 Terminal WebSocket 服务器
terminal.start_term_ws_server()
time.sleep(0.5)

# 启动 HTTP 服务器
server_address = ('', PORT)
httpd = http_handler.T(server_address, http_handler.H)
print(f"=" * 70)
print(f"  NetTool Server ({'开放模式' if OPEN_MODE else '安全模式'})")
print(f"  HTTP:      http://0.0.0.0:{PORT}")
print(f"  WebSocket: ws://0.0.0.0:{websocket.WS_PORT}  (实时拓扑同步)")
print(f"  Terminal:  ws://0.0.0.0:{terminal.TERM_WS_PORT}  (远程终端)")
print(f"  数据目录:  {DATA_DIR}")
print(f"  项目目录:  {PROJECTS_DIR}")
print(f"  PID:       {os.getpid()}")
print(f"=" * 70)

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\n[Server] Shutting down...")
    httpd.shutdown()
