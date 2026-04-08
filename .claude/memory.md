# NetTool 项目记忆文件

## 项目概述

NetTool 是一个**网络工具 × AI 深度集成**的综合平台，定位是让网络工程师能用自然语言驱动网络设备。

### 架构：三层 AI Agent

```
【用户层】 ─────────────────────────────────────────────────────────────▶
     │                                                                │
     │◀─────────────────────────────────────────────────────────────│
                          ▲
                          │ 自然语言
                          │
┌──────────────────────────┼──────────────────────────────────────────┐
│     【协调层 Manage】    │                                        │
│                          │                                        │
│  职责：                  │  职责：                                 │
│  - 理解用户需求          │  - 执行拓扑操作（增删改查设备/连线）     │
│  - 拆解任务步骤          │  - Telnet/SSH 设备控制                   │
│  - 风险判断              │  - 返回结构化执行结果                   │
│  - 等待用户确认          │                                        │
│  - 汇总结果汇报          │                                        │
│                          │                                        │
│  端口：8999              │  端口：9000                              │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
                           │ HTTP API / WebSocket
                           ▼
                    【执行层 NetOps】
```

### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| NetOps | 9000 | 网络拓扑编辑器 + AI执行层 |
| Manage | 8999 | 协调层统筹平台 |
| WebSocket | 9012 | Manage实时进度推送 |
| Terminal WS | 9011 | NetOps Telnet/SSH WebSocket |

---

## 目录结构

```
/root/nettool/
├── netops/                      # 执行层（NetOps）
│   ├── server.py                # HTTP服务器 + API（2900+行）
│   ├── index.html               # 单页应用，内嵌完整JS
│   ├── op-skills.js             # 前端拓扑skill注册表
│   ├── skills/
│   │   ├── ui-skills.js         # UI工具类skills（ping/toast等）
│   │   └── netops-device/
│   │       └── device-skill.js  # Telnet/SSH设备连接技能
│   ├── AI_sys_prompt/           # AI Prompt配置
│   │   ├── ai_soul.json         # 身份层
│   │   ├── ai_system_prompt.txt # 规则层
│   │   ├── ai-skills.txt        # 工具层
│   │   └── agent_system_prompt.txt # Agent角色定义
│   └── data/projects/           # 项目数据
│
├── manage/                       # 协调层（Manage）
│   ├── server.py                 # 协调层HTTP服务器（1589行）
│   ├── websocket_server.py        # WebSocket实时推送（200行）
│   ├── task_queue.py            # 任务队列（84行）
│   ├── index.html                # 前端
│   ├── js/app.js                 # 前端逻辑（1585行）
│   ├── css/main.css              # 样式
│   ├── AI_sys_prompt/
│   │   ├── ai_soul.json          # 协调层身份配置
│   │   └── agents.json           # Agent注册配置
│   └── records/                  # 会话和操作记录
│       ├── sessions/              # 会话JSON文件
│       └── ops/                  # 操作记录JSON文件
│
└── README.md                      # 项目说明文档
```

---

## 核心技术栈

| 组件 | 技术 |
|------|------|
| 前端框架 | 原生 JavaScript（单页应用） |
| 拓扑渲染 | Cytoscape.js 3.x |
| 终端模拟 | xterm.js + Python PTY |
| 后端框架 | Python 3 自定义 HTTPServer |
| AI 模型 | MiniMax M2.5-highspeed（内置） |
| 实时通信 | WebSocket |
| 项目数据 | JSON 文件存储 |

---

## 已发现的问题（待修复）

### P0 - device_* action 后端未实现

- `ai-skills.txt` 定义了 `device_connect`, `device_send` 等设备操控action
- 这些功能在前端 `device-skill.js` 中已完整实现（Telnet/SSH）
- 但后端 `server.py` 的 `_execute_single_action` **只处理拓扑操作**
- 后端不支持这些 action，AI 调用会返回"未知 action"错误

### P1 - Skills 文档与实际能力不匹配

后端 `_execute_single_action` 实际只支持：
```
add_node, add_edge, delete_node, delete_edge, modify_node, move_node
```

但 `ai-skills.txt` 还列出了未实现的：
- `device_*` 系列（前端有，后端无）
- `ping`, `get_topology_summary` 等（前端UI操作，非后端执行）

### P1 - batch actions 未告知 AI

- `server.py:2163` 支持批量操作（`actions` 数组）
- 但 AI prompt 中完全没有提及此能力

### P2 - delete_node 级联删除未说明

- `server.py:139` delete_node 会自动删除该设备所有连线
- `ai-skills.txt` 没有说明这是级联删除

### P2 - clear_topo action 未定义

- `server.py:1146` 支持 `clear_topo` 别名
- 但 `ai-skills.txt` 没有定义

### P3 - 端口命名规范不一致

| 文件 | 路由器端口 | 交换机端口 |
|------|------------|------------|
| `agent_system_prompt.txt` | GE0/0/0~GE0/0/3 | GE0/0/1~GE0/0/24 |
| `server.py` 默认 | GE0/0/1 | GE0/0/1 |

### P3 - 设备类型定义混乱

| 来源 | 类型数量 | 类型 |
|------|----------|------|
| `ai-skills.txt` | 7种 | router, switch, firewall, server, PC, cloud, internet |
| `manage/ai_soul.json` | 11种 | + router_core, router_advanced, switch_core, switch_access, printer, camera, loadbalancer |
| `netops/index.html` | 11种 | 同上（DEVICES对象） |

---

## API 调用链路

### 1. 用户发送消息

```
用户输入自然语言
        │
        ▼
POST /api/manage/chat
{
  "message": "帮我添加一台路由器",
  "project_id": "xxx"
}
```

### 2. Manage 协调层处理

`manage/server.py:1037-1438`:
1. 保存用户消息到本地会话
2. 查询 NetOps 拓扑（GET /api/agent/topology）
3. 构建三层 system prompt（ai_soul + rules + topology）
4. 调用 MiniMax LLM 分析意图
5. 解析 LLM 返回的 action（add_node / add_edge 等）
6. 危险操作等待用户确认
7. 执行操作或返回执行计划

### 3. Manage 下发任务到 NetOps

**方式A：直接执行（confirm=false）**
```
POST /api/agent/execute
{
  "action": "add_node",
  "project_id": "xxx",
  "id": "Router-1",
  "type": "router",
  "ip": "192.168.1.1"
}
```

**方式B：Goal Mode（复杂任务）**
```
POST /api/agent/goal
{
  "goal": "在R1下方添加一台接入交换机",
  "project_id": "xxx"
}
```

NetOps 返回：
```json
{
  "ok": true,
  "goal_summary": "添加接入交换机SW-New-1",
  "execution_plan": [
    {"step": 1, "action": "add_node", "params": {...}},
    {"step": 2, "action": "add_edge", "params": {...}}
  ],
  "risk_note": "..."
}
```

用户确认后执行：
```
POST /api/agent/goal/execute
{
  "project_id": "xxx",
  "plan": [...]
}
```

### 4. NetOps 执行操作

`netops/server.py:2147-2594`:
- `add_node` - 添加设备到拓扑
- `add_edge` - 添加设备连线
- `delete_node` - 删除设备（级联删除连线）
- `delete_edge` - 删除连线
- `modify_node` - 修改设备属性
- `move_node` - 移动设备位置

### 5. 结果返回

NetOps 返回：
```json
{
  "ok": true,
  "results": [
    {"step": 1, "action": "add_node", "ok": true, "message": "添加设备Router-1"},
    {"step": 2, "action": "add_edge", "ok": true, "message": "添加连线R1→SW1"}
  ],
  "topology": {"nodes": [...], "edges": [...]}
}
```

Manage 汇总后返回给用户自然语言结果。

---

## WebSocket 实时推送

Manage 连接到 `ws://localhost:9012` 接收：

| type | 说明 |
|------|------|
| `token` | AI 流式输出 token |
| `stage` | 协调层/执行层阶段更新 |
| `plan` | 执行计划等待确认 |
| `done` | 处理完成 |

---

## 三层 Prompt 架构

### NetOps AI（执行层）

| 层级 | 文件 | 内容 |
|------|------|------|
| 身份层 | `ai_soul.json` | name="拓扑专家", role, persona, boundaries |
| 规则层 | `ai_system_prompt.txt` | 操作流程、核心规则、先说再做 |
| 工具层 | `ai-skills.txt` | action 清单和参数格式 |
| Agent层 | `agent_system_prompt.txt` | Goal Mode 专用角色定义 |

### Manage AI（协调层）

| 层级 | 文件 | 内容 |
|------|------|------|
| 身份层 | `ai_soul.json` | name="阿维", role="统筹平台AI助手" |
| 规则层 | `server.py` 内 `build_manage_system_prompt()` | 三层分离架构、沟通规范、action格式 |
| Agent配置 | `agents.json` | netops agent 注册 |

---

## 设备类型（NetOps支持）

| type | 说明 | 颜色 |
|------|------|------|
| router | 路由器 | #3b82f6 |
| router_core | 核心路由器 | #6366f1 |
| router_advanced | 高级路由器 | #8b5cf6 |
| switch | 交换机 | #10b981 |
| switch_core | 核心交换机 | #6366f1 |
| switch_access | 接入交换机 | #10b981 |
| firewall | 防火墙 | #ef4444 |
| server | 服务器 | #8b5cf6 |
| pc | 个人电脑 | #f59e0b |
| cloud | 云 | #06b6d4 |

---

## 三层架构匹配分析（核心发现）

### 设计意图 vs 实际实现

**设计意图**：
```
用户层 → Manage LLM(协调) → NetOps LLM(执行) → 返回结果
```

**实际实现**：

#### 模式A：直接执行（普通模式，非Goal Mode）

```
用户消息 → Manage LLM分析意图 → Manage本地执行所有action
                                         ↓
                               np_post("/api/agent/execute")
                                         ↓
                               NetOps 只修改JSON数据
                                         ↓
                               返回结果给用户
```

**关键发现**：
- `manage/server.py:1145-1234` **Manage直接在本地执行所有action**
- 调用 `np_post("/api/agent/execute")` 只是让NetOps修改JSON数据
- **NetOps LLM 完全不被调用！**
- NetOps 的 `_execute_single_action` 只是数据操作，不涉及任何AI

#### 模式B：Goal Mode（复杂任务）

```
用户消息 → Manage LLM分析意图
                 ↓
        返回【任务目标】JSON
                 ↓
        POST /api/agent/goal
                 ↓
        NetOps LLM 被调用（生成执行计划）
                 ↓
        返回执行计划给Manage
                 ↓
        用户确认
                 ↓
        POST /api/agent/goal/execute
                 ↓
        NetOps 执行计划（只是数据操作，不调用LLM）
                 ↓
        返回结果给用户
```

**关键发现**：
- 只有Goal Mode下，NetOps LLM才被调用
- 但NetOps LLM只生成执行计划，不执行实际操作
- 实际操作还是Manage通过NetOps API执行

### 核心问题

#### 问题1：三层架构变成了"两层"

| 层 | 设计 | 实际 |
|---|------|------|
| 用户层 | ✅ | ✅ |
| 协调层 Manage LLM | ✅ | ✅ |
| 执行层 NetOps LLM | ✅ 被调用 | ❌ 大部分时候不调用 |

**Manage 实际上是"执行者"**，它通过NetOps的API操作数据，但NetOps的AI几乎不参与决策。

#### 问题2：NetOps LLM资源浪费

- NetOps 有完整的AI System Prompt（三层架构：ai_soul + rules + skills）
- 但**只有在Goal Mode下** `POST /api/agent/goal` 才会调用它
- **普通操作（add/delete node等）完全绕过了NetOps LLM**

#### 问题3：职责边界模糊

**Manage（协调层）实际做的**：
- LLM分析用户意图
- 直接执行所有拓扑操作
- 调用NetOps只是修改数据

**NetOps（执行层）实际做的**：
- 存储拓扑数据
- Goal Mode下生成执行计划
- 提供Telnet/SSH终端能力

**NetOps的"AI"形同虚设**——它的Prompt配置最完善，但实际很少被使用。

#### 问题4：Manage和NetOps都调用LLM，造成浪费

- Manage每次处理消息都调用MiniMax
- NetOps在Goal Mode下也调用MiniMax
- 两者都是MiniMax M2.5，实际是同一个模型被调用两次

### 架构建议

**方案A：保持现状（如果设计就是如此）**
- Manage作为唯一LLM决策者
- NetOps退化为纯数据存储+终端
- 更新README说明三层架构实际是"Manage为协调+执行，NetOps为数据层"

**方案B：让NetOps真正成为执行层**
- 所有拓扑操作都通过Goal Mode下发
- NetOps LLM负责理解任务并执行
- Manage LLM只做协调和汇总

**方案C：混合模式**
- 简单操作（add/delete node）→ Manage直接执行
- 复杂操作（需要规划的）→ Goal Mode下发给NetOps

---

## 待完成任务

- [ ] 确认三层架构设计意图（方案A/B/C）
- [ ] 如果需要真正的执行层，实现方案B或C
- [ ] 修复 device_* action 后端支持（或从 prompt 移除）
- [ ] 同步 ai-skills.txt 与实际支持能力
- [ ] 添加 batch actions 说明到 prompt
- [ ] 添加 delete_node 级联删除说明
- [ ] 定义 clear_topo action
- [ ] 统一端口命名规范
- [ ] 统一设备类型定义

---

## 最后更新

2026-04-08
