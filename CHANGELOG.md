# 更新日志

所有重要更新均记录于此。格式：`类型(范围): 描述`

类型前缀：`feat` 新功能 | `fix` Bug 修复 | `chore` 维护 | `docs` 文档 | `refactor` 重构

---

## 2026-04-12

### feat: Plan 完整性保护 + 实时执行进度

**Plan 哈希校验**
- 新增 CRC32 哈希函数（`simpleHash` 前端 / `simple_hash` 后端）
- `POST /api/manage/execute` 增加 `plan_hash` 字段校验
- 防篡改：哈希不匹配时拒绝执行，返回 "计划已被篡改"
- UTF-8 兼容：中文 label 的 JSON 序列化字节序列与前端完全一致

**WebSocket 实时执行步骤**
- `broadcast_exec_step()` — 每执行完一条操作立即推送
- 前端 `renderExecStep()` — 实时渲染执行进度条 + 步骤列表
- 乱序保护：`_renderedSeqs` Set 去重，防止同一条结果重复渲染
- `done` 信号延迟 600ms 清理：等待最后几条 exec_step 追上
- `_execCleanupPending` flag：防止重复清理 container

**Plan 确认 UI 全新设计**
- `.plan-confirm` 三段式结构：header / body / footer
- `fmtOpHtml()` 同时支持原始格式（add/connect）和标准格式（add_node/add_edge）
- `showPlanConfirm()` 同步调用，SHA-256 存储到 `_pendingPlanHash`
- `CancelPlan()` 精确定位 DOM 节点，移除时清除 `_pendingPlanHash`
- 新增 CSS 变量：`--space-*` 间距、`--shadow-*` 阴影

**会话历史增强**
- `plan_confirm` 类型写入 `messages.json`，附带 plan 摘要
- 兼容旧格式：未携带 `plan_confirm` 时不写入

**错误处理**
- `save_operation` 在 error 分支也被调用（不因异常跳过）
- NetOps 执行异常时返回友善错误提示

### fix: 细节修复

- `nid_r` → `node_id`（http_handler.py 第 926 行）
- 移除 `/api/manage/goal` 废弃端点代码
- `.bak` 备份文件清理（server.py.bak / app.js.bak）

---

## 2026-04-11

### feat: 两层 AI 架构完成

**Manage 协调层（:8999）**
- `POST /api/manage/chat` — 意图分类（classify_intent）、转发至 NetOps
- `build_manage_system_prompt()` — 薄协调层 prompt（只路由不执行）
- Plan 摘要生成 + `plan_confirm` 类型返回
- MiniMax AI 分析执行结果，自然语言汇报给用户

**执行链路修复**
- `parse_execute_command()` 新增三种格式 + Natural Language fallback
- 即使 AI 说"已成功添加 R5"，也能从文本提取设备 ID 并真正执行
- System prompt 更新：强制要求输出 `action:` 行
- NetOps `add_edge` handler 增加自动端口分配逻辑

**UI 改进**
- 动态进度阶段：分析需求 → 理解意图 → 规划步骤 → 执行中
- Toast 通知（右上角）
- 快速回复按钮（AI 询问时显示）
- 执行后操作按钮
- 设备位置网格布局

### feat: 资源池完善

- `PortAllocator` 端口分配器：`GE0/0/X` 三段式格式
- 自动规避 `usedPorts` 中已占用的端口
- `ipcalc2`（9002）、`usermanage`（9004）集成

### fix: 多项修复

- `save_topo` 路径 bug（projects 拼写错误）
- 路由重定向 bug（`'null'` 字符串而非 `None`）
- 节点数据扁平化 bug（LLM 返回单设备时包一层 list）
- `GET /api/ping/` POST 方法缺失
- 会话隔离逻辑：每个项目独立 `sessions/` 目录

---

## 2026-04-09

### feat: MemPalace 记忆系统

- MCP 服务器：`mcp_server.py`（单例守护 + PID 文件锁）
- 知识图谱三元组：`(主体, 谓词, 客体)` SQLite 存储
- FTS5 全文搜索
- SOUL.md Memory Protocol 强制执行
- 四 agent（main/yunwei/news/topo）全部注册 MemPalace

### feat: Skills 系统

- 13 个 skill 覆盖：浏览器自动化、生命周期管理、权限系统、上下文管理、工具执行管道等
- Agent Browser（无头浏览器）、Verification Agent（对抗验证）等

### docs: UI 设计规范

- `DESIGN.md` v1.0：Linear + Vercel Dashboard 风格
- CSS 变量体系：`--space-*` `--shadow-*` `--transition-*` `--z-*`
- 组件四态规范：默认/hover/active/disabled

---

## 2026-04-07

### feat: 两层 AI 架构确立

```
用户 → Manage AI（协调层/MiniMax）
              ↓ 下发需求
         NetOps AI（实施层/网络专家）
              ↓ 制定计划/执行
         NetOps 执行引擎
```

- Manage AI = 统筹协调（理解需求、分析结果、统筹汇报）
- NetOps AI = 真正实施（网络专业知识、拓扑操作执行）
- MiniMax 分析：NetOps 执行完成后，Manage 调用 MiniMax 分析执行结果

---

## 早期版本

### 2026-04-05
- NetTool 平台架构确立
- NetOps AI System Prompt 重构：三层分离（身份层/规则层/工具层）
- 新增「先说再做」+「操作前自检」+「操作后验证」机制

### 2026-04-04
- AI Chat 移至 Manage（9000 端口保留给拓扑编辑）
- 完整资源池概念引入
