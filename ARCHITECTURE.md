# NetTool Multi-Agent Architecture

## Overview

NetTool is evolving from a single monolithic application into a **multi-agent orchestration platform** with a clear separation of concerns:

```
用户
  ↓
Manage（协调层 / Orchestrator）
  ↓
  ├── NetOps（工具Agent：网络拓扑）
  └── NetKnowledge（工具Agent：知识库）【规划中】
```

## Design Principles

### 1. Manage = 薄协调层（Thin Orchestrator）

Manage 只负责三件事：
- **意图识别**：判断用户请求该由哪个 Agent 处理
- **路由分发**：把任务转交给对应的 Agent
- **结果聚合**：把 Agent 的结果汇总返回给用户

Manage **不应该**：
- 懂网络拓扑的细节（设备类型、端口分配规则）
- 自己解析 action 指令再转发
- 维护复杂的执行计划逻辑

### 2. Agent = 垂直领域专家

每个 Agent 独立运作，有自己的：
- LLM 调用能力（理解领域内的自然语言）
- 执行能力（对自己的操作负责）
- 会话历史（管理自己的上下文）

当前唯一 Agent：**NetOps**，负责网络拓扑的构建、修改、查询。

## System Architecture

### Components

| 组件 | 角色 | 职责 |
|------|------|------|
| **Manage** | 协调层 | 意图分类、路由分发、结果汇总 |
| **NetOps** | 工具Agent | 网络拓扑操作（添加/删除设备、连线等）|
| **NetKnowledge** | 工具Agent（未来）| 知识库、协议差异、设计审查 |

### Ports

| 端口 | 应用 | 用途 |
|------|------|------|
| 8999 | Manage | HTTP |
| 9000 | NetOps | HTTP |
| 9001 | 预留 | — |
| 9002 | (旧版停用) | — |
| 9003–9010 | 预留 | — |
| 9011 | NetOps | Terminal WS（SSH/Telnet）|
| 9012 | Manage | AI 流式输出 WebSocket |
| 9013 | NetOps | 拓扑同步 WebSocket（原 9002）|

## Communication Protocol

### Manage → NetOps

Manage 通过 HTTP POST 转发用户请求到 NetOps：

```
POST /api/agent/chat
{
  "message": "用户的需求描述",
  "history": [...],          // 最近 20 条对话历史
  "project_id": "default"
}
```

**NetOps 响应**：
```json
{
  "ok": true,
  "reply": "NetOps 的自然语言回复"
}
```

### LLM Response Format（Manage System Prompt）

Manage 的 LLM 输出必须包含路由决定：

```
[ROUTE_TO=netops] 需要在拓扑中添加相关设备。
好的，我来帮您设计一个三层网络架构...

[ROUTE_TO=none] 这是一个闲聊。
你好！有什么我可以帮您的吗？
```

格式：`[ROUTE_TO=<agent_id>]` 或 `[ROUTE_TO=none]`，后面跟自然语言回复。

## Intent Classification

Manage 的 LLM 根据请求内容判断路由到哪个 Agent：

### NetOps（netops）
适用场景：
- 提到"拓扑"、"网络架构"、"设计网络"
- 提到设备类型（路由器、交换机、防火墙）
- 要求添加/删除/修改设备或连线
- 涉及 IP 地址规划、子网划分

### NetKnowledge（netknowledge）【未来】
适用场景：
- 问"是什么"、"有什么区别"
- 问协议原理（OSPF、BGP、VLAN）
- 问不同厂家配置差异（Cisco vs 华为）
- 故障排查、设计合理性审查

### None（直接回复）
适用场景：
- 闲聊
- 问候
- 无法归类为任何 Agent 的请求

## Concurrency Model

### 并行（未来）

当一个请求同时涉及多个 Agent 时：

```
用户: "帮我设计网络，并告诉我 OSPF 和 RIP 的区别"

Manage 并发：
  ├── NetKnowledge: 查询协议差异
  └── NetOps: 准备拓扑上下文

结果聚合（Manage LLM）：
  → 合并两个 Agent 的输出，返回给用户
```

### 串行（依赖场景）

当 NetOps 生成拓扑后需要 NetKnowledge 审查：

```
NetOps 生成拓扑 → NetKnowledge 审查合理性 → 返回用户
```

## Session Management

### Manage Session
- 维护对话历史（`session_messages` 表，`type='AI'`）
- 历史随请求转发给 NetOps（最近 20 条）

### NetOps Session
- 独立维护自己的会话历史（`sessions` 表）
- 每个项目独立

### 跨 Agent 上下文

Manage 在转发时附加历史：
```python
{
  "history": session_msgs[-20:]  # 最近 20 条 Manage 侧对话
}
```

NetOps 将这些历史注入自己的 messages 数组，让 LLM 有完整上下文。

## Future Extensions

### NetKnowledge Agent

**定位**：网络知识库 + 设计审查

**能力**：
- 协议原理查询（RFC、书籍）
- 厂家配置差异（Cisco / 华为 / Juniper）
- 拓扑设计合理性审查
- 故障排查知识

**接口**（规划中）：
```
POST /api/knowledge/query
{
  "query": "OSPF 和 RIP 的区别",
  "context": {...}
}
```

### 新增 Agent 的步骤

1. 在 Manage `build_manage_system_prompt()` 的 `【可用 Agent】` 部分添加新 Agent 的描述
2. 在 Manage `/api/manage/chat` 的路由逻辑中添加 `elif route_target == "new_agent":`
3. 在新 Agent 中实现对应的 `/api/agent/chat` 端点

## 已完成的改动（Task A）

### Manage Server（server.py）

| 改动 | 说明 |
|------|------|
| `build_manage_system_prompt()` 重写 | 从 160 行精简到 ~40 行，只保留路由规则 |
| `/api/manage/chat` 重构 | 删除 action 解析和执行逻辑，改为解析 `[ROUTE_TO=xxx]` 并转发 |
| 删除 `parse_execute_command` | 不再需要，不再解析 action 块 |
| 删除 `parse_goal_from_reply` | 不再需要 |
| 删除 `parse_steps_from_reply` | 不再需要 |
| 删除 `topo_info` 收集 | Manage 不再需要了解拓扑详情 |
| 代码行数 | 1685 → 990 行（减少 41%）|

### NetOps Server（modules/http_handler.py）

| 改动 | 说明 |
|------|------|
| `/api/agent/chat` 支持 `history` 参数 | 接受 Manage 转发的对话历史 |

## 待完成

- [ ] NetKnowledge Agent 开发（规划中）
- [ ] Manage 前端 UI 调整（去除 action 相关的状态显示）
- [ ] 错误处理优化（NetOps 无响应时的友好提示）
- [ ] 多个 Agent 并发调用逻辑
- [ ] Agent 能力注册机制（代替硬编码路由规则）
