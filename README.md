# NetTool - 网络运维 AI 协作平台

> 自然的语言，简单的操作，专业的网络。

NetTool 是一个**网络运维 AI 协作平台**，通过两层 AI 架构（协调层 + 实施层）实现自然语言驱动的网络拓扑管理和设备运维。

---

## 架构概览

```
用户
  │
  ▼
┌─────────────────────────┐
│  Manage (协调层 :8999)   │  ← 理解意图、转发请求、展示结果
│  AI: MiniMax-M2         │
└────────┬────────────────┘
         │ HTTP / Plan
         ▼
┌─────────────────────────┐
│  NetOps (实施层 :9000)   │  ← 生成计划、执行拓扑操作
│  AI: MiniMax-M2.5       │
└────────┬────────────────┘
         │ 持久化
         ▼
   文件系统（项目拓扑）
```

| 服务 | 端口 | 职责 | 模型 |
|------|------|------|------|
| Manage | 8999 | 协调层：意图分类、计划确认、结果展示 | MiniMax-M2 |
| NetOps | 9000 | 实施层：拓扑操作、计划生成与执行 | MiniMax-M2.5 |
| WebSocket | 9012 | 实时推送：流程阶段 + 执行步骤 | — |

---

## 核心能力

### Manage — 协调层

- **意图分类**：自动判断用户需求类型（闲聊/NetOps/未来扩展）
- **计划确认 UI**：展示操作摘要，支持用户确认或取消
- **结果分析**：执行完成后调用 AI 分析结果，自然语言汇报
- **会话管理**：多项目支持，每个项目独立会话历史

### NetOps — 实施层

- **拓扑编辑**：可视化拖拽，支持路由器/交换机/防火墙/服务器
- **AI 助手**：自然语言添加/修改/删除设备和连线
- **设备终端**：浏览器内 Telnet/SSH 连接（规划中）
- **端口自动分配**：GE0/0/X 格式，自动规避冲突

---

## 快速开始

```bash
cd /root/nettool
bash start.sh      # 启动 NetOps (:9000) + Manage (:8999)
bash stop.sh       # 停止所有服务
```

访问：
- Manage 管理界面：`http://localhost:8999`
- NetOps 拓扑编辑：`http://localhost:9000`

---

## 工作流程

```
用户输入 → Manage 意图分类 → NetOps 生成计划 → 用户确认
    → 执行（WebSocket 实时步骤）→ AI 分析结果 → 用户
```

1. **发送请求**：`POST /api/manage/chat` — 用户说"添加两台交换机"
2. **计划确认**：返回 plan_confirm，前端展示摘要，用户点确认
3. **执行操作**：Plan 完整性校验（CRC32），通过后逐条执行
4. **实时推送**：WebSocket 推送每一步执行结果
5. **结果汇报**：所有操作完成后，AI 分析结果并汇报给用户

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | 原生 JavaScript + CSS 变量体系 |
| 后端 | Python 3（自定义 HTTP 服务器） |
| 实时推送 | WebSocket（Python threading） |
| 可视化 | Cytoscape.js |
| AI | MiniMax API（自动穿透） |
| 终端 | xterm.js + Python PTY（规划中） |

---

## 目录结构

```
net_tool/
├── manage/                  # 协调层（薄）
│   ├── server.py            # HTTP 入口、意图分类、哈希校验
│   ├── websocket_server.py  # WebSocket 实时推送
│   ├── js/app.js           # 前端逻辑、renderExecStep
│   ├── css/main.css        # Plan 确认 UI、执行进度 UI
│   └── AI_sys_prompt/      # AI 灵魂配置
│
├── netops/                  # 实施层（厚）
│   ├── server.py           # 路由分发
│   ├── modules/
│   │   ├── http_handler.py # 执行入口、normalize_ops
│   │   ├── topology.py     # 拓扑操作、端口分配
│   │   └── llm.py         # Plan 生成 Prompt
│   └── data/projects/     # 项目数据（拓扑、会话、快照）
│
├── ARCHITECTURE.md          # 完整架构文档
├── CHANGELOG.md            # 更新日志
└── start.sh / stop.sh      # 启停脚本
```

---

## API 概览

### Manage 对外接口（:8999）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/manage/projects` | 项目列表 |
| GET | `/api/manage/topology` | 拓扑数据 |
| POST | `/api/manage/chat` | AI 聊天（自动路由） |
| POST | `/api/manage/execute` | 执行已确认的计划 |
| POST | `/api/manage/snapshot` | 创建拓扑快照 |

### NetOps 内部接口（:9000）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agent/topology` | 拓扑数据 |
| POST | `/api/agent/plan` | 生成执行计划 |
| POST | `/api/agent/goal/execute` | 执行完整计划 |

---

## 保护机制

- **Plan 完整性校验**：CRC32 哈希，前后端一致，防 DOM 篡改
- **端口自动分配**：GE0/0/X 格式，自动递增，告别冲突
- **WebSocket 乱序保护**：seq 标记 + `_renderedSeqs` 去重
- **失败操作日志**：执行失败也写入 oplog，不丢记录

---

## 工具矩阵

| 工具 | 状态 | 说明 |
|------|------|------|
| NetOps | ✅ 已上线 | 网络拓扑编辑器 + AI 助手 |
| NetDiag | 🔲 规划中 | 网络诊断工具 |
| NetConf | 🔲 规划中 | 设备配置管理 |

---

## License

MIT
