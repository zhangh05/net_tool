# NetOps AI Chat 整合方案

> 设计目标：让 AI 能读懂拓扑上下文、感知网络设备状态，并实际执行 ping/终端/备份等操作。

---

## 一、现有架构分析

### 1.1 Chat Panel（index.html）

| 组件 | 职责 | 关键函数 |
|------|------|----------|
| `chatPanel` | 右侧滑出面板，380px宽 | `toggleChat()` |
| `chatInput` | 消息输入框 | `sendChat()` |
| `chatMessages` | 消息列表容器 | `addChatBubble(role, text, ts, ops)` |
| `chat-ops-card` | 操作建议卡片（AI返回可执行操作时显示） | `renderOpsCard()`, `executeTopoOps()` |
| `topoMode` | 拓扑上下文模式：detail（首条发送完整）/ brief（后续精简） | `setTopoMode()` |

**已有流程：**
1. `sendChat()` → `POST /api/chat/send`（含 topology 数据）
2. AI 返回文本中含 `[op]` 标记的操作
3. `parseOpsFromText()` 解析 `[op] add:type=router...` 等操作
4. `addChatBubble()` 显示操作卡片，用户点"执行" → `executeTopoOps()`
5. `removeTypingIndicator()` / `showTypingIndicator()` 打字机动画

**现有消息格式（已支持）：**
```
用户: 帮我添加一台路由器
AI: 好的，我来添加路由器 [op] add:id=R1,type=router,x=300,y=200
→ 显示操作卡片 → 用户确认 → 执行 addNode()
```

### 1.2 Server（server.py）

| 端点 | 逻辑 |
|------|------|
| `POST /api/chat/send` | 接收 user text + topology，构建 messages → `call_llm_chat()` |
| `build_system_prompt()` | 组合 AI soul + 操作规范（从 `ai_soul_template.json` 读取） |
| `call_llm_chat()` | 代理到 LLM，支持 Anthropic（MiniMax）和 OpenAI 兼容格式 |

**现有拓扑注入方式（`/api/chat/send` 中）：**
- `withTopo=true` 时，将拓扑序列化为文本附加到用户消息
- detail 模式：完整拓扑（所有节点 label/id/type/ip + 连线）
- brief 模式：仅摘要（设备数 + 关键设备名）

### 1.3 现有能力总结

✅ 已实现：拓扑上下文注入、拓扑操作（增删改设备/连线）、session 会话管理
❌ 未实现：设备状态感知（ping/在线状态）、实际设备操作（SSH/备份）、跨系统上下文

---

## 二、拓扑上下文注入方案

### 2.1 注入时机

| 时机 | 内容 | 方式 |
|------|------|------|
| 首条消息（detail 模式） | 完整拓扑（节点+连线+端口） | 追加到 user 消息 |
| 后续消息（brief 模式） | 摘要（设备数+关键设备+在线状态） | 追加到 user 消息 |
| AI 调用工具后（Tool Result） | 工具执行结果 | 作为独立 assistant 消息注入 |
| 用户选中设备时 | 被选中设备的详细信息 | 单独 system 提示 |

### 2.2 增强拓扑上下文格式（Detail 模式）

```
━━━ 当前拓扑（共 N 个设备，M 条连线）━━━

设备列表：
  [R1] 路由器 | IP=192.168.1.1 | 端口: GE0/0/0(已用) GE0/0/1(可用)
  [SW1] 交换机 | IP=192.168.1.2 | 端口: GE0/0/0(已用) GE0/0/1(已用) GE0/0/2(可用)
  [FW1] 防火墙 | IP=192.168.1.254 | 端口: GE0/0/0(已用) GE0/0/1(可用)
  ...

连线列表：
  [R1].GE0/0/0 ←→ [SW1].GE0/0/0  (光纤)
  [R1].GE0/0/1 ←→ [FW1].GE0/0/0  (铜缆)
  ...

设备状态（从锚点同步）：
  [R1] ● 在线（2小时前检测）
  [SW1] ● 在线（2小时前检测）
  [FW1] ○ 离线（5小时前检测）
```

### 2.3 Brief 模式（后续消息）

```
当前拓扑：5台设备，4条连线
关键设备：R1(路由器,192.168.1.1) | SW1(交换机,192.168.1.2) | FW1(防火墙,192.168.1.254)
```

### 2.4 注入策略修改（server.py）

```python
# server.py /api/chat/send 中，修改拓扑注入部分：
# 1. 优先从锚点系统获取设备在线状态
# 2. 注入格式升级为增强版（带端口状态、设备状态）
# 3. 当 AI 返回工具调用时，将 tool_calls 结果作为独立消息注入

# 伪代码示意：
if with_topo and topo_info:
    # 获取锚点状态
    anchor_status = fetch_anchor_status(topo_info)  # 新增
    topo_text = build_enhanced_topo_context(topo_info, anchor_status)
    user_content = user_text + "\n\n" + topo_text
```

---

## 三、工具定义（Tool Description）

> 格式参考 `/root/nettool/agent/skills.json`，专供 AI 在对话中理解和使用。

### 3.1 工具列表

```
━━━ 可用工具 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### get_topology()
描述：获取当前 NetOps 拓扑中的所有设备节点和连线信息
参数：无
返回：
  {
    "nodes": [
      {"id": "n123", "label": "R1", "type": "router", "ip": "192.168.1.1",
       "usedPorts": ["GE0/0/0"], "availablePorts": ["GE0/0/1","GE0/0/2"]},
      ...
    ],
    "edges": [
      {"source": "n123", "target": "n456", "srcPort": "GE0/0/0", "tgtPort": "GE0/0/0"},
      ...
    ]
  }
使用场景：用户询问拓扑结构、设备列表、想了解有哪些设备时调用

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### ping_device(ip)
描述：对指定 IP 地址发送 ICMP ping，检测设备是否在线
参数：
  - ip (string, required): 目标 IP 地址，如 "192.168.1.1"
返回：
  {"success": true, "output": "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=0.5 ms", "reachable": true}
  或
  {"success": false, "output": "Request timeout", "reachable": false}
使用场景：用户问"X设备在线吗"、"能ping通吗"、"帮我测试Y地址"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### get_device_info(ip)
描述：从锚点系统获取设备的详细信息（品牌、型号、SN、在线时长、CPU/内存等）
参数：
  - ip (string, required): 设备 IP 地址
返回：
  {
    "success": true,
    "device": {
      "ip": "192.168.1.1",
      "hostname": "Core-Router-01",
      "type": "路由器",
      "vendor": "Huawei",
      "model": "AR3260",
      "sn": "ABC123456",
      "uptime": "120天3小时",
      "cpu": "23%",
      "mem": "45%",
      "reachable": true,
      "last_seen": "2秒前"
    }
  }
  或 {"success": false, "error": "设备未在锚点注册或无法连接"}
使用场景：用户问"给我看看R1的详情"、"这台设备什么型号"、"设备运行状态"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### open_terminal(ip, method, port)
描述：生成终端连接 URL，直接在浏览器打开 Web Terminal 连接到设备
参数：
  - ip (string, required): 设备 IP，如 "192.168.1.1"
  - method (string, required): 连接方式，"ssh" | "telnet"
  - port (number, optional): 端口，默认 22(ssh) / 23(telnet)
返回：
  {"success": true, "url": "/tools/terminal/?ip=192.168.1.1&method=ssh", "message": "终端已准备就绪"}
  或 {"success": false, "error": "设备IP格式无效"}
使用场景：用户说"帮我连接R1"、"打开SW1的SSH终端"、"打开防火墙的telnet"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### backup_config(ip)
描述：远程登录设备执行配置备份（save + display current-config），结果存入服务器
参数：
  - ip (string, required): 设备 IP 地址
返回：
  {
    "success": true,
    "backup_file": "/data/backups/192.168.1.1_20260401_193000.cfg",
    "output": "保存成功，配置文件已备份",
    "size_kb": 128,
    "timestamp": "2026-04-01 19:30:00"
  }
  或 {"success": false, "error": "设备不在线或认证失败"}
使用场景：用户说"备份R1的配置"、"帮我备份这台交换机的配置"、"定期备份"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### scan_network(subnet)
描述：扫描指定网段，探测在线主机
参数：
  - subnet (string, required): 网段，支持 "192.168.1.0/24" 或 "192.168.1.1-254"
返回：
  {"success": true, "online": ["192.168.1.1","192.168.1.2","192.168.1.254"], "count": 3}
使用场景：用户问"这个网段有哪些设备在线"、"帮我扫一下192.168.1.0/24"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 3.2 系统提示词追加（server.py build_system_prompt）

在现有操作规范后追加：

```python
TOOL_SYSTEM_ADDITION = """

━━━ 网络操作工具（可选使用）━━━
AI 可以根据用户需求，主动调用以下工具获取信息或执行操作。
调用工具时，AI 应先分析用户需求，选择最合适的工具。

【工具调用格式】
当需要调用工具时，在回复末尾附加（不要在主回复文本中间穿插）：

[TOOL_CALL]
tool: get_topology
args: {}

[TOOL_CALL]
tool: ping_device
args: {"ip": "192.168.1.1"}

[TOOL_CALL]
tool: get_device_info
args: {"ip": "192.168.1.1"}

[TOOL_CALL]
tool: open_terminal
args: {"ip": "192.168.1.1", "method": "ssh", "port": 22}

[TOOL_CALL]
tool: backup_config
args: {"ip": "192.168.1.1"}

【工具调用时机指引】
- 用户问"有哪些设备" → get_topology()
- 用户问"XX设备在线吗" → ping_device(ip)
- 用户问"设备详情/型号/状态" → get_device_info(ip)
- 用户说"帮我连接/打开终端" → open_terminal(ip, method)
- 用户说"备份配置" → backup_config(ip)
- 用户问"这个网段有什么" → scan_network(subnet)

【操作与工具的关系】
- 拓扑操作（增删改设备/连线）→ 继续使用现有的 [op] add/del/add_edge 格式
- 设备实际操作（ping/终端/备份）→ 使用新的 [TOOL_CALL] 格式
- 两者可以同时存在于一条回复中
"""
```

---

## 四、执行流程

### 4.1 完整交互时序

```
用户输入
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ sendChat()                                               │
│  ├─ 读取当前拓扑 (cy.json)                               │
│  ├─ 读取锚点设备状态 (GET /api/anchors)                  │
│  └─ 构造消息体: user_text + 拓扑上下文 + 设备状态        │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ POST /api/chat/send                                      │
│  ├─ build_system_prompt() → 系统提示词（规则+工具定义）  │
│  ├─ 构建 messages[]（含历史 session 消息）               │
│  └─ call_llm_chat() → 调用 LLM                         │
└──────────────────────────────────────────────────────────┘
   │
   ├─── AI 返回纯文本 ───→ 直接显示 addChatBubble("ai", text)
   │
   ├─── AI 返回含 [op] ─→→ 解析拓扑操作 → 显示 chat-ops-card
   │                         用户点"执行" → executeTopoOps() → 操作拓扑
   │
   └─── AI 返回含 [TOOL_CALL] ──→ 解析工具调用
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              get_topology()  ping_device()  get_device_info()
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────────┐
                    │ 将工具结果注入 messages，作为         │
                    │ role=assistant 的 tool result        │
                    │ 再次调用 LLM（Tool Use 模式）        │
                    └──────────────────────────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────────┐
                    │ LLM 基于工具结果生成最终回复         │
                    │ addChatBubble("ai", final_text)      │
                    └──────────────────────────────────────┘
```

### 4.2 典型场景流程

**场景1：用户问"R1在线吗"**
```
用户: R1在线吗？
AI分析: 需要 ping_device("192.168.1.1")
AI回复前: [TOOL_CALL] tool: ping_device, args: {"ip": "192.168.1.1"}
          （显示"正在检测..."）
后台执行: ping 192.168.1.1
工具结果: {"success": true, "reachable": true, "time": "0.5ms"}
再次调用LLM，注入工具结果
最终回复: "R1 在线 ✓ 响应时间 0.5ms，设备运行正常。"
```

**场景2：用户说"帮我看看R1的详细信息"**
```
用户: R1的详细信息？
AI: [TOOL_CALL] get_device_info("192.168.1.1")
     "正在查询R1的设备信息..."
后台: GET /api/anchors → 锚点返回设备详情
工具结果: {"hostname": "Core-Router-01", "model": "Huawei AR3260", ...}
最终回复: "R1 信息如下：\n型号：Huawei AR3260\n序列号：ABC123456\n运行时间：120天3小时\nCPU：23% 内存：45%"
```

**场景3：用户说"帮我连接R1的终端"**
```
用户: 帮我连接R1的SSH终端
AI: [TOOL_CALL] open_terminal("192.168.1.1", "ssh")
     "好的，正在为你打开SSH终端..."
后台: 生成终端 URL → 通知前端打开
结果: {"url": "/tools/terminal/?ip=192.168.1.1&method=ssh"}
前端: 打开 terminal panel，加载该 URL
回复: "✅ 终端已打开，正在连接到 R1 (192.168.1.1)..."
```

---

## 五、实现计划

### 5.1 第一阶段：基础（前端改动）

| 任务 | 文件 | 改动 |
|------|------|------|
| A. 工具调用解析 | `index.html` | `parseToolsFromText()` 解析 `[TOOL_CALL]` |
| B. 工具调用卡片 | `index.html` | 新增 `chat-tool-card` UI，显示执行状态 |
| C. 工具执行入口 | `index.html` | `executeToolCall(tool, args)` → AJAX 调用后端 |
| D. 终端面板打开 | `index.html` | `openTerminalPanel(url)` 打开底部 terminal |

### 5.2 第二阶段：后端（server.py 改动）

| 任务 | 端点 | 改动 |
|------|------|------|
| E. 锚点状态查询 | `GET /api/anchors` | 从锚点服务获取设备在线状态 |
| F. Ping 执行 | `POST /api/netops/ping` | 执行 `ping -c 4 ip`，返回结果 |
| G. 设备信息 | `POST /api/netops/device-info` | 调锚点 `/api/anchors` 获取详情 |
| H. 终端 URL 生成 | `POST /api/netops/terminal-url` | 生成 web terminal URL |
| I. 配置备份 | `POST /api/netops/backup` | SSH 登录 → save → 存文件 |
| J. 工具定义追加 | `build_system_prompt()` | 追加 Tool Description 到 system prompt |
| K. 工具调用路由 | `/api/chat/send` | 解析 `[TOOL_CALL]` → 调用对应端点 → 将结果注入 messages |

### 5.3 工具执行 API（新增端点）

```
POST /api/netops/ping
Body: {"ip": "192.168.1.1"}
Response: {"success": true, "reachable": true, "output": "64 bytes from...", "time_ms": 0.5}

POST /api/netops/device-info
Body: {"ip": "192.168.1.1"}
Response: {"success": true, "device": {...}} 或 {"success": false, "error": "..."}

POST /api/netops/terminal-url
Body: {"ip": "192.168.1.1", "method": "ssh", "port": 22}
Response: {"success": true, "url": "/tools/terminal/?ip=192.168.1.1&method=ssh"}

POST /api/netops/backup
Body: {"ip": "192.168.1.1"}
Response: {"success": true, "backup_file": "...", "size_kb": 128}
```

---

## 六、关键技术难点与替代方案

### 6.1 难点1：AI 无法正确使用工具

**问题**：LLM 对 `[TOOL_CALL]` 格式的遵守不稳定，可能乱放、漏放、或格式错误。

**解决方案**：
- 方案A（推荐）：使用 Tool Use / Function Calling 模式——利用模型的原生 function calling 能力，而非文本内嵌
  - OpenAI / MiniMax API 的 `tools` 参数直接声明工具定义
  - 模型原生返回 `tool_calls` 块，无需解析文本
  - server.py 需改为 `tools=` 参数 + `tool_call` 处理
- 方案B：强化 prompt，在 system prompt 中强调"必须用 `[TOOL_CALL]` 格式"，并用 few-shot 示例

**推荐方案A**，修改 `call_llm_chat()` 支持 tools 参数：

```python
def call_llm_chat(api_url, api_key, model, messages, temperature=0.7,
                  max_tokens=8192, tools=None, tool_result=None):
    # Anthropic 格式（MiniMax）
    if '/anthropic' in base:
        payload['tools'] = tools  # 传入工具定义
        payload['tool_choice'] = {"type": "auto"}
        # tool_result 作为特殊消息注入

    # OpenAI 格式
    else:
        payload['tools'] = tools
        payload['tool_choice'] = "auto"
```

### 6.2 难点2：设备操作安全性

**问题**：AI 可以执行 ping/终端/备份，有误操作风险。

**解决方案**：
- 备份操作需二次确认（chat-confirm-modal 已有）
- 所有写操作（备份、配置修改）都需要用户确认
- 只读操作（ping、查看设备信息）可直接执行，但需显示执行状态
- 配置操作（备份）记录操作日志（opLog）

### 6.3 难点3：多工具并发调用

**问题**：AI 可能一次请求多个工具调用（如先 ping 再查详情）。

**解决方案**：
- 前端串行执行：解析所有 `[TOOL_CALL]` → 逐个执行 → 累积结果 → 一起注入
- server.py 支持批量 tool_call 处理

### 6.4 难点4：锚点系统不可用时

**问题**：锚点服务（9006）未启动时，`get_device_info()` 会失败。

**替代方案**：
- 前端降级：锚点不可用时，`get_device_info()` 改为显示拓扑中已有的 IP/desc 信息
- 后端降级：锚点请求超时 3 秒后返回 `{"success": false, "error": "锚点服务不可用"}`
- AI prompt 中说明："如果锚点不可用，返回拓扑中已有的信息即可"

### 6.5 难点5：拓扑上下文过长导致 LLM 超限

**问题**：详细模式下拓扑文本可能很长，超过 max_tokens。

**替代方案**：
- 设备数 > 20 时自动切换 brief 模式
- 只发送 IP 已配置的设备，跳过未配置 IP 的设备
- 超出 token 限制时截断拓扑（保留前 N 个设备 + 连线）

---

## 七、消息格式汇总

### 7.1 AI 回复中的嵌入标记

| 标记 | 含义 | 解析方 |
|------|------|--------|
| `[op] add:id=R1,type=router` | 拓扑操作 | `parseOpsFromText()` |
| `[TOOL_CALL] tool: ping_device, args: {"ip": "..."}` | 工具调用 | `parseToolsFromText()`（新增） |
| `---` | 消息内容结束分隔符 | AI 被指示在 `---` 之前放主回复 |

### 7.2 工具调用卡片 UI

```html
<div class="chat-tool-card">
  <div class="tool-title">🔧 正在执行：ping_device</div>
  <div class="tool-args">IP: 192.168.1.1</div>
  <div class="tool-loading">⏳ 检测中...</div>
  <!-- 执行完成后： -->
  <div class="tool-result success">✅ 在线 | 响应 0.5ms</div>
</div>
```

---

## 八、优先级

| 优先级 | 任务 | 理由 |
|--------|------|------|
| P0 | Tool Use 模式（函数调用）| 核心能力，决定 AI 能否正确使用工具 |
| P0 | `get_topology()` + `ping_device()` | 最常用，覆盖 80% 场景 |
| P1 | `get_device_info()` | 锚点集成，设备详情查询 |
| P1 | `open_terminal()` | 终端直连，实际操作设备 |
| P2 | `backup_config()` | 配置备份，需安全二次确认 |
| P2 | `scan_network()` | 网段扫描，补充探测能力 |
