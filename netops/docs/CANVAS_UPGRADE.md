# NetOps 画布升级方案

> 调研日期：2026-04-01
> 代码基准：index.html (7193行)
> 画布底层：Cytoscape.js

---

## 一、当前状态

### 1.1 已实现功能

| 功能 | 状态 | 代码位置 |
|------|------|----------|
| Cytoscape 画布初始化 | ✅ 完成 | 第 1778 行附近 |
| 节点渲染（SVG 背景图） | ✅ 完成 | `makeDeviceSVG()` 第 6091 行 |
| 形状渲染（椭圆/矩形/文本框） | ✅ 完成 | `makeShapeSVG()` 第 6095 行 |
| 节点拖拽（单选） | ✅ 完成 | Cytoscape 原生 |
| 多选节点拖拽 | ✅ 完成 | 第 3070 行 `_multiDragNodes` |
| 框选多选 | ✅ 完成（自定义实现） | 第 3098 行匿名 IIFE |
| 连线（带端口标签） | ✅ 完成 | `addEdge()` 第 2184 行 |
| 网格背景（CSS） | ✅ 完成 | `.grid-on` CSS 第 154 行 |
| 网格吸附 | ✅ 完成（逻辑层） | `snapToGrid()` 第 2279 行 |
| 网格切换按钮 | ✅ 完成 | `toggleGrid()` 第 2291 行 |
| 撤销/重做 | ✅ 完成（快照式） | 第 5758-5820 行 |
| 键盘快捷键 | ✅ 完成（部分） | 第 3160 行 keydown handler |
| 自动布局（COSE） | ✅ 完成 | `autoLayout()` 第 2908 行 |
| 左/右/顶/底/网格对齐 | ✅ 完成 | `doAlign()` 第 2288 行 |
| 保存/加载（项目） | ✅ 完成 | `saveTopology()` 第 3738 行 |
| JSON 导出/导入 | ✅ 完成 | `exportJSON()` 第 3765 行 |
| 形状面板（侧边） | ✅ 完成（编辑菜单） | `编辑 ▾` 菜单 |
| 属性面板 | ✅ 完成 | `showProps()` 第 2559 行附近 |
| 右键菜单 | ✅ 完成 | `ctxMenu` + `cxttap` |
| 节点缩放/旋转 | ✅ 完成（属性面板） | resizeHandle 拖拽 |
| 设备面板（侧边） | ✅ 完成（100px 窄） | `.palette` 第 80 行 |
| 云/AI 拓扑同步 | ✅ 完成 | `syncToAI()` 第 3859 行附近 |

### 1.2 现有 Cytoscape 配置要点

```javascript
cy = cytoscape({
  container: document.getElementById('canvasWrap'),  // 注意：用canvasWrap而非cyCanvas
  style: [
    selector: 'node' → 背景图=SVG data(icon), shape=roundrectangle, border-color=data(color)
    selector: 'edge' → curve-style=bezier, 带 source-label/target-label 端口显示
  ],
  layout: { name: 'preset' }
});
```

### 1.3 现有撤销栈实现

```javascript
var undoStack = [], redoStack = [], MAX_UNDO = 50;
// saveUndoState() 在每个 mutation 操作前调用（addNode/edge/drag等）
// isUndoRedo 标志位防止在 undo 中重复保存
// 快照格式：{ nodes: [...data+position], edges: [...data] }
```

---

## 二、缺失功能清单

| # | 功能 | 状态 | 优先级 | 实现难度 |
|---|------|------|--------|---------|
| 1 | 撤销/重做 | ✅ 已有 | - | - |
| 2 | 网格 + 吸附 | ✅ 部分完成 | - | - |
| 3 | 框选多选 | ✅ 已有 | - | - |
| 4 | 键盘快捷键 | ✅ 部分完成 | - | - |
| 5 | 连接点/连接桩（锚点） | ❌ 缺失 | P0 | 高 |
| 6 | 正交连线（直角） | ❌ 缺失 | P1 | 中 |
| 7 | 自动布局算法（一键排列） | ✅ 已有（COSE）| - | - |
| 8 | **复制粘贴节点** | ❌ 缺失 | P0 | 低 |
| 9 | **节点分组/图层** | ❌ 缺失 | P1 | 高 |
| 10 | **放大缩小滑块** | ❌ 缺失 | P1 | 低 |
| 11 | **鹰眼/小地图** | ❌ 缺失 | P2 | 中 |
| 12 | **侧边形状面板（节点库）** | ✅ 部分（编辑菜单）| P2 | 低 |
| 13 | **标尺辅助线** | ❌ 缺失 | P2 | 中 |
| 14 | **导出 PNG/SVG** | ❌ 缺失 | P1 | 低 |
| 15 | **跨浏览器复制粘贴** | ❌ 缺失 | P2 | 中 |
| 16 | **触摸支持（移动端）** | ❌ 缺失 | P2 | 高 |

### 详细说明

#### 连接点/连接桩（P0）
现有连线只能从节点中心出发。用户需要从节点的四边/四角（东/南/西/北/东北等）作为连接桩起点，使得连线更美观。需要实现：
- 每个节点渲染 4-8 个连接桩锚点（视觉上小圆点，hover 显示）
- 连线起点/终点记录 anchor 位置
- Cytoscape edge endpoint 设置

#### 正交连线（P1）
现有 bezier 曲线在复杂拓扑中会交叉混乱。需要：
- `curve-style: straight`（直线）或 `curve-style: segments`（折线）
- 优先实现直线作为快速方案，再考虑带拐点的正交路由

#### 复制粘贴节点（P0）
现有 Ctrl+C/V 无此功能。需要：
- Ctrl+C 序列化选中节点 + 其连线（保留相对坐标）
- Ctrl+V 在画布中央偏移 20px 粘贴
- 自动生成新 ID，避免冲突

#### 节点分组/图层（P1）
Cytoscape 支持 Compound Node（父子嵌套）可实现分组。方案：
- 允许选中多个节点后创建分组（包裹在父节点内）
- 图层面板控制 Z-index（`cy.nodes().move()`）
- 支持图层折叠/展开

#### 放大缩小滑块（P1）
现有只有鼠标滚轮缩放。需要：
- 工具栏添加 `[-][====○====][+]` 滑块
- `cy.zoom(val)` 控制，`cy.fit()` 适应画布
- 快捷键 `+`/`-` 缩放

#### 鹰眼/小地图（P2）
- 右下角小窗口显示整体拓扑缩略图
- 用第二个 Cytoscape 实例（只读）作为 minimap
- 拖拽小地图视口同步大画布 pan

#### 标尺辅助线（P2）
- 画布顶部/左侧显示像素刻度标尺
- 拖拽节点时显示对齐辅助线（红色虚线对齐其他节点）

#### 导出 PNG（P1）
Cytoscape 官方方案：
```javascript
cy.png({ output: 'blob', bg: '#f1f5f9', scale: 2 })
```
需要 toolbar 加按钮 + 下载触发

#### 触摸支持（P2）
- `touch-action: none` 处理手势冲突
- Cytoscape touch 事件兼容性处理（iOS/Android）

---

## 三、整合设计（阿网 + 阿维完成后）

### 3.1 网格系统和撤销栈共存

**现状问题**：
- `snapToGrid()` 在 `addNode`、鼠标 `tap`、拖拽 `dragfree` 中多处调用
- `saveUndoState()` 在 `addNode` 之前调用一次，但多节点拖拽时只保存一次

**整合方案**：
```
┌─────────────────────────────────────────┐
│  用户拖拽节点                            │
│    ↓                                     │
│  dragfree 事件                          │
│    ↓                                     │
│  统一保存撤销快照（单次）                 │
│    ↓                                     │
│  应用网格吸附（多处 → 统一为工具函数）     │
│    ↓                                     │
│  updateRenderedNode() 统一渲染           │
└─────────────────────────────────────────┘
```

关键改动：
1. 新增 `applyGridSnap(pos) → pos`，所有位置变更统一经过此函数
2. 拖拽结束后，**先**保存快照，**再**应用吸附（避免撤销时位置不对）
3. 阿维的网格背景 CSS class `.grid-on` 不变，与 `gridEnabled` 逻辑解耦

### 3.2 快捷键覆盖所有操作

**现有键盘 handler**（第 3160 行）：
```javascript
Delete/Backspace → 删除选中
Escape → 取消选择/退出放置
Ctrl+S → 保存
Ctrl+Z → 撤销
Ctrl+Y / Ctrl+Shift+Z → 重做
Ctrl+A → 全选
```

**补充快捷键**（按优先级）：
```
Ctrl+C          → 复制选中节点（新增）
Ctrl+V          → 粘贴（新增）
Ctrl+D          → 复制并偏移（新增）
Delete          → 删除（已有）
G               → 切换网格
L               → 触发自动布局
+/-             → 放大/缩小
0               → 重置缩放为 100%
Ctrl+G          → 创建分组（新增）
```

**注意事项**：
- 阿网在框选时会阻止 keydown 冒泡 → 需要在 `cy.on('tap')` 阶段判断是否在框选
- 快捷键 handler 应放在 Cytoscape 事件之后，避免冲突
- `e.target.tagName === 'INPUT'` 时跳过（已有）

### 3.3 工具栏布局调整

**现有布局问题**：
- 撤销/重做按钮和清空/AI按钮挤在一起
- 无缩放控制、无复制粘贴、无导出
- 编辑菜单是下拉式，操作繁琐

**建议新布局**：
```
[保存] [选择] [连线] [网格] | [对齐▾] [编辑▾] | [撤销][重做][缩放滑块] | [清空][导出▾][AI同步]
```

具体改动：
1. 新增 **导出** 下拉菜单：`导出PNG | 导出JSON | 导出SVG`
2. 撤销/重做按钮移到缩放滑块旁边
3. 新增缩放滑块：`[-][====●====][+]`
4. 网格按钮保留（已有 `toggleGrid`）

---

## 四、待开发功能优先级

### P0（阿网/阿维收尾 + 必须新增）

| 功能 | 负责人 | 实现方式 | 工作量 |
|------|--------|---------|--------|
| 阿网：**撤销栈完善**（多步操作合并、批量撤销） | 阿网 | 改进 `saveUndoState()`，批量操作合并为一步 | 小 |
| 阿网：**框选多选美化**（选框样式、选中高亮） | 阿网 | 改进 CSS `.selBox` 样式 | 小 |
| 阿维：**连接桩锚点** | 阿维 | 每个节点渲染 4-8 个小圆点，绑定 `cy.addSink` | 中 |
| 阿维：**网格吸附增强**（对齐辅助线） | 阿维 | drag 时检测附近节点，显示临时对齐线 | 中 |
| **新增：复制粘贴** | 阿维 | `copyNodes()` / `pasteNodes()` + Ctrl+C/V | 小 |

### P1（重要，下一迭代）

| 功能 | 实现方式 | 工作量 |
|------|---------|--------|
| 正交连线（直线优先） | `curve-style: straight`，按钮切换 | 小 |
| 缩放滑块 | toolbar 加 `<input type=range>`，`cy.zoom()` 绑定 | 小 |
| PNG 导出 | `cy.png({ output: 'blob', scale: 2 })` + 下载 | 小 |
| 节点分组（图层） | Cytoscape compound node，支持 `cy.nodes().parent()` | 中 |

### P2（可选，后续迭代）

| 功能 | 实现方式 | 工作量 |
|------|---------|--------|
| 鹰眼小地图 | 第二个只读 Cytoscape 实例 | 中 |
| 标尺辅助线 | canvas overlay + 事件监听 | 中 |
| 跨浏览器复制粘贴 | Clipboard API + localStorage 备份 | 中 |
| 触摸支持 | `touch-action`, pinch-to-zoom | 高 |
| 侧边形状面板展开 | 把编辑菜单改造为可折叠侧边栏 | 小 |

---

## 五、技术难点

### 难点 1：Cytoscape 容器选择冲突

**问题**：`cy = cytoscape({ container: document.getElementById('canvasWrap') })`  
`#canvasWrap` 同时是 `.canvas-wrap`（外层容器，有背景图）和 Cytoscape 挂载点。

**现状**：Cytoscape 3.x 内部 canvas 覆盖在 `.canvas-wrap` 之上，背景图通过 CSS 解决。

**风险**：minimap 或标尺需要叠加层时，`canvasWrap` 不能直接复用。

**方案**：
```javascript
// 保持现状，不改容器
// minimap 使用独立 container，位置: absolute, right: 10px, bottom: 10px
```

### 难点 2：网格切换时撤销栈不变

**问题**：打开/关闭网格不触发撤销，但会改变节点吸附行为。

**方案**：网格切换本身不保存撤销，但网格吸附后的拖拽位置变化需要正常保存撤销。

### 难点 3：Cytoscape 3.x vs 2.x 事件兼容性

**现状**：代码中有 `"manual collision for Cytoscape 3.x compatibility"` 注释（第 3098 行）。

**阿维连接桩**：Cytoscape 3.x 使用 `cy.edgehandles` 插件或自定义 `mousedown` 检测，**不要**依赖 2.x 的 `nsimple` 插件。

**推荐插件**：
- `cytoscape-popper` — 锚点/气泡定位
- 手写锚点 — 每个节点 4 个锚点 div，绝对定位，事件绑定

### 难点 4：大拓扑性能

**现状**：`autoLayout` 用 COSE（力导向），500+ 节点会卡顿。

**优化方案**：
- 节点 >200 时用 `preset` 布局（用户手动调整）
- 批量节点操作时用 `cy.batch()` 包裹
- SVG 渲染改为 Canvas 渲染（`renderer: { name: 'canvas' }`）— 实验性
- undoStack 每步最多存 50 步，50 步以上自动截断

### 难点 5：撤销栈与批量删除

**现状**：`deleteSelected()` 会正确调用 `saveUndoState()`（第 3154 行）。

**改进方向**：
- 批量删除时所有节点合并为一次撤销（当前已做到）
- 批量添加（AI 同步导入 50+ 节点）时，合并为一次撤销

---

## 六、整合检查清单

阿网 + 阿维开发完成后，主 Agent 验收检查：

```
□ 撤销/重做按钮响应 Ctrl+Z / Ctrl+Y
□ 网格开启后，新增节点自动吸附 48px
□ 网格开启后，拖拽节点结束后吸附到网格
□ 框选时拖出蓝色选框，松开选中框内节点
□ 选中多个节点后 Ctrl+C → Ctrl+V 粘贴出副本
□ 连线模式下点击两个节点弹出端口输入框
□ 连接桩锚点（小圆点）hover 时显示在节点四边
□ 导出 PNG 按钮生成带网格背景的 PNG 文件
□ 缩放滑块拖动时画布同步缩放
□ 鹰眼小地图显示在右下角，拖拽同步主画布
□ 所有新增功能不影响现有保存/加载
□ Ctrl+S 保存后刷新页面，数据完整恢复
```

---

## 七、参考资源

- [Cytoscape.js 官方文档](https://js.cytoscape.org/api/cytoscape/latest/)
- Cytoscape edge endpoints: `edge.sourceEndpoint()`, `edge.targetEndpoint()`
- Cytoscape compound nodes: `cy.add({ group: 'nodes', data: { parent: parentId } })`
- Cytoscape PNG export: `cy.png({ output: 'blob', scale: 2, bg: '#f1f5f9' })`
- Cytoscape minimap: 用第二个 `cy2 = cytoscape({ container: minimapDiv, ... })` + `cy.on('pan zoom', () => cy2.viewport(...))`
