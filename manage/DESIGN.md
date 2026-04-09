# Manage Design System

> 基于 VoltAgent awesome-design-md 规范格式
> 版本：1.0.0 | 更新：2026-04-09

---

## 1. Visual Theme & Atmosphere

**定位：** NOC 风格的 AI 协调平台，面向网络运维场景。

**氛围关键词：** 专业 · 冷静 · 高效 · 清晰

**视觉基调：**
- 浅色主调（浅灰蓝底 + 纯白面板），深色侧重点缀
- 主强调色：蓝/青（`#3b82f6` → `#06b6d4` 渐变方向）
- 界面密度：中等偏高，信息丰富但不拥挤
- 圆角：统一 `8px`（卡片）/`6px`（按钮）/`4px`（标签）

**参考风格：** Linear + Vercel Dashboard — 极简但信息密度高，精准的视觉层级

---

## 2. Color Palette & Roles

```css
/* ── 背景层 ── */
--bg-primary:    #f4f7fb;   /* 主背景：浅灰蓝 */
--bg-secondary:  #ffffff;    /* 面板/卡片背景：纯白 */
--bg-hover:      #eef2f8;   /* Hover 态 */
--bg-input:      #f8fafc;    /* 输入框背景 */
--bg-active:     #e8f4fe;   /* 选中/激活态（浅蓝）*/

/* ── 边框 ── */
--border:        #dde3ed;   /* 主边框 */
--border-light:  #e8ecf4;   /* 浅分隔线 */
--border-focus:  #3b82f6;   /* Focus 边框（蓝色）*/

/* ── 文字 ── */
--text-primary:  #1a2332;   /* 主文字：深蓝黑 */
--text-secondary:#5a677d;   /* 次要文字：灰蓝 */
--text-muted:    #9aa3b5;   /* 弱文字/提示 */

/* ── 强调色 ── */
--accent:        #3b82f6;   /* 主强调蓝 */
--accent-dim:    #1d4ed8;   /* 深蓝（hover 态）*/
--accent-light:  #eff6ff;   /* 浅蓝背景 */
--accent-glow:   rgba(59,130,246,0.15); /* 发光效果 */

/* ── 功能色 ── */
--success:       #10b981;   /* 成功：翠绿 */
--success-bg:    #d1fae5;   /* 成功背景 */
--warn:          #f59e0b;   /* 警告：琥珀 */
--warn-bg:       #fef3c7;   /* 警告背景 */
--danger:        #ef4444;   /* 危险：红 */
--danger-bg:     #fee2e2;   /* 危险背景 */
--purple:        #8b5cf6;   /* 紫色（用户气泡）*/
--purple-bg:     #ede9fe;   /* 紫色背景（Agent 图标）*/

/* ── 阴影色 ── */
--shadow-color:  rgba(0,0,0,0.08);
--shadow-lg:     rgba(0,0,0,0.12);

/* ── 特殊 ── */
--gradient-primary: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
--glass:         rgba(255,255,255,0.8);
```

### Agent 图标配色

| Agent | 背景色 | 边框色 | 文字色 |
|-------|--------|--------|--------|
| NetOps | `#dbeafe` | `#93c5fd` | `#3b82f6` |
| 阿网 | `#dcfce7` | `#86efac` | `#10b981` |
| 阿维 | `#fef9c3` | `#fde047` | `#f59e0b` |
| 阿研 | `#ede9fe` | `#c4b5fd` | `#8b5cf6` |

---

## 3. Typography Rules

**字体栈：**
```css
font-family: -apple-system, BlinkMacSystemFont,
            'Segoe UI', 'PingFang SC',
            'Microsoft YaHei', sans-serif;
```

**字号层级：**

| 用途 | 字号 | 字重 | 行高 | 颜色 |
|------|------|------|------|------|
| 页面标题 | 15px | 700 | - | `--text-primary` |
| 面板标题 | 10px | 600 | - | `--text-muted` (UPPCASE) |
| Agent 名称 | 13px | 500 | - | `--text-primary` |
| 正文/气泡 | 14px | 400 | 1.6 | `--text-primary` |
| 次要文字 | 13px | 400 | - | `--text-secondary` |
| 小标签 | 11px | 400 | - | `--text-muted` |
| 按钮文字 | 13px | 500 | - | 继承 |
| 输入框 | 14px | 400 | - | `--text-primary` |

**字重梯度：** 400（正文）/ 500（次要）/ 600（标签）/ 700（标题）

---

## 4. Component Stylings

### 按钮 `.hbtn`

```css
/* 基础 */
.hbtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
/* 默认 */
.hbtn {
  background: var(--bg-secondary);
  border-color: var(--border);
  color: var(--text-primary);
}
.hbtn:hover {
  background: var(--bg-hover);
  border-color: var(--border);
}
/* 主按钮（accent）*/
.hbtn-primary,
.hbtn-save {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.hbtn-primary:hover { background: var(--accent-dim); }
/* 危险按钮 */
.hbtn-danger {
  background: transparent;
  color: var(--danger);
  border-color: var(--danger);
}
.hbtn-danger:hover { background: var(--danger-bg); }
/* 幽灵按钮 */
.hbtn-goto {
  background: transparent;
  color: var(--accent);
  border-color: var(--accent);
}
.hbtn-goto:hover { background: var(--accent-light); }
/* 禁用 */
.hbtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
/* Processing（带加载动画）*/
.hbtn.processing {
  animation: pulse-accent 1.5s infinite;
}
```

### 卡片 `.agent-card`

```css
.agent-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
  border-left: 3px solid transparent;
}
.agent-card:hover {
  background: var(--bg-hover);
  box-shadow: inset 0 0 0 1px var(--border-light);
}
.agent-card.selected {
  background: var(--bg-active);
  border-left-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-glow);
}
```

### 气泡

```css
/* AI 气泡 */
.msg-ai {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 12px 12px 12px 4px;
  box-shadow: 0 1px 4px var(--shadow-color);
  padding: 10px 14px;
  max-width: 85%;
  margin-bottom: 8px;
}
/* 用户气泡 */
.msg-user {
  background: var(--purple);
  color: #fff;
  border-radius: 12px 12px 4px 12px;
  padding: 10px 14px;
  max-width: 75%;
  margin-left: auto;
  margin-bottom: 8px;
  box-shadow: 0 2px 8px rgba(139,92,246,0.25);
}
```

### 输入框

```css
.msg-input {
  background: var(--bg-input);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 14px;
  resize: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  outline: none;
}
.msg-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
  background: #fff;
}
```

### Flow Step

```css
.flow-step {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  background: var(--bg-hover);
  color: var(--text-muted);
  border: 1px solid var(--border-light);
  transition: all 0.2s ease;
}
/* 当前活跃 */
.flow-step.active {
  background: var(--accent-light);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-glow);
}
/* 已完成 */
.flow-step.done {
  background: var(--success-bg);
  color: var(--success);
  border-color: var(--success);
}
/* 失败 */
.flow-step.error {
  background: var(--danger-bg);
  color: var(--danger);
  border-color: var(--danger);
}
```

---

## 5. Layout Principles

**间距系统（基于 4px 网格）：**

| Token | 值 | 用途 |
|-------|-----|------|
| `--space-1` | 4px | 紧凑间距 |
| `--space-2` | 8px | 默认内边距 |
| `--space-3` | 12px | 卡片内间距 |
| `--space-4` | 16px | 面板内间距 |
| `--space-5` | 20px | section 间距 |
| `--space-6` | 24px | 大区块间距 |

**三栏布局：**

```
┌──────────┬────────────────────────────┬─────────────┐
│  220px   │         flex: 1           │   280px    │
│ LeftPanel│     Chat Workbench        │ RightPanel │
│ Agent列表│  Chat气泡 + 输入框         │ FlowTracker │
│          │                           │ Exec日志   │
└──────────┴────────────────────────────┴─────────────┘
```

**Header：** 52px 固定高度，`flex-shrink: 0`  
**Left Panel：** 固定 220px，`flex-shrink: 0`  
**Right Panel：** 固定 280px（可考虑改为可拖拽）  
**Chat Area：** `flex: 1`，`overflow-y: auto`

---

## 6. Depth & Elevation

**阴影层级：**

| 层级 | 用途 | 值 |
|------|------|-----|
| `shadow-sm` | 输入框 focus | `0 1px 3px rgba(0,0,0,0.08)` |
| `shadow` | 卡片/气泡 | `0 2px 12px rgba(0,0,0,0.08)` |
| `shadow-lg` | 浮层/弹窗 | `0 8px 32px rgba(0,0,0,0.12)` |
| `shadow-accent` | 激活态边框发光 | `0 0 0 3px rgba(59,130,246,0.15)` |

**Z-Index：**

| 值 | 用途 |
|-----|------|
| 1 | Header |
| 10 | 浮出面板（如 save-menu） |
| 100 | Toast 通知 |
| 1000 | Modal 弹窗 |

---

## 7. Do's and Don'ts

### Do
- ✅ 所有交互元素有 `hover`/`active`/`disabled` 态
- ✅ 颜色语义化：成功=绿、警告=黄、危险=红、强调=蓝
- ✅ 选中态用蓝色边框/背景区分，不要只靠加粗
- ✅ 动画过渡统一 `0.15s ease`，不用 linear
- ✅ 图标统一用 emoji 或 SVG，不混用
- ✅ 输入框 focus 态有蓝色 glow

### Don't
- ❌ 不要混用浅色和深色主题（保持浅色统一）
- ❌ 不要用纯黑色 `#000` 作为文字颜色
- ❌ 不要用 `!important` 覆盖组件样式
- ❌ 动画不要超过 `0.3s`（感觉卡顿）
- ❌ 不要改变 Header 高度（52px 固定）
- ❌ 不要改变三栏宽度比例（会影响布局）

---

## 8. Responsive Behavior

**断点：**

| 断点 | 行为 |
|------|------|
| `≥ 1280px` | 三栏完整显示 |
| `768px ~ 1279px` | Right Panel 隐藏（可折叠）|
| `< 768px` | Left + Right 均隐藏，仅 Chat 工作区 |

**移动端：**
- Header 压缩：隐藏文字，仅显示图标按钮
- 输入框：`position: fixed`，底部固定
- Chat 区域：全屏

**触控目标：** 最小 `44px × 44px`

---

## 9. Agent Prompt Guide

> 以下内容供 AI 阅读，在修改 UI 时遵循此规范。

### 修改 CSS 时
1. 优先修改 CSS 变量（`--variable-name`），不要硬编码色值
2. 新增组件样式必须包含：默认/hover/active/disabled 四态
3. 阴影统一用 `shadow` / `shadow-lg` / `shadow-sm`

### 新增 UI 组件时
1. 照此规范选择颜色（背景/边框/文字/强调）
2. 圆角统一 `6px`（小）/ `8px`（中）/ `12px`（气泡）
3. 必须定义 `transition: all 0.15s ease`

### 动画规范
- 使用 `ease` 而非 `linear`
- 时长：`hover`=0.15s，`展开`=0.2s，`出现`=0.25s
- 禁止超过 0.4s 的非必要动画

### 不要动的部分
- 核心 HTML 结构（`.app` / `.header` / `.left-panel` / `.workbench` / `.right-panel`）
- JavaScript 事件绑定（id/class 名不变）
- API 调用逻辑
- 功能逻辑（Agent调度、Chat、FlowTracker）
