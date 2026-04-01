# Konva.js 迁移 - 功能移植清单

> 调研时间：2026-04-01
> 背景：阿网做 Konva 核心渲染层，阿维做交互层。此文档做功能整合和遗留问题处理。

---

## 一、Cytoscape 版本关键函数清单

| 函数 | 位置（行） | 功能 | 迁移优先级 |
|------|-----------|------|---------|
| `addNode(type, x, y, extra)` | ~2151 | 添加设备节点 | P0 |
| `showProps(ele)` | ~2700 | 显示属性面板 | P0 |
| `upd(key, val)` | ~2920 | 更新节点属性 | P0 |
| `getTopologySummary()` | ~4594 | AI上下文拓扑摘要 | P0 |
| `saveTopology()` | ~3919 | 保存拓扑到服务器 | P0 |
| `loadTopology()` | ~3939 | 从服务器加载拓扑 | P0 |
| `addEdge(srcId, tgtId)` | ~2224 | 添加边并弹出端口配置 | P0 |
| `parseOpsFromText(text)` | ~4471 | 解析AI返回的[op]块 | P0 |
| `sendChat()` | ~4712 | 发送聊天消息 | P1 |
| `exportJSON()` / `importJSON()` | ~3960 | JSON导出/导入 | P1 |
| `importFromServer()` | ~4000 | 从服务器导入拓扑 | P1 |
| 终端抽屉（xterm.js） | ~6957 | SSH/Telnet终端 | P1 |
| 工具栏按钮 | ~1292 | 各种操作按钮 | P1 |
| `changeNodeType` | 无此函数 | 需新增节点类型切换 | P2 |
| 右键菜单 | ~contextmenu | 上下文菜单 | P2 |
| COSE自动布局 | 无 | 力导向布局算法 | P2 |

---

## 二、已迁移（阿网+阿维）

- [x] 节点渲染（Konva Group + SVG image）
- [x] 边渲染（Konva Line + 箭头）
- [x] 缩放/平移（Stage scale + position）
- [x] 拖拽（Konva draggable）
- [x] 网格背景
- [x] 吸附（snapToGrid）
- [x] 撤销/重做
- [x] 框选多选（Rubber band selection）
- [x] 键盘快捷键

---

## 三、待迁移

### P0（必须）

#### 1. 属性面板 ↔ Konva 节点联动

**现状（Cytoscape）：**
```javascript
// showProps(ele) 中：
const d = ele.data();           // cy.getElementById(id).data()
const id = d.id;
ele.data(key, val);             // 更新数据
```

**问题：** `showProps` 接收的是 Cytoscape Element 对象，Konva 需要从 `_nodeDataMap` 读取数据。

**解决方案：维护 `_nodeDataMap` 全局数据映射**

```javascript
// ── 全局数据映射（Konva 版本核心数据结构）───────────────────────────────
var _nodeDataMap = {};    // id -> { id, type, label, ip, desc, mac, port, bandwidth, color, w, h, ... }
var _edgeDataMap = {};    // id -> { id, source, target, srcPort, tgtPort, bandwidth, edgeColor, edgeStyle, edgeWidth }
var _currentSelectedId = null;   // 当前选中节点ID
var _currentSelectedEdgeId = null;  // 当前选中边ID

// ── showProps(id) - Konva 版本 ──────────────────────────────────────────
window.showProps = function(id) {
    // 支持传入字符串ID或Cytoscape兼容的Element对象
    if (typeof id !== 'string') {
        // 兼容旧调用：传入 Cytoscape Element 时提取ID
        id = id && id.id ? id.id() : (id.data ? id.data('id') : null);
        if (!id) return;
    }

    var empty = document.getElementById('propsEmpty');
    var content = document.getElementById('propsContent');
    if (!empty || !content) return;
    empty.style.display = 'none';
    content.style.display = 'block';

    var nodeData = _nodeDataMap[id];
    if (!nodeData) return;

    _currentSelectedId = id;
    _currentSelectedEdgeId = null;

    // 更新节点高亮（边框变蓝）
    highlightNode(id);
    clearEdgeHighlight();

    // 渲染设备属性面板（和原版相同HTML结构）
    var d = nodeData;
    content.innerHTML = `
      <div class="prop-group">
        <div class="prop-label">设备类型</div>
        <div style="font-size:13px;color:#d1d5db">
          <i class="fa-solid ${getDeviceConfig(d.type).icon}" style="color:${d.color}"></i>
          ${getDeviceConfig(d.type).label || d.type}
        </div>
      </div>
      <div class="prop-group">
        <div class="prop-label">名称</div>
        <input class="prop-input" id="p-label" value="${d.label}" oninput="updKonva('label',this.value)">
      </div>
      <div class="prop-group">
        <div class="prop-label">IP地址</div>
        <input class="prop-input" id="p-ip" value="${d.ip||''}" placeholder="如 192.168.1.1" oninput="updKonva('ip',this.value)">
      </div>
      <div class="prop-group">
        <div class="prop-label">描述</div>
        <input class="prop-input" id="p-desc" value="${d.desc||''}" placeholder="设备描述" oninput="updKonva('desc',this.value)">
      </div>
      <div class="prop-group">
        <button onclick="saveNodeProps()" style="width:100%;background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:10px;font-size:13px;font-weight:600;cursor:pointer">
          <i class="fa-solid fa-check"></i> 保存修改
        </button>
      </div>
    `;
};

// ── showPropsEdge(id) - 边属性面板 ─────────────────────────────────────
window.showPropsEdge = function(id) {
    if (typeof id !== 'string') {
        id = id && id.id ? id.id() : (id.data ? id.data('id') : null);
        if (!id) return;
    }

    var empty = document.getElementById('propsEmpty');
    var content = document.getElementById('propsContent');
    if (!empty || !content) return;
    empty.style.display = 'none';
    content.style.display = 'block';

    var edgeData = _edgeDataMap[id];
    if (!edgeData) return;

    _currentSelectedId = null;
    _currentSelectedEdgeId = id;

    clearNodeHighlight();
    highlightEdge(id);

    content.innerHTML = `
      <div class="prop-group">
        <div class="prop-label">连线</div>
        <div style="font-size:12px;color:#9ca3af">
          ${_nodeDataMap[edgeData.source] ? _nodeDataMap[edgeData.source].label : edgeData.source}
          →
          ${_nodeDataMap[edgeData.target] ? _nodeDataMap[edgeData.target].label : edgeData.target}
        </div>
      </div>
      <div class="prop-group">
        <div class="prop-label">带宽</div>
        <input class="prop-input" id="p-bandwidth" value="${edgeData.bandwidth||''}" placeholder="如 1Gbps" oninput="updEdgeKonva('bandwidth',this.value)">
      </div>
    `;
};
```

**`updKonva(key, val)` - 实时更新 Konva 节点：**

```javascript
// ── updKonva(key, val) - 实时更新节点属性 ──────────────────────────────
window.updKonva = function(key, val) {
    var id = _currentSelectedId;
    if (!id) return;

    // 1. 更新数据映射
    _nodeDataMap[id][key] = val;

    // 2. 更新 Konva 节点视觉
    var group = mainLayer.findOne('#' + id);
    if (!group) return;

    if (key === 'label') {
        // 重新生成 SVG 图标
        var d = _nodeDataMap[id];
        var devType = d.type || 'switch';
        var w = d.w || 80, h = d.h || 80;
        var color = d.color || '#3b82f6';
        var devConfig = window.getDeviceConfig ? window.getDeviceConfig(devType) : null;
        var iconUrl = devConfig ? '/icons/' + devConfig.icon : '/icons/switch.png';
        var svgUri = makeDeviceSVG(devType, color, w, h, val, iconUrl);

        // 找到 Konva Group 内的 Image 节点并更新
        var imgNode = group.findOne('Image');
        if (imgNode) {
            var imgObj = new Image();
            imgObj.onload = function() {
                imgNode.image(imgObj);
                mainLayer.batchDraw();
            };
            imgObj.src = svgUri;
        }

        // 更新标签文字
        var labelNode = group.findOne('Text');
        if (labelNode) {
            labelNode.text(val);
            mainLayer.batchDraw();
        }
    } else if (key === 'ip') {
        // IP 地址变化可以显示在副标签上
        // 可选：给 group 添加一个 IP 标签 Text 节点
    }
    // 其他属性类似处理

    mainLayer.batchDraw();
};

// ── updEdgeKonva(key, val) - 实时更新边属性 ───────────────────────────
window.updEdgeKonva = function(key, val) {
    var id = _currentSelectedEdgeId;
    if (!id) return;

    _edgeDataMap[id][key] = val;
    // 边属性变化（如带宽）可以在边上显示标签
    updateEdgeLabel(id);
    mainLayer.batchDraw();
};
```

**`highlightNode(id)` / `highlightEdge(id)` - 选中高亮：**

```javascript
// ── 节点/边选中高亮 ────────────────────────────────────────────────────
var _prevStroke = {};
var _prevStrokeEdge = {};

function highlightNode(id) {
    var group = mainLayer.findOne('#' + id);
    if (!group) return;
    var rect = group.findOne('Rect');
    if (rect) {
        _prevStroke[id] = rect.stroke();
        rect.stroke('#3b82f6');
        rect.strokeWidth(3);
        mainLayer.batchDraw();
    }
}

function clearNodeHighlight(id) {
    if (!id) return;
    var group = mainLayer.findOne('#' + id);
    if (!group) return;
    var rect = group.findOne('Rect');
    if (rect && _prevStroke[id] !== undefined) {
        rect.stroke(_prevStroke[id]);
        rect.strokeWidth(1);
        mainLayer.batchDraw();
    }
}

function highlightEdge(id) {
    var line = edgesLayer.findOne('#' + id);
    if (!line) return;
    _prevStrokeEdge[id] = line.stroke();
    line.stroke('#3b82f6');
    line.strokeWidth(4);
    edgesLayer.batchDraw();
}

function clearEdgeHighlight(id) {
    if (!id) return;
    var line = edgesLayer.findOne('#' + id);
    if (!line) return;
    if (_prevStrokeEdge[id] !== undefined) {
        line.stroke(_prevStrokeEdge[id]);
        line.strokeWidth(_edgeDataMap[id] ? _edgeDataMap[id].edgeWidth : 2);
        edgesLayer.batchDraw();
    }
}

function clearAllHighlights() {
    // 清除所有节点高亮
    Object.keys(_nodeDataMap).forEach(function(id) {
        clearNodeHighlight(id);
    });
    // 清除所有边高亮
    Object.keys(_edgeDataMap).forEach(function(id) {
        clearEdgeHighlight(id);
    });
}
```

---

#### 2. `getTopologySummary()` - 格式兼容

**现状：** 直接调用 `cy.nodes()`, `cy.edges()`，返回包含节点详细信息的 JSON。

**Konva 版本：**

```javascript
// ── getTopologySummary() - Konva 版本 ────────────────────────────────
function getTopologySummary() {
    if (topoMode === 'brief') {
        return {
            version: '1.3',
            deviceCount: Object.keys(_nodeDataMap).length,
            connectionCount: Object.keys(_edgeDataMap).length,
            nodes: [],
            edges: []
        };
    }

    // Build port usage map
    var nodePorts = {};
    Object.values(_edgeDataMap).forEach(function(e) {
        var src = e.source, tgt = e.target;
        var sp = e.srcPort, tp = e.tgtPort;
        if (!nodePorts[src]) nodePorts[src] = [];
        if (!nodePorts[tgt]) nodePorts[tgt] = [];
        if (sp) nodePorts[src].push(sp);
        if (tp) nodePorts[tgt].push(tp);
    });

    var PORT_CONVENTIONS = {
        router: ['GE0/0/0','GE0/0/1','GE0/0/2','GE0/0/3','GE0/1/0','GE0/1/1','ETH0','ETH1'],
        switch: ['GE0/0/1','GE0/0/2','GE0/0/3','GE0/0/4','GE0/0/5','GE0/0/6','GE0/0/7','GE0/0/8',
                 'GE0/0/9','GE0/0/10','GE0/0/11','GE0/0/12','GE0/0/13','GE0/0/14','GE0/0/15','GE0/0/16',
                 'GE0/0/17','GE0/0/18','GE0/0/19','GE0/0/20','GE0/0/21','GE0/0/22','GE0/0/23','GE0/0/24',
                 '10GE0/0/1','10GE0/0/2','10GE0/0/3','10GE0/0/4'],
        firewall: ['GE0/0/0','GE0/0/1','GE0/0/2','GE0/0/3','GE0/0/4','GE0/0/5','GE0/0/6','GE0/0/7'],
        server: ['ETH0','ETH1','ETH2','ETH3'],
        cloud: [],
        internet: []
    };

    var nodesList = Object.keys(_nodeDataMap).map(function(id) {
        var d = _nodeDataMap[id];
        var nType = d.type || 'switch';
        var used = nodePorts[id] || [];
        var allPorts = PORT_CONVENTIONS[nType] || PORT_CONVENTIONS.switch;
        var available = allPorts.filter(function(p) { return used.indexOf(p) < 0; });

        // 从 Konva 节点获取坐标
        var konvaNode = mainLayer.findOne('#' + id);
        var pos = konvaNode ? konvaNode.position() : { x: 200, y: 200 };

        return {
            id: id,
            type: nType,
            label: d.label,
            ip: d.ip || '',
            mac: d.mac || '',
            desc: d.desc || '',
            port: d.port || '',
            bandwidth: d.bandwidth || '',
            usedPorts: used,
            availablePorts: available,
            allPorts: allPorts,
            x: Math.round(pos.x),
            y: Math.round(pos.y),
        };
    });

    var edgesList = Object.keys(_edgeDataMap).map(function(id) {
        var e = _edgeDataMap[id];
        return {
            id: id,
            source: e.source,
            target: e.target,
            srcPort: e.srcPort || '',
            tgtPort: e.tgtPort || '',
            bandwidth: e.bandwidth || '',
        };
    });

    return {
        version: '1.3',
        deviceCount: nodesList.length,
        connectionCount: edgesList.length,
        portConventions: PORT_CONVENTIONS,
        nodes: nodesList,
        edges: edgesList,
    };
}
```

**`getTopoData()` - 完整拓扑数据（用于保存）：**

```javascript
// ── getTopoData() - 用于 JSON 导出/服务器保存 ─────────────────────────
function getTopoData() {
    var nodes = [];
    Object.keys(_nodeDataMap).forEach(function(id) {
        var d = _nodeDataMap[id];
        var konvaNode = mainLayer.findOne('#' + id);
        var pos = konvaNode ? konvaNode.position() : { x: 200, y: 200 };
        nodes.push({
            id: id,
            type: d.type || 'switch',
            label: d.label || id,
            ip: d.ip || '',
            desc: d.desc || '',
            mac: d.mac || '',
            port: d.port || '',
            bandwidth: d.bandwidth || '',
            color: d.color || '#3b82f6',
            w: d.w || 80,
            h: d.h || 80,
            x: pos.x,
            y: pos.y,
        });
    });

    var edges = Object.keys(_edgeDataMap).map(function(id) {
        var e = _edgeDataMap[id];
        return {
            id: id,
            source: e.source,
            target: e.target,
            srcPort: e.srcPort || '',
            tgtPort: e.tgtPort || '',
            bandwidth: e.bandwidth || '',
            edgeColor: e.edgeColor || '#64748b',
            edgeStyle: e.edgeStyle || 'solid',
            edgeWidth: e.edgeWidth || 2,
        };
    });

    return { nodes: nodes, edges: edges };
}
```

---

#### 3. AI Chat 集成 - `addNode`/`deleteNode` 兼容性

**现状：** AI 返回 `[op]` 块，`parseOpsFromText` 解析后调用 `addNode()` 和 `addEdge()`。

**方案：** `addNode` 和 `addEdge` 改为同时支持 Cytoscape 和 Konva，通过全局标志 `__konva_mode__` 切换。

```javascript
// ── 全局渲染引擎标志 ──────────────────────────────────────────────────
var __konva_mode__ = true;  // true=Konva, false=Cytoscape
var __cy__ = null;          // Cytoscape 实例（Konva模式下保留用于兼容性）

// ── addNode(type, x, y, extra) - 通用版本 ────────────────────────────
window.addNode = function(type, x, y, extra) {
    if (__konva_mode__) {
        return addNodeKonva(type, x, y, extra);
    } else {
        return addNodeCy(type, x, y, extra);
    }
};

// ── addNodeKonva - Konva 实现 ─────────────────────────────────────────
function addNodeKonva(type, x, y, extra) {
    var def = DEFAULTS[type];
    var d = getDeviceConfig(type);
    var id = 'n' + Date.now() + Math.random().toString(36).substr(2, 5);
    nodeCounter[type] = (nodeCounter[type] || 0) + 1;

    if (!isUndoRedo) saveUndoStateKonva();

    // 坐标吸附
    var pos = {
        x: gridEnabled ? snapToGrid(x || Math.random() * 500 + 150) : (x || Math.random() * 500 + 150),
        y: gridEnabled ? snapToGrid(y || Math.random() * 300 + 150) : (y || Math.random() * 300 + 150)
    };

    var nodeData = {
        id: id,
        type: type,
        label: extra.label || (def.desc + '-' + nodeCounter[type]),
        icon: '/icons/' + d.icon,
        color: d.color,
        w: d.w, h: d.h,
        ip: def.ip, desc: def.desc,
        mac: '', port: '', bandwidth: '',
        ...extra,
    };

    // 保存到数据映射
    _nodeDataMap[id] = nodeData;

    // 创建 Konva Group
    var group = renderNodeKonva(id, nodeData, pos);
    mainLayer.add(group);
    mainLayer.batchDraw();

    // 选中并显示属性
    _currentSelectedId = id;
    showProps(id);
    highlightNode(id);

    toast('✓ 已添加 ' + d.label);
    return id;
}

// ── renderNodeKonva(id, nodeData, pos) - 创建 Konva 节点 ───────────────
function renderNodeKonva(id, nodeData, pos) {
    var w = nodeData.w || 80;
    var h = nodeData.h || 80;
    var color = nodeData.color || '#3b82f6';

    var group = new Konva.Group({
        id: id,
        x: pos.x,
        y: pos.y,
        draggable: true,
        name: 'device-node',
    });

    // 背景矩形
    var rect = new Konva.Rect({
        width: w,
        height: h,
        fill: '#ffffff',
        stroke: '#cbd5e1',
        strokeWidth: 1,
        cornerRadius: 8,
        shadowColor: '#000',
        shadowBlur: 4,
        shadowOpacity: 0.1,
        shadowOffset: { x: 2, y: 2 },
    });
    group.add(rect);

    // SVG 图标（通过 Image 加载）
    var iconUrl = nodeData.icon || '/icons/switch.png';
    loadSVGToGroup(group, iconUrl, 0, 0, w, h * 0.6, nodeData.label, color);

    // 标签文字
    var labelText = new Konva.Text({
        text: nodeData.label || id,
        width: w,
        align: 'center',
        y: h - 20,
        fontSize: 11,
        fontStyle: 'bold',
        fill: '#374151',
    });
    group.add(labelText);

    // 拖拽事件
    group.on('dragend', function() {
        var p = group.position();
        if (gridEnabled) {
            group.position({ x: snapToGrid(p.x), y: snapToGrid(p.y) });
        }
        mainLayer.batchDraw();
        saveUndoStateKonva();
    });

    // 点击选中
    group.on('click', function(e) {
        e.cancelBubble = true;
        clearAllHighlights();
        highlightNode(id);
        showProps(id);
    });

    // 双击打开终端
    group.on('dblclick', function(e) {
        e.cancelBubble = true;
        var nd = _nodeDataMap[id];
        if (nd && nd.ip) {
            openNetopsSSH(nd.ip);
        }
    });

    return group;
}

// ── loadSVGToGroup - 异步加载SVG图标到Konva ────────────────────────────
function loadSVGToGroup(group, iconUrl, x, y, w, h, label, color) {
    var svgUrl = iconUrl;
    // 如果是PNG/JPG，用原URL；如果是相对路径，拼接完整路径
    var fullUrl = svgUrl.startsWith('http') ? svgUrl : (window.location.origin + svgUrl);

    var img = new Image();
    img.onload = function() {
        var imgNode = new Konva.Image({
            x: x + (w - 48) / 2,
            y: y + 8,
            width: 48,
            height: 48,
            image: img,
        });
        group.add(imgNode);
        group.getParent().batchDraw();
    };
    img.onerror = function() {
        // fallback: 画一个带颜色的圆角矩形占位
        var fallback = new Konva.Rect({
            x: x + (w - 48) / 2,
            y: y + 8,
            width: 48,
            height: 48,
            fill: color,
            cornerRadius: 8,
        });
        group.add(fallback);
        group.getParent().batchDraw();
    };
    img.src = fullUrl;
}

// ── addEdgeKonva - 添加边 ──────────────────────────────────────────────
window.addEdgeKonva = function(srcId, tgtId, srcPort, tgtPort, edgeOpts) {
    var id = 'e' + Date.now();
    var edgeData = {
        id: id,
        source: srcId,
        target: tgtId,
        srcPort: srcPort || '',
        tgtPort: tgtPort || '',
        bandwidth: '',
        edgeColor: edgeOpts && edgeOpts.edgeColor || pendingEdgeColor,
        edgeStyle: edgeOpts && edgeOpts.edgeStyle || pendingEdgeStyle,
        edgeWidth: edgeOpts && edgeOpts.edgeWidth || pendingEdgeWidth,
    };

    _edgeDataMap[id] = edgeData;
    renderEdgeKonva(id, edgeData);
    edgesLayer.batchDraw();
    return id;
};

// ── renderEdgeKonva(id, edgeData) - 渲染边 ─────────────────────────────
function renderEdgeKonva(id, edgeData) {
    var srcGroup = mainLayer.findOne('#' + edgeData.source);
    var tgtGroup = mainLayer.findOne('#' + edgeData.target);
    if (!srcGroup || !tgtGroup) return;

    var srcPos = getNodeConnectionPoint(srcGroup, tgtGroup.position());
    var tgtPos = getNodeConnectionPoint(tgtGroup, srcGroup.position());

    var points = [srcPos.x, srcPos.y, tgtPos.x, tgtPos.y];

    var line = new Konva.Line({
        id: id,
        points: points,
        stroke: edgeData.edgeColor || '#64748b',
        strokeWidth: edgeData.edgeWidth || 2,
        lineCap: 'round',
        lineJoin: 'round',
        dash: edgeData.edgeStyle === 'dashed' ? [10, 5] : [],
        hitStrokeWidth: 20,  // 扩大点击区域
    });

    // 点击选中边
    line.on('click', function(e) {
        e.cancelBubble = true;
        clearAllHighlights();
        highlightEdge(id);
        showPropsEdge(id);
    });

    edgesLayer.add(line);

    // 如果有标签，在中点显示文字
    if (edgeData.srcPort || edgeData.tgtPort) {
        var midX = (srcPos.x + tgtPos.x) / 2;
        var midY = (srcPos.y + tgtPos.y) / 2;
        var labelText = new Konva.Text({
            text: (edgeData.srcPort || '') + ' → ' + (edgeData.tgtPort || ''),
            x: midX - 40,
            y: midY - 8,
            fontSize: 10,
            fill: '#64748b',
        });
        labelText.id('label_' + id);
        edgesLayer.add(labelText);
    }
}

// ── getNodeConnectionPoint - 计算节点连接点 ────────────────────────────
function getNodeConnectionPoint(group, targetPos) {
    var pos = group.position();
    var w = group.width ? group.width() : 80;
    var h = group.height ? group.height() : 80;
    var cx = pos.x + w / 2;
    var cy = pos.y + h / 2;
    var angle = Math.atan2(targetPos.y - cy, targetPos.x - cx);
    // 返回边与矩形的交点
    var hw = w / 2, hh = h / 2;
    var tx = (hw * hh) / Math.sqrt(hh * hh * Math.cos(angle) * Math.cos(angle) + hw * hw * Math.sin(angle) * Math.sin(angle));
    var ty = (hh * hw) / Math.sqrt(hw * hw * Math.sin(angle) * Math.sin(angle) + hh * hh * Math.cos(angle) * Math.cos(angle));
    tx = Math.abs(tx) * Math.sign(Math.cos(angle));
    ty = Math.abs(ty) * Math.sign(Math.sin(angle));
    return { x: cx + tx, y: cy + ty };
}

// ── updateEdgePositions - 边的两端坐标随节点移动更新 ──────────────────
function updateEdgePositions() {
    Object.keys(_edgeDataMap).forEach(function(id) {
        var e = _edgeDataMap[id];
        var line = edgesLayer.findOne('#' + id);
        if (!line) return;
        var srcGroup = mainLayer.findOne('#' + e.source);
        var tgtGroup = mainLayer.findOne('#' + e.target);
        if (!srcGroup || !tgtGroup) return;
        var srcPos = getNodeConnectionPoint(srcGroup, tgtGroup.position());
        var tgtPos = getNodeConnectionPoint(tgtGroup, srcGroup.position());
        line.points([srcPos.x, srcPos.y, tgtPos.x, tgtPos.y]);

        // 更新标签位置
        var label = edgesLayer.findOne('#label_' + id);
        if (label) {
            label.position({ x: (srcPos.x + tgtPos.x) / 2 - 40, y: (srcPos.y + tgtPos.y) / 2 - 8 });
        }
    });
    edgesLayer.batchDraw();
}

// Hook: 节点拖拽时实时更新边的位置
// 在节点的 dragmove 事件中调用 updateEdgePositions()
```

---

### P1（重要）

#### 4. 终端抽屉 - 不受影响

终端抽屉完全独立于画布渲染引擎，使用 xterm.js + WebSocket。**无需修改。**

唯一注意：终端打开时使用的设备 IP 从 `_nodeDataMap[id].ip` 读取，而不是 `cy.getElementById(id).data('ip')`。

```javascript
// 修改终端相关函数，从 Konva 数据读取 IP
function openNetopsSSH(ip) {
    // 如果传入的是节点ID而非IP
    if (!ip.match(/\d+\.\d+\.\d+\.\d+/)) {
        var nodeData = _nodeDataMap[ip];
        ip = nodeData ? nodeData.ip : '';
    }
    _doOpenTermXterm('ssh', ip, 22, '', '');
}

function openNetopsTelnet(ip) {
    if (!ip.match(/\d+\.\d+\.\d+\.\d+/)) {
        var nodeData = _nodeDataMap[ip];
        ip = nodeData ? nodeData.ip : '';
    }
    _doOpenTermXterm('telnet', ip, 23, '', '');
}
```

#### 5. 工具栏按钮

工具栏按钮大多调用包装函数，这些函数内部使用 Cytoscape API。需要逐个检查：

| 按钮 | 调用的函数 | 修改方案 |
|------|-----------|---------|
| 保存 | `saveProject()` | 内部调用 `cy.json()` → 改为 `getTopoData()` |
| 选择模式 | `setMode('select')` | Konva 交互层处理，不依赖 cy |
| 连线模式 | `setMode('connect')` | Konva 交互层处理 |
| 网格 | `toggleGrid()` | 独立功能，不依赖 cy |
| 删除选中 | `deleteSelected()` | 需重写，从 `_currentSelectedId` 删除 |
| 全选 | `selectAll()` | 遍历 `_nodeDataMap` 批量高亮 |
| 复制粘贴 | `copySelected()` / `pasteSelected()` | 需重写 |
| 撤销/重做 | `undo()` / `redo()` | 阿维交互层已实现 |
| 导入/导出 | `importJSON()` / `exportJSON()` | 改为 `getTopoData()` |

**关键修改：`saveProject()` / `saveTopology()`**

```javascript
// saveTopology() - Konva 版本
function saveTopology() {
    autoSaveProject();
    updateProjectMeta();

    if (Object.keys(_nodeDataMap).length > 0 && currentProjectId) {
        var data = getTopoData();
        authFetch('/api/projects/' + encodeURIComponent(currentProjectId) + '/topo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(function(r) { return r.json(); }).then(function(d) {
            if (d && d.status === 'ok') toast('✓ 已保存到服务器');
        }).catch(function(e) { toast('❌ 服务器保存失败'); });
    }
}

// loadTopology() - Konva 版本
function loadTopology() {
    manageProjects();  // 打开项目管理对话框，让用户选择
}

// importFromServer() - Konva 版本
function importFromServer() {
    if (!currentProjectId) { toast('请先选择项目'); return; }
    fetch('/api/topo?projectId=' + encodeURIComponent(currentProjectId)).then(function(r) { return r.json(); }).then(function(topo) {
        if (!topo || (topo.nodes && topo.nodes.length === 0 && topo.edges && topo.edges.length === 0)) {
            toast('服务器暂无拓扑数据'); return;
        }
        // 清除当前 Konva 画布
        clearAllKonvaNodes();
        nodeCounter = {};

        if (topo.nodes) topo.nodes.forEach(function(n) {
            var _dc = getDeviceConfig(n.type);
            var nodeData = {
                id: n.id,
                type: n.type || 'switch',
                label: n.label || n.id,
                ip: n.ip || '',
                desc: n.desc || '',
                mac: n.mac || '',
                port: n.port || '',
                bandwidth: n.bandwidth || '',
                color: n.color || (_dc && _dc.color) || '#3b82f6',
                w: n.w || 80,
                h: n.h || 80,
            };
            _nodeDataMap[n.id] = nodeData;
            var pos = n.position || n;  // 兼容 n.x/n.y 和 {x,y} 两种格式
            var posObj = { x: pos.x || pos.x || 200, y: pos.y || pos.y || 200 };
            var group = renderNodeKonva(n.id, nodeData, posObj);
            mainLayer.add(group);
        });

        if (topo.edges) topo.edges.forEach(function(e) {
            _edgeDataMap[e.id] = {
                id: e.id,
                source: e.source,
                target: e.target,
                srcPort: e.srcPort || '',
                tgtPort: e.tgtPort || '',
                bandwidth: e.bandwidth || '',
                edgeColor: e.edgeColor || '#64748b',
                edgeStyle: e.edgeStyle || 'solid',
                edgeWidth: e.edgeWidth || 2,
            };
            renderEdgeKonva(e.id, _edgeDataMap[e.id]);
        });

        mainLayer.batchDraw();
        edgesLayer.batchDraw();
        toast('✓ 已从服务器加载（' + Object.keys(_nodeDataMap).length + '个设备）');
    }).catch(function() { toast('⚠ 加载失败'); });
}

// exportJSON() / importJSON()
function exportJSON() {
    if (Object.keys(_nodeDataMap).length === 0) { toast('拓扑为空'); return; }
    var data = {
        version: '1.1',
        exportedAt: new Date().toISOString(),
        nodes: Object.keys(_nodeDataMap).map(function(id) {
            var d = _nodeDataMap[id];
            var konvaNode = mainLayer.findOne('#' + id);
            var pos = konvaNode ? konvaNode.position() : { x: 200, y: 200 };
            return { ...d, x: pos.x, y: pos.y };
        }),
        edges: Object.keys(_edgeDataMap).map(function(id) {
            return { ..._edgeDataMap[id] };
        }),
        counters: nodeCounter,
    };
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'topology-' + new Date().toISOString().slice(0,10) + '.json';
    a.click();
    URL.revokeObjectURL(url);
    toast('✓ 已导出 JSON');
}

// deleteSelected()
function deleteSelected() {
    if (!isEditable()) return;
    if (_currentSelectedId) {
        deleteNodeKonva(_currentSelectedId);
        _currentSelectedId = null;
        hideProps();
    } else if (_currentSelectedEdgeId) {
        deleteEdgeKonva(_currentSelectedEdgeId);
        _currentSelectedEdgeId = null;
        hideProps();
    }
}

function deleteNodeKonva(id) {
    if (!isUndoRedo) saveUndoStateKonva();
    delete _nodeDataMap[id];
    var group = mainLayer.findOne('#' + id);
    if (group) group.destroy();
    // 删除关联的边
    Object.keys(_edgeDataMap).forEach(function(eid) {
        var e = _edgeDataMap[eid];
        if (e.source === id || e.target === id) {
            deleteEdgeKonva(eid);
        }
    });
    mainLayer.batchDraw();
    edgesLayer.batchDraw();
}

function deleteEdgeKonva(id) {
    if (!isUndoRedo) saveUndoStateKonva();
    delete _edgeDataMap[id];
    var line = edgesLayer.findOne('#' + id);
    if (line) line.destroy();
    var label = edgesLayer.findOne('#label_' + id);
    if (label) label.destroy();
    edgesLayer.batchDraw();
}

function clearAllKonvaNodes() {
    Object.keys(_nodeDataMap).forEach(function(id) {
        var group = mainLayer.findOne('#' + id);
        if (group) group.destroy();
    });
    Object.keys(_edgeDataMap).forEach(function(id) {
        var line = edgesLayer.findOne('#' + id);
        if (line) line.destroy();
    });
    _nodeDataMap = {};
    _edgeDataMap = {};
    mainLayer.batchDraw();
    edgesLayer.batchDraw();
}
```

#### 6. 节点类型切换

**现状：** 节点类型通过属性面板的设备类型下拉框选择，调用 `addNode` 重新创建节点。

**Konva 版本方案：**

```javascript
// changeNodeType(id, newType) - 切换节点类型
function changeNodeTypeKonva(id, newType) {
    var oldData = _nodeDataMap[id];
    if (!oldData) return;

    var d = getDeviceConfig(newType);
    var newData = {
        ...oldData,
        type: newType,
        color: d.color,
        w: d.w,
        h: d.h,
        icon: '/icons/' + d.icon,
    };

    _nodeDataMap[id] = newData;

    // 重新渲染节点
    var group = mainLayer.findOne('#' + id);
    if (group) {
        group.destroy();
    }

    var konvaNode = mainLayer.findOne('#' + id); // 应该不存在了
    var pos = group ? group.position() : { x: oldData.x || 200, y: oldData.y || 200 };
    var newGroup = renderNodeKonva(id, newData, pos);
    mainLayer.add(newGroup);

    // 更新关联边的位置
    updateEdgePositions();
    mainLayer.batchDraw();
    edgesLayer.batchDraw();

    // 刷新属性面板
    showProps(id);
}
```

---

### P2（可选）

#### 7. 右键菜单 - contextmenu

Konva 提供了 `stage.getContext()` 但没有原生 contextmenu 事件。方案：

```javascript
// 在 stage 上监听 contextmenu 事件
stage.on('contextmenu', function(e) {
    e.evt.preventDefault();
    // 显示自定义右键菜单
    var pos = stage.getPointerPosition();
    showContextMenu(pos.x, pos.y, e.target);
});

function showContextMenu(x, y, target) {
    // 复用现有 .context-menu div 或新建
    var menu = document.getElementById('context-menu') || createContextMenu();
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu.style.display = 'block';
    // 根据 target 类型显示不同菜单项
}
```

#### 8. 自动布局 - COSE 算法

Cytoscape 的 COSE 是力导向布局。Konva 没有内置，需自己实现：

```javascript
// 简易力导向布局（可后续扩展为 COSE）
function autoLayout() {
    var nodes = Object.keys(_nodeDataMap);
    if (nodes.length === 0) return;

    // 初始化位置（随机散布）
    nodes.forEach(function(id) {
        var group = mainLayer.findOne('#' + id);
        if (group) {
            group.position({
                x: Math.random() * 600 + 100,
                y: Math.random() * 400 + 100
            });
        }
    });

    // 迭代计算（Fruchterman-Reingold 简化版）
    var iterations = 50;
    var area = 800 * 600;
    var k = Math.sqrt(area / nodes.length);

    for (var iter = 0; iter < iterations; iter++) {
        var displacement = {};
        nodes.forEach(function(id) { displacement[id] = { x: 0, y: 0 }; });

        // 节点间斥力
        for (var i = 0; i < nodes.length; i++) {
            for (var j = i + 1; j < nodes.length; j++) {
                var n1 = nodes[i], n2 = nodes[j];
                var g1 = mainLayer.findOne('#' + n1);
                var g2 = mainLayer.findOne('#' + n2);
                if (!g1 || !g2) continue;
                var p1 = g1.position(), p2 = g2.position();
                var dx = p2.x - p1.x, dy = p2.y - p1.y;
                var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                var force = (k * k) / dist;
                displacement[n1].x -= (dx / dist) * force;
                displacement[n1].y -= (dy / dist) * force;
                displacement[n2].x += (dx / dist) * force;
                displacement[n2].y += (dy / dist) * force;
            }
        }

        // 边弹簧引力
        Object.keys(_edgeDataMap).forEach(function(eid) {
            var e = _edgeDataMap[eid];
            var g1 = mainLayer.findOne('#' + e.source);
            var g2 = mainLayer.findOne('#' + e.target);
            if (!g1 || !g2) return;
            var p1 = g1.position(), p2 = g2.position();
            var dx = p2.x - p1.x, dy = p2.y - p1.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 1;
            var force = (dist * dist) / k;
            displacement[e.source].x += (dx / dist) * force * 0.1;
            displacement[e.source].y += (dy / dist) * force * 0.1;
            displacement[e.target].x -= (dx / dist) * force * 0.1;
            displacement[e.target].y -= (dy / dist) * force * 0.1;
        });

        // 应用位移
        var temp = 20 * (1 - iter / iterations);  // 温度递减
        nodes.forEach(function(id) {
            var group = mainLayer.findOne('#' + id);
            if (!group) return;
            var p = group.position();
            var dx = displacement[id].x, dy = displacement[id].y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 1;
            var limited = Math.min(dist, temp) / dist;
            group.position({
                x: p.x + dx * limited,
                y: p.y + dy * limited,
            });
        });
    }

    updateEdgePositions();
    mainLayer.batchDraw();
    edgesLayer.batchDraw();
    toast('✓ 已完成自动布局');
}
```

---

## 四、撤销/重做数据层适配

Cytoscape 版本的 `saveUndoState()` 存储 `cy.json()`。Konva 版本需要存储自己的数据快照：

```javascript
var _undoStack = [];
var _redoStack = [];
var MAX_UNDO = 50;

function saveUndoStateKonva() {
    var snapshot = {
        nodes: JSON.parse(JSON.stringify(_nodeDataMap)),
        edges: JSON.parse(JSON.stringify(_edgeDataMap)),
        positions: {},
    };
    Object.keys(_nodeDataMap).forEach(function(id) {
        var g = mainLayer.findOne('#' + id);
        if (g) snapshot.positions[id] = g.position();
    });
    _undoStack.push(snapshot);
    if (_undoStack.length > MAX_UNDO) _undoStack.shift();
    _redoStack = [];
}

function undoKonva() {
    if (_undoStack.length < 2) return;
    var current = _undoStack.pop();
    _redoStack.push(current);
    var prev = _undoStack[_undoStack.length - 1];
    restoreSnapshot(prev);
}

function redoKonva() {
    if (_redoStack.length === 0) return;
    var next = _redoStack.pop();
    _undoStack.push(next);
    restoreSnapshot(next);
}

function restoreSnapshot(snap) {
    clearAllKonvaNodes();
    _nodeDataMap = JSON.parse(JSON.stringify(snap.nodes));
    _edgeDataMap = JSON.parse(JSON.stringify(snap.edges));

    Object.keys(_nodeDataMap).forEach(function(id) {
        var d = _nodeDataMap[id];
        var pos = snap.positions[id] || { x: d.x || 200, y: d.y || 200 };
        var group = renderNodeKonva(id, d, pos);
        mainLayer.add(group);
    });
    Object.keys(_edgeDataMap).forEach(function(id) {
        renderEdgeKonva(id, _edgeDataMap[id]);
    });

    mainLayer.batchDraw();
    edgesLayer.batchDraw();
}
```

---

## 五、切换策略

### 方案A：单文件双引擎（推荐）
在 `index.html` 中用 `__konva_mode__` 全局标志切换，`addNode` 等核心函数自动路由到对应引擎。保持文件统一，方便调试。

### 方案B：独立 Konva 文件
创建 `index_konva.html`，与原文件完全独立。切换时只需修改入口 URL。

---

## 六、验证检查清单

| # | 功能 | 验证方法 |
|---|------|---------|
| 1 | 属性面板显示正确 | 添加节点后点击，检查面板显示label/ip/desc |
| 2 | 属性修改实时生效 | 修改名称输入框，Konva节点文字同步更新 |
| 3 | 保存/加载拓扑 | 保存后刷新页面，加载，节点数量和位置一致 |
| 4 | JSON导出/导入 | 导出JSON，检查格式；再导入，数据完整 |
| 5 | AI Chat 添加节点 | 发送"添加一台路由器"，验证节点出现在画布 |
| 6 | AI Chat 删除节点 | 发送"删除R1"，验证节点消失 |
| 7 | AI Chat 连线 | 发送"连接R1和R2"，验证边出现 |
| 8 | 终端抽屉打开 | 双击节点，验证终端以该IP打开 |
| 9 | 节点拖拽后边跟随 | 拖动节点，验证连接的边同步更新 |
| 10 | 撤销/重做 | 添加节点后撤销，节点消失；重做，节点恢复 |
| 11 | 从服务器加载 | 选择项目后从服务器导入，验证拓扑完整 |
| 12 | 节点类型切换 | 在属性面板切换设备类型，验证图标/颜色变化 |

---

## 七、实现优先级排序

```
第一阶段（P0核心打通）：
  1. _nodeDataMap / _edgeDataMap 数据结构
  2. addNodeKonva() / deleteNodeKonva()
  3. renderNodeKonva() / renderEdgeKonva()
  4. showProps() / updKonva() 打通属性面板
  5. getTopologySummary() 打通 AI Chat

第二阶段（P1功能对齐）：
  6. saveTopology() / loadTopology() / importFromServer()
  7. 工具栏按钮（删除、复制粘贴等）
  8. 节点类型切换
  9. 撤销/重做数据层适配
  10. updateEdgePositions() 边跟随节点移动

第三阶段（P2增强）：
  11. 右键菜单
  12. 自动布局
  13. 框选删除（batch delete）
```
