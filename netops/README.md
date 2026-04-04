# NetTool - 网络拓扑编辑器

基于 Cytoscape.js + Flask 的交互式网络拓扑编辑器，支持 AI 智能辅助和网络设备 Telnet/SSH 终端连接。

## 功能概览

### 🖱️ 拓扑编辑
- 左侧面板选择设备类型（路由器、交换机、防火墙、服务器、PC、云、WiFi AP、手机、互联网）
- 点击画布放置设备，支持拖拽移动
- 连线工具连接设备，支持端口标签
- 自动布局（Force-Directed 算法）
- 支持形状绘制和文本框标注

### 🤖 AI 智能助手
- 内置 AI（MiniMax M2.5）理解网络拓扑结构
- 自然语言操作设备：添加、删除、修改属性
- AI 可解释拓扑设计意图并提供优化建议

### 💻 Telnet/SSH 终端
- 直接在浏览器内连接网络设备
- 支持 Telnet 和 SSH 协议
- 多会话管理

### 💾 数据管理
- 多项目支持，每个项目独立存储
- 变更记录完整保存，可追溯每次操作
- 导入/导出 JSON 格式拓扑文件

## 启动服务

```bash
cd /root/nettool/netops
bash start.sh      # 启动
bash stop.sh       # 停止
```

访问地址：`http://localhost:9000`

## 设备类型

| 图标 | 类型 | 默认 IP |
|------|------|---------|
| 📡 | 路由器 | 192.168.1.1 |
| 🔌 | 交换机 | 192.168.1.254 |
| 🔥 | 防火墙 | 192.168.0.1 |
| 🖥 | 服务器 | 192.168.1.10 |
| 💻 | PC | 192.168.1.100 |
| ☁️ | 云 | - |
| 📶 | WiFi AP | 192.168.1.200 |
| 📱 | 手机 | DHCP |
| 🌐 | 互联网 | - |

## 技术栈

- **前端**：Cytoscape.js 3.x、Cytoscape.js npm extensions
- **后端**：Python 3（Flask 风格自定义 HTTP 服务器）
- **终端**：xterm.js + Python PTY
- **AI**：MiniMax M2.5-highspeed（内置，无需外接服务）

## 目录结构

```
netops/
  index.html          # 主应用（单文件）
  server.py           # Python HTTP 服务器 + API
  start.sh            # 启动脚本
  stop.sh             # 停止脚本
  data/               # 项目数据（自动生成，包含 LLM 配置）
  icons/              # 设备图标
  cytoscape.min.js    # Cytoscape.js
  fontawesome.min.css # Font Awesome 图标库
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/` | 项目列表 |
| POST | `/api/projects/` | 创建项目 |
| GET | `/api/projects/{id}/topo` | 获取拓扑 |
| POST | `/api/projects/{id}/topo` | 保存拓扑 |
| POST | `/api/term/sessions` | 创建终端会话 |
| WS | `/api/term/ws/{session_id}` | 终端 WebSocket |
| POST | `/api/chat/send` | AI 对话（含拓扑上下文） |
