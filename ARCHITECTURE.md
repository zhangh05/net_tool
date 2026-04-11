# NetTool 完整架构文档

> 最后更新：2026-04-12

---

## 一、系统架构总览

NetTool 采用三层 AI 协调架构：

```
用户
  │
  ▼
Manage (8999) — 协调层（薄）
  │  理解意图、转发请求、展示结果
  ▼
NetOps (9000) — 实施层（厚）
  │  生成 plan、执行操作、管理拓扑
  ▼
持久化层（文件系统）
```

| 服务 | 端口 | 职责 | 模型 |
|-------|------|------|------|
| Manage | 8999 | 协调层：意图分类、转发、展示 | MiniMax-M2 |
| NetOps | 9000 | 实施层：拓扑操作、plan 生成、执行 | MiniMax-M2.5 |
| WebSocket | 9012 | 实时推送：流程阶段、执行步骤 | — |

---

## 二、完整调用流程

### 2.1 用户说「添加两台交换机并连接」

```
┌─────────────────────────────────────────────────────────────┐
│ 步骤 1：用户发起请求                                          │
└─────────────────────────────────────────────────────────────┘
用户输入 → POST /api/manage/chat
  {
    "message": "添加两台交换机并连接",
    "project_id": "100"
  }

  ▼ Manage server.py /api/manage/chat
  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 2：意图分类（classify_intent）                         │
  │ "添加" in user_text → intent = "netops"                   │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 3：WS 推送流程阶段                                   │
  │ broadcast_layer_stage("coord", "routing", 30, "📋 转发...") │
  │ broadcast_layer_stage("netops", "receiving", 40, "📥...")   │
  │ broadcast_layer_stage("netops", "planning", 50, "🧠...")   │
  └─────────────────────────────────────────────────────────────┘

  ▼ Manage 调用 NetOps
  POST http://127.0.0.1:9000/api/agent/plan
  {
    "project_id": "100",
    "user_text": "添加两台交换机并连接"
  }

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 4：NetOps 生成执行计划                                 │
  │ NetOps LLM (build_plan_system_prompt)                      │
  │    → 读取拓扑上下文                                         │
  │    → 生成 [plan] 块                                        │
  │    → 返回 {ok: true, plan: [...], plan_summary: "..."}    │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 5：WS 推送等待确认                                    │
  │ broadcast_layer_stage("netops", "confirming", 70, "⏳...")   │
  │ broadcast_layer_stage("coord", "confirming", 70, "⏳...")   │
  └─────────────────────────────────────────────────────────────┘

  ▼ 返回给前端
  {
    "ok": true,
    "type": "plan_confirm",
    "plan": [{action:"add", id:"SW01", ...}, ...],
    "plan_summary": "添加2台设备，建立1条连线",
    "pending_confirmation": true
  }

┌─────────────────────────────────────────────────────────────┐
│ 步骤 6：前端展示计划确认 UI                                  │
│ showPlanConfirm() → 渲染新设计卡片 + SHA-256 哈希存储        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 用户点击「确认执行」

```
┌─────────────────────────────────────────────────────────────┐
│ 步骤 7：前端验证 + 发送执行请求                               │
│ simpleHash(ops) → _pendingPlanHash                         │
│ POST /api/manage/execute                                     │
│ {                                                           │
│   "project_id": "100",                                      │
│   "ops": [...],        ← 原始 plan ops                       │
│   "plan_hash": "h7a9bbf54"  ← CRC32 校验哈希              │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 8：后端哈希校验（防篡改）                              │
  │ client_hash = payload.get("plan_hash")                      │
  │ expected = simple_hash(ops)  ← 同样 CRC32                  │
  │ if client_hash != expected → 拒绝执行                        │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 9：WS 推送执行开始                                    │
  │ broadcast_layer_stage("netops", "executing", 80, "⚙️...")   │
  └─────────────────────────────────────────────────────────────┘

  ▼ Manage 调用 NetOps 执行
  POST http://127.0.0.1:9000/api/agent/goal/execute
  { "project_id": "100", "plan": normalize_ops(raw_ops) }

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 10：NetOps 执行（同步）                                │
  │ for each op in plan:                                       │
  │   execute_single_action(action, params, nodes, edges)       │
  │   auto-allocate GE0/0/X ports                              │
  │ return {ok: true, results: [...], topology: {...}}          │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 11：逐条 WS 推送执行结果（实时）                       │
  │ for each result:                                           │
  │   broadcast_exec_step(i+1, total, action, target, ok, msg)  │
  │   → 前端 renderExecStep() 实时渲染每一步                    │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 12：WS 推送完成                                       │
  │ broadcast_layer_stage("netops", "done", 95, "✅...")       │
  │ broadcast_layer_stage("coord", "analyzing", 90, "🔍...")   │
  │ broadcast_layer_stage("coord", "reporting", 100, "✅...")   │
  │ broadcast_done()                                           │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ 步骤 13：前端处理 done 信号                                 │
  │ renderExecStep() 渲染最后一条 → 延迟 600ms                  │
  │ clearExecStepContainer() → 移除执行进度 UI                   │
  │ appendBubble("bot", "✅ 执行完成") → 补一条完成提示          │
  └─────────────────────────────────────────────────────────────┘
```

---

## 三、核心数据结构

### 3.1 Plan Ops（原始格式）

```javascript
// AI 返回的原始 plan ops
[
  {action: "add", id: "SW01", type: "switch", label: "交换机1"},
  {action: "add", id: "SW02", type: "switch", label: "交换机2"},
  {action: "connect", from: "SW01", to: "SW02", srcPort: "GE0/0/1", tgtPort: "GE0/0/1"}
]
```

### 3.2 Normalized Ops（NetOps 执行格式）

```javascript
// normalize_ops() 转换后
[
  {action: "add_node", params: {id: "SW01", type: "switch", label: "交换机1"}},
  {action: "add_node", params: {id: "SW02", type: "switch", label: "交换机2"}},
  {action: "add_edge", params: {from: "SW01", to: "SW02", srcPort: "GE0/0/1", tgtPort: "GE0/0/1"}}
]
```

### 3.3 执行结果

```javascript
// NetOps 返回的 results
[
  {action: "add_node", ok: true, id: "SW01", message: "添加设备 SW01 [switch]"},
  {action: "add_node", ok: true, id: "SW02", message: "添加设备 SW02 [switch]"},
  {action: "add_edge", ok: true, edge: "SW01 -> SW02", message: "添加连线 SW01 → SW02"}
]
```

---

## 四、端口分配规则

**格式**：`GE0/0/X`（Cisco 风格，三段式）

**规则**：
- 新设备：从 `GE0/0/1` 开始
- 已有设备：自动递增到 `max(usedPorts) + 1`
- 端口号严格递增，不复用

**自动分配逻辑**（`topology.py` 和 `http_handler.py`）：
```python
def next_port(device_id, used_list):
    max_num = max(int(p.split('/')[-1]) for p in used_list if p.isdigit()) or 0
    return f'GE0/0/{max_num + 1}'
```

---

## 五、Plan 完整性保护（SHA-256 哈希校验）

防止用户在浏览器 DevTools 中篡改 DOM 后执行不同的操作。

```
showPlanConfirm(ops)
  → simpleHash(ops)  // CRC32 of UTF-8 JSON
  → _pendingPlanHash 存储

用户点击确认
  → simpleHash(ops)  // 再次计算
  → plan_hash 随请求发出

后端校验
  → simple_hash(ops)  // 同样 CRC32
  → 比对 hash
    ├─ 相等 → 执行
    └─ 不等 → 拒绝，返回 "计划已被篡改"
```

---

## 六、WebSocket 实时推送

### 6.1 消息类型

| type | 触发时机 | 用途 |
|------|---------|------|
| `stage` | 任何阶段变化 | 更新流程追踪卡片（coord/netops 双层） |
| `exec_step` | 每个操作执行完成 | 实时渲染执行进度行 |
| `done` | 执行全部完成 | 清理 exec-step UI，重置流程卡片 |

### 6.2 exec_step 消息格式

```javascript
{
  "type": "exec_step",
  "step": 1,           // 当前第几步
  "total": 3,          // 总共几步
  "action": "add_node", // 操作类型
  "target": "SW01",    // 目标设备
  "ok": true,          // 是否成功
  "message": "添加设备 SW01 [switch]",  // 描述文字
  "seq": 1             // 序列号（防重）
}
```

---

## 七、两层流程追踪

```
协调层 Manage                    实施层 NetOps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
understanding (10%)  ─────────
                              receiving (40%)
routing (30%)       ───────────────────────────── planning (50%)
confirming (70%)    ───────────────────────────── confirming (70%)
analyzing (90%)     ◄─────────────────────────── executing (80%)
reporting (100%)    ◄──────────────────────────── done (95%)
```

---

## 八、关键文件索引

### Manage 协调层（8999）

| 文件 | 职责 |
|------|------|
| `server.py` | HTTP API、intent 分类、plan 哈希校验、WS 推送 |
| `js/app.js` | 前端 UI、renderExecStep、simpleHash |
| `css/main.css` | 样式（plan-confirm、exec-step、flow-card） |
| `websocket_server.py` | WS 服务、broadcast_* 函数 |
| `AI_sys_prompt/ai_soul.json` | AI 名称和角色 |

### NetOps 实施层（9000）

| 文件 | 职责 |
|------|------|
| `server.py` | HTTP 入口、路由分发 |
| `modules/http_handler.py` | HTTP handler、normalize_ops、执行入口 |
| `modules/topology.py` | 拓扑操作（add/delete/connect）、端口分配 |
| `modules/llm.py` | plan 生成 prompt、intent 识别 |

### 数据目录

```
/root/nettool/netops/data/projects/
  {project_id}/
    topo.json        # 拓扑数据
    sessions/        # AI 会话历史
    snapshots/       # 拓扑快照
    oplog/           # 操作日志
```

---

## 九、API 端点一览

### Manage（8999）对外接口

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/` | 管理界面 |
| GET | `/api/agents` | 查询可用 Agent |
| GET | `/api/manage/projects` | 项目列表 |
| GET | `/api/manage/topology?project_id=X` | 拓扑数据 |
| POST | `/api/manage/chat` | 发送消息（AI 入口） |
| POST | `/api/manage/execute` | 执行确认的 plan |
| GET | `/api/manage/snapshots?project_id=X` | 快照列表 |
| POST | `/api/manage/snapshot` | 创建快照 |
| POST | `/api/manage/clear_history` | 清空会话 |

### NetOps（9000）内部接口

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/agent/topology` | 拓扑数据 |
| POST | `/api/agent/plan` | 生成执行计划 |
| POST | `/api/agent/execute` | 执行单个操作（action: add_node 等） |
| POST | `/api/agent/goal/execute` | 执行 plan（含归一化和端口分配） |

---

## 十、已实现的保护机制

| 机制 | 实现位置 | 说明 |
|------|---------|------|
| Plan 哈希校验 | 前端 simpleHash + 后端 simple_hash | CRC32，防 DOM 篡改 |
| 端口自动分配 | topology.py / http_handler.py | GE0/0/X 格式，不重复 |
| 空结果保护 | server.py execute handler | 空 results 时发 nop 信号 |
| 乱序保护 | exec_step seq + _renderedSeqs | 防止重复渲染同一条 |
| done 延迟清理 | done handler 600ms setTimeout | 给最后几条 exec_step 追上来的时间 |
| _execCleanupPending flag | window._execCleanupPending | 防止重复清理 |
| 失败记录 | save_operation in error branch | 执行失败也写入操作日志 |
