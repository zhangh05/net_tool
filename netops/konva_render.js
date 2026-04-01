/**
 * NetOps Topology Editor - Konva.js Rendering Layer
 * Replaces Cytoscape.js for canvas rendering and interaction
 * 
 * Architecture:
 *   Stage (canvas-wrap)
 *   ├── gridLayer  - Grid background
 *   ├── mainLayer  - Nodes + Edges
 *   └── uiLayer    - Selection box, connector dots
 */

'use strict';

// ============================================================
// Global State
// ============================================================
var stage, gridLayer, mainLayer, uiLayer;
var _selectedNodes = [];      // Currently selected Konva nodes
var _selectedEdges = [];      // Currently selected Konva edges
var _zoom = 1;
var _panOffset = {x: 0, y: 0};
var _gridSize = 48;           // Canvas grid cell size (px) - matches GRID_SIZE in index.html
var _snapToGrid = true;
var _edgeMode = 'bezier';     // 'bezier' | 'straight' | 'orthogonal'
var gridEnabled = false;

// Connector dots (connection anchors on nodes)
var _connectorDots = [];

// Shape/TextBox rendering support
var _shapeNodes = [];   // Additional shapes on canvas
var _textBoxNodes = [];

// Box selection state
var _boxSelecting = false;
var _boxStartPos = null;
var _selRect = null;

// Internal data store (mirrors Cytoscape's internal data)
var _topoData = {
    nodes: {},  // id -> { id, type, label, ip, desc, x, y, color, w, h, isShape, isTextBox, ... }
    edges: {},  // id -> { id, source, target, srcPort, tgtPort, edgeColor, edgeStyle, edgeWidth, bandwidth }
};

// ============================================================
// Device Colors
// ============================================================
var DEVICE_COLORS = {
    router:           {fill: '#1a2e4a', stroke: '#3b82f6'},
    router_advanced:  {fill: '#2e1a4a', stroke: '#8b5cf6'},
    router_core:      {fill: '#1a2e4a', stroke: '#6366f1'},
    switch:           {fill: '#1a2e1a', stroke: '#10b981'},
    switch_core:      {fill: '#1a2e4a', stroke: '#6366f1'},
    switch_access:    {fill: '#1a2e1a', stroke: '#10b981'},
    firewall:         {fill: '#2e2a1a', stroke: '#ef4444'},
    server:           {fill: '#2e1a1a', stroke: '#a78bfa'},
    pc:               {fill: '#1a1a2e', stroke: '#fbbf24'},
    cloud:            {fill: '#1a2e2e', stroke: '#06b6d4'},
    default:          {fill: '#1a2e2e', stroke: '#6b7280'},
};

// Default device sizes
var DEVICE_SIZES = {
    router:           {w: 120, h: 70},
    router_advanced:   {w: 120, h: 70},
    router_core:       {w: 120, h: 70},
    switch:           {w: 120, h: 70},
    switch_core:       {w: 120, h: 70},
    switch_access:     {w: 120, h: 70},
    firewall:          {w: 120, h: 70},
    server:            {w: 120, h: 70},
    pc:               {w: 120, h: 70},
    cloud:             {w: 120, h: 70},
};

// ============================================================
// Initialization
// ============================================================
function initKonvaCanvas() {
    var wrap = document.getElementById('canvasWrap');
    if (!wrap) {
        console.error('[Konva] canvasWrap not found');
        return;
    }

    var w = wrap.clientWidth || 800;
    var h = wrap.clientHeight || 600;

    // Create Konva Stage
    stage = new Konva.Stage({
        container: 'canvasWrap',
        width: w,
        height: h,
    });

    // Create layers
    gridLayer = new Konva.Layer();
    mainLayer = new Konva.Layer();
    uiLayer = new Konva.Layer();

    stage.add(gridLayer);
    stage.add(mainLayer);
    stage.add(uiLayer);

    // Draw initial grid
    drawGrid();

    // ---- Mouse wheel: zoom ----
    stage.on('wheel', function(e) {
        e.evt.preventDefault();
        var oldScale = stage.scaleX();
        var pointer = stage.getPointerPosition();
        if (!pointer) return;

        var mousePointTo = {
            x: (pointer.x - stage.x()) / oldScale,
            y: (pointer.y - stage.y()) / oldScale,
        };

        var direction = e.evt.deltaY > 0 ? -1 : 1;
        var scaleBy = 1.08;
        var newScale = direction > 0 ? oldScale * scaleBy : oldScale / scaleBy;
        newScale = Math.max(0.15, Math.min(4, newScale));

        stage.scale({x: newScale, y: newScale});
        stage.position({
            x: pointer.x - mousePointTo.x * newScale,
            y: pointer.y - mousePointTo.y * newScale,
        });

        _zoom = newScale;
        _panOffset = stage.position();
    });

    // ---- Click on empty canvas: deselect ----
    stage.on('click tap', function(e) {
        if (e.target === stage) {
            deselectAll();
        }
    });

    // ---- Double click: handle device placement or edit ----
    stage.on('dblclick dbltap', function(e) {
        if (e.target === stage) {
            // Double click on empty canvas — if a device type is selected, place it
            if (window.selectedDeviceType) {
                var pos = getStagePointerPosition();
                var x = pos.x, y = pos.y;
                if (gridEnabled) {
                    x = snapToGrid(x);
                    y = snapToGrid(y);
                }
                if (window.addNode) window.addNode(window.selectedDeviceType, x, y);
                window.selectedDeviceType = null;
                document.querySelectorAll('.palette-item').forEach(function(el) { el.classList.remove('selected'); });
                var mb = document.getElementById('modeBadge');
                if (mb) {
                    mb.classList.remove('visible');
                    var t = mb.querySelector('.mode-text');
                    if (t) t.textContent = '选择模式';
                }
            }
        }
    });

    // ---- Window resize ----
    window.addEventListener('resize', function() {
        if (!stage) return;
        var wrap = document.getElementById('canvasWrap');
        if (wrap) {
            stage.width(wrap.clientWidth);
            stage.height(wrap.clientHeight);
            stage.batchDraw();
        }
    });

    console.log('[Konva] Canvas initialized', w + 'x' + h);
}

// Get pointer position in world (untransformed) coordinates
function getStagePointerPosition() {
    var pointer = stage.getPointerPosition();
    if (!pointer) return {x: 0, y: 0};
    var scale = stage.scaleX();
    var pos = stage.position();
    return {
        x: (pointer.x - pos.x) / scale,
        y: (pointer.y - pos.y) / scale,
    };
}

// ============================================================
// Grid
// ============================================================
function drawGrid() {
    if (!gridLayer) return;
    gridLayer.destroyChildren();

    if (!gridEnabled) {
        gridLayer.batchDraw();
        return;
    }

    var w = stage.width();
    var h = stage.height();
    var scale = stage.scaleX();
    var pan = stage.position();

    // Calculate world coordinates of viewport corners
    var worldTL = screenToWorld(0, 0);
    var worldBR = screenToWorld(w, h);

    // Draw grid lines within viewport
    var gridSpacing = _gridSize;
    var ctx = gridLayer.getContext();
    ctx.save();

    // Transform for pan/zoom
    ctx.translate(pan.x, pan.y);
    ctx.scale(scale, scale);

    var startX = Math.floor(worldTL.x / gridSpacing) * gridSpacing;
    var startY = Math.floor(worldTL.y / gridSpacing) * gridSpacing;
    var endX = Math.ceil(worldBR.x / gridSpacing) * gridSpacing;
    var endY = Math.ceil(worldBR.y / gridSpacing) * gridSpacing;

    ctx.strokeStyle = '#94a3b8';
    ctx.lineWidth = 0.5 / scale;
    ctx.globalAlpha = 0.3;

    for (var x = startX; x <= endX; x += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(x, worldTL.y - gridSpacing);
        ctx.lineTo(x, worldBR.y + gridSpacing);
        ctx.stroke();
    }
    for (var y = startY; y <= endY; y += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(worldTL.x - gridSpacing, y);
        ctx.lineTo(worldBR.x + gridSpacing, y);
        ctx.stroke();
    }

    ctx.restore();
    gridLayer.batchDraw();
}

function toggleGrid() {
    gridEnabled = !gridEnabled;
    var btn = document.getElementById('btn-grid');
    var wrap = document.getElementById('canvasWrap');
    if (btn) {
        if (gridEnabled) btn.classList.add('active');
        else btn.classList.remove('active');
    }
    if (wrap) {
        if (gridEnabled) wrap.classList.add('grid-on');
        else wrap.classList.remove('grid-on');
    }
    drawGrid();
    if (gridEnabled) {
        if (window.toast) window.toast('✓ 网格吸附已开启');
    } else {
        if (window.toast) window.toast('ℹ 网格吸附已关闭');
    }
}

// Screen (pixel) to world (graph) coordinates
function screenToWorld(sx, sy) {
    var scale = stage.scaleX();
    var pan = stage.position();
    return {
        x: (sx - pan.x) / scale,
        y: (sy - pan.y) / scale,
    };
}

// World to screen coordinates
function worldToScreen(wx, wy) {
    var scale = stage.scaleX();
    var pan = stage.position();
    return {
        x: wx * scale + pan.x,
        y: wy * scale + pan.y,
    };
}

// ============================================================
// Node Rendering
// ============================================================
function renderNode(nodeData) {
    var type = nodeData.type || 'switch';
    var colors = DEVICE_COLORS[type] || DEVICE_COLORS.default;
    var size = DEVICE_SIZES[type] || DEVICE_SIZES.switch;
    var w = nodeData.w || size.w;
    var h = nodeData.h || size.h;
    var x = nodeData.x || 200;
    var y = nodeData.y || 200;

    var group = new Konva.Group({
        x: x,
        y: y,
        draggable: true,
        id: nodeData.id,
        name: 'device-node',
    });

    // Shadow rect (subtle depth effect)
    var shadow = new Konva.Rect({
        x: 3,
        y: 3,
        width: w,
        height: h,
        fill: 'rgba(0,0,0,0.15)',
        cornerRadius: 8,
    });
    group.add(shadow);

    // Background rect
    var rect = new Konva.Rect({
        width: w,
        height: h,
        fill: colors.fill,
        stroke: colors.stroke,
        strokeWidth: 2,
        cornerRadius: 8,
        name: 'bg-rect',
    });
    group.add(rect);

    // Left accent bar
    var accent = new Konva.Rect({
        x: 0,
        y: 0,
        width: 4,
        height: h,
        fill: colors.stroke,
        cornerRadius: [8, 0, 0, 8],
    });
    group.add(accent);

    // Type icon (using text-based icon)
    var iconText = getDeviceIconText(type);
    var icon = new Konva.Text({
        x: 0,
        y: 10,
        width: w,
        text: iconText,
        fontSize: 20,
        align: 'center',
        name: 'icon-text',
    });
    group.add(icon);

    // Label
    var labelText = nodeData.label || nodeData.id;
    var label = new Konva.Text({
        x: 0,
        y: 36,
        width: w,
        text: labelText,
        fontSize: 12,
        fill: '#e5e7eb',
        align: 'center',
        fontStyle: '600',
        name: 'label-text',
    });
    group.add(label);

    // IP text
    if (nodeData.ip) {
        var ipText = new Konva.Text({
            x: 0,
            y: 52,
            width: w,
            text: nodeData.ip,
            fontSize: 10,
            fill: '#8b949e',
            align: 'center',
            name: 'ip-text',
        });
        group.add(ipText);
    }

    // Store data on group
    group.setAttr('nodeData', nodeData);
    group.setAttr('bgRect', rect);
    group.setAttr('accentRect', accent);

    // ---- Drag events ----
    group.on('dragstart', function() {
        hideConnectorDots();
    });

    group.on('dragmove', function() {
        updateConnectorDots(nodeData.id);
    });

    group.on('dragend', function() {
        var pos = group.position();
        if (gridEnabled) {
            pos.x = snapToGrid(pos.x);
            pos.y = snapToGrid(pos.y);
            group.position(pos);
        }
        // Save position
        _saveNodePos(nodeData.id, pos.x, pos.y);
        // Re-render edges
        updateAllEdges();
        // Update connector dots
        updateConnectorDots(nodeData.id);
    });

    // ---- Click to select ----
    group.on('click tap', function(e) {
        e.cancelBubble = true;
        selectNode(nodeData.id);
    });

    // ---- Double click to edit ----
    group.on('dblclick dbltap', function(e) {
        e.cancelBubble = true;
        selectNode(nodeData.id);
        // Trigger property panel edit
        if (window.selectElement) {
            window.selectElement({ group: function() { return 'nodes'; }, id: function() { return nodeData.id; }, data: function(k) { return nodeData[k] || nodeData; } });
        }
        setTimeout(function() {
            var inp = document.getElementById('p-label');
            if (inp) { inp.focus(); inp.select(); }
        }, 60);
    });

    // ---- Hover effects ----
    group.on('mouseenter', function() {
        rect.strokeWidth(3);
        mainLayer.batchDraw();
        showConnectorDots(nodeData.id);
        stage.container().style.cursor = 'pointer';
    });

    group.on('mouseleave', function() {
        rect.strokeWidth(2);
        mainLayer.batchDraw();
        hideConnectorDots();
        stage.container().style.cursor = 'default';
    });

    mainLayer.add(group);

    // Store reference
    _topoData.nodes[nodeData.id] = nodeData;

    return group;
}

function getDeviceIconText(type) {
    var icons = {
        router:          '📡',
        router_advanced: '📡',
        router_core:     '📡',
        switch:          '🔃',
        switch_core:     '🔃',
        switch_access:   '🔃',
        firewall:        '🛡️',
        server:          '🖥️',
        pc:              '💻',
        cloud:           '☁️',
    };
    return icons[type] || '📦';
}

function _saveNodePos(id, x, y) {
    if (_topoData.nodes[id]) {
        _topoData.nodes[id].x = x;
        _topoData.nodes[id].y = y;
    }
    // Trigger autosave if available
    if (window.autoSaveProject) window.autoSaveProject();
}

function snapToGrid(val) {
    return Math.round(val / _gridSize) * _gridSize;
}

// ============================================================
// Shape Rendering (ellipse, rectangle)
// ============================================================
function renderShape(shapeData) {
    var w = shapeData.w || 120;
    var h = shapeData.h || 80;
    var x = shapeData.x || 200;
    var y = shapeData.y || 200;
    var color = shapeData.shapeColor || '#ef4444';
    var bg = shapeData.shapeBg;
    var label = shapeData.label || '';
    var fg = shapeData.shapeFg || '#1f2937';

    var group = new Konva.Group({
        x: x,
        y: y,
        draggable: true,
        id: shapeData.id,
        name: 'shape-node',
    });

    var shape;
    if (shapeData.type === 'ellipse') {
        shape = new Konva.Ellipse({
            radiusX: w / 2,
            radiusY: h / 2,
            fill: bg === 'transparent' ? 'transparent' : (bg || 'transparent'),
            stroke: color,
            strokeWidth: 3,
        });
    } else {
        shape = new Konva.Rect({
            width: w,
            height: h,
            fill: bg === 'transparent' ? 'transparent' : (bg || 'transparent'),
            stroke: color,
            strokeWidth: 3,
            cornerRadius: 4,
        });
    }
    group.add(shape);

    // Label inside shape
    var text = new Konva.Text({
        x: 0,
        y: h / 2 - 7,
        width: w,
        text: label,
        fontSize: 13,
        fill: fg,
        align: 'center',
        name: 'shape-label',
    });
    group.add(text);

    group.setAttr('nodeData', shapeData);

    group.on('dragend', function() {
        var pos = group.position();
        if (gridEnabled) {
            pos.x = snapToGrid(pos.x);
            pos.y = snapToGrid(pos.y);
            group.position(pos);
        }
        _topoData.nodes[shapeData.id].x = pos.x;
        _topoData.nodes[shapeData.id].y = pos.y;
    });

    group.on('click tap', function(e) {
        e.cancelBubble = true;
        selectNode(shapeData.id);
    });

    mainLayer.add(group);
    _topoData.nodes[shapeData.id] = shapeData;
    return group;
}

// ============================================================
// TextBox Rendering
// ============================================================
function renderTextBox(tbData) {
    var w = tbData.w || 160;
    var h = tbData.h || 60;
    var x = tbData.x || 200;
    var y = tbData.y || 200;
    var bg = tbData.tbBg || 'transparent';
    var fg = tbData.tbFg || '#1f2937';
    var label = tbData.label || '';

    var group = new Konva.Group({
        x: x,
        y: y,
        draggable: true,
        id: tbData.id,
        name: 'textbox-node',
    });

    var rect = new Konva.Rect({
        width: w,
        height: h,
        fill: bg === 'transparent' ? 'rgba(0,0,0,0.01)' : bg,
        cornerRadius: 4,
        stroke: '#374151',
        strokeWidth: 1,
    });
    group.add(rect);

    var text = new Konva.Text({
        x: 4,
        y: 4,
        width: w - 8,
        height: h - 8,
        text: label,
        fontSize: 13,
        fill: fg,
        name: 'tb-text',
    });
    group.add(text);

    group.setAttr('nodeData', tbData);

    group.on('dragend', function() {
        var pos = group.position();
        if (gridEnabled) {
            pos.x = snapToGrid(pos.x);
            pos.y = snapToGrid(pos.y);
            group.position(pos);
        }
        _topoData.nodes[tbData.id].x = pos.x;
        _topoData.nodes[tbData.id].y = pos.y;
    });

    group.on('click tap', function(e) {
        e.cancelBubble = true;
        selectNode(tbData.id);
    });

    mainLayer.add(group);
    _topoData.nodes[tbData.id] = tbData;
    return group;
}

// ============================================================
// Edge Rendering
// ============================================================
function renderEdge(edgeData) {
    var srcId = edgeData.source;
    var tgtId = edgeData.target;
    var srcNode = mainLayer.findOne('#' + srcId);
    var tgtNode = mainLayer.findOne('#' + tgtId);
    if (!srcNode || !tgtNode) return null;

    var sp = srcNode.position();
    var tp = tgtNode.position();
    var srcData = _topoData.nodes[srcId] || {};
    var tgtData = _topoData.nodes[tgtId] || {};
    var sw = srcData.w || 120;
    var sh = srcData.h || 70;
    var tw = tgtData.w || 120;
    var th = tgtData.h || 70;

    // Connection anchor: center of node
    var ax1 = sp.x + sw / 2;
    var ay1 = sp.y + sh / 2;
    var ax2 = tp.x + tw / 2;
    var ay2 = tp.y + th / 2;

    var color = edgeData.edgeColor || '#374151';
    var style = edgeData.edgeStyle || 'solid';
    var strokeW = edgeData.edgeWidth || 2;

    var line;
    var mode = _edgeMode || 'bezier';

    if (mode === 'straight') {
        line = new Konva.Line({
            points: [ax1, ay1, ax2, ay2],
            stroke: color,
            strokeWidth: strokeW,
            lineCap: 'round',
            lineJoin: 'round',
            dash: style === 'dashed' ? [10, 5] : undefined,
            id: edgeData.id,
            name: 'edge-line',
        });
    } else if (mode === 'orthogonal') {
        // L-shape or Z-shape depending on relative position
        var midX = (ax1 + ax2) / 2;
        line = new Konva.Line({
            points: [ax1, ay1, midX, ay1, midX, ay2, ax2, ay2],
            stroke: color,
            strokeWidth: strokeW,
            lineCap: 'round',
            lineJoin: 'round',
            dash: style === 'dashed' ? [10, 5] : undefined,
            id: edgeData.id,
            name: 'edge-line',
        });
    } else {
        // Bezier
        var dx = ax2 - ax1;
        var dy = ay2 - ay1;
        var tension = 0.3;
        line = new Konva.Line({
            points: [ax1, ay1, ax1 + dx * 0.5, ay1, ax2 - dx * 0.5, ay2, ax2, ay2],
            stroke: color,
            strokeWidth: strokeW,
            tension: tension,
            lineCap: 'round',
            bezier: true,
            dash: style === 'dashed' ? [10, 5] : undefined,
            id: edgeData.id,
            name: 'edge-line',
        });
    }

    // Edge click
    line.on('click tap', function(e) {
        e.cancelBubble = true;
        selectEdge(edgeData.id);
    });

    // Arrowhead (simple triangle at target end)
    var angle = Math.atan2(ay2 - ay1, ax2 - ax1);
    var arrowSize = 10;
    var arrow = new Konva.Arrow({
        points: [
            ax2 - Math.cos(angle) * (strokeW * 2 + 2),
            ay2 - Math.sin(angle) * (strokeW * 2 + 2),
            ax2, ay2
        ],
        stroke: color,
        strokeWidth: strokeW,
        fill: color,
        pointerLength: arrowSize,
        pointerWidth: arrowSize,
        name: 'edge-arrow',
    });

    // Z-order: edges below nodes
    mainLayer.add(line);
    mainLayer.add(arrow);
    line.moveToBottom();

    // Store references
    line.setAttr('edgeData', edgeData);
    line.setAttr('edgeArrow', arrow);
    arrow.setAttr('edgeData', edgeData);
    arrow.setAttr('edgeLine', line);

    _topoData.edges[edgeData.id] = edgeData;

    return line;
}

function updateAllEdges() {
    // Remove all existing edges and re-render
    mainLayer.find('.edge-line').forEach(function(n) { n.destroy(); });
    mainLayer.find('.edge-arrow').forEach(function(n) { n.destroy(); });

    Object.keys(_topoData.edges).forEach(function(id) {
        var e = _topoData.edges[id];
        if (e) renderEdge(e);
    });
    mainLayer.batchDraw();
}

// ============================================================
// Selection & Highlighting
// ============================================================
function showKonvaHighlight(konvaGroup) {
    var bg = konvaGroup.getAttr('bgRect');
    if (bg) {
        bg.strokeWidth(3);
        bg.stroke('#60a5fa');
    }
    var accent = konvaGroup.getAttr('accentRect');
    if (accent) {
        accent.fill('#60a5fa');
    }
    mainLayer.batchDraw();
}

function hideKonvaHighlight(konvaGroup) {
    var type = konvaGroup.getAttr('nodeData').type || 'switch';
    var colors = DEVICE_COLORS[type] || DEVICE_COLORS.default;
    var bg = konvaGroup.getAttr('bgRect');
    if (bg) {
        bg.strokeWidth(2);
        bg.stroke(colors.stroke);
    }
    var accent = konvaGroup.getAttr('accentRect');
    if (accent) {
        accent.fill(colors.stroke);
    }
    mainLayer.batchDraw();
}

function showKonvaEdgeHighlight(line, arrow) {
    line.strokeWidth(3);
    line.stroke('#60a5fa');
    arrow.stroke('#60a5fa');
    arrow.fill('#60a5fa');
    mainLayer.batchDraw();
}

function hideKonvaEdgeHighlight(line, arrow) {
    var ed = line.getAttr('edgeData') || {};
    var color = ed.edgeColor || '#374151';
    var w = ed.edgeWidth || 2;
    line.strokeWidth(w);
    line.stroke(color);
    arrow.stroke(color);
    arrow.fill(color);
    mainLayer.batchDraw();
}

function selectNode(id) {
    var konvaNode = mainLayer.findOne('#' + id);
    if (!konvaNode) return;

    // Deselect previous
    deselectAll();

    _selectedNodes = [konvaNode];
    showKonvaHighlight(konvaNode);

    // Show properties
    if (window.showProps) {
        var nodeData = _topoData.nodes[id] || {};
        var fakeEle = {
            group: function() { return 'nodes'; },
            id: function() { return id; },
            data: function(k) { return k ? nodeData[k] : nodeData; },
        };
        window.showProps(fakeEle);
    }

    window.editingId = id;
}

function selectEdge(id) {
    var line = mainLayer.findOne('#' + id);
    if (!line) return;

    deselectAll();

    var arrow = line.getAttr('edgeArrow');
    _selectedEdges = [line];
    showKonvaEdgeHighlight(line, arrow);

    if (window.showProps) {
        var edgeData = _topoData.edges[id] || {};
        var fakeEle = {
            group: function() { return 'edges'; },
            id: function() { return id; },
            data: function(k) { return k ? edgeData[k] : edgeData; },
            src: function() { return edgeData.source; },
            tgt: function() { return edgeData.target; },
        };
        window.showProps(fakeEle);
    }

    window.editingEdgeId = id;
}

function deselectAll() {
    _selectedNodes.forEach(function(n) { hideKonvaHighlight(n); });
    _selectedNodes = [];

    _selectedEdges.forEach(function(line) {
        var arrow = line.getAttr('edgeArrow');
        if (arrow) hideKonvaEdgeHighlight(line, arrow);
    });
    _selectedEdges = [];

    window.editingId = null;
    window.editingEdgeId = null;
}

// ============================================================
// Connector Dots
// ============================================================
function showConnectorDots(nodeId) {
    hideConnectorDots();
    var nodeGroup = mainLayer.findOne('#' + nodeId);
    if (!nodeGroup) return;

    var nodeData = _topoData.nodes[nodeId] || {};
    var pos = nodeGroup.position();
    var w = nodeData.w || 120;
    var h = nodeData.h || 70;

    var anchors = [
        {x: pos.x + w/2, y: pos.y, dir: 'top'},
        {x: pos.x + w, y: pos.y + h/2, dir: 'right'},
        {x: pos.x + w/2, y: pos.y + h, dir: 'bottom'},
        {x: pos.x, y: pos.y + h/2, dir: 'left'},
    ];

    anchors.forEach(function(a) {
        var dot = new Konva.Circle({
            x: a.x,
            y: a.y,
            radius: 6,
            fill: '#3b82f6',
            stroke: '#ffffff',
            strokeWidth: 2,
            name: 'connector-dot',
            draggable: true,
            id: 'dot-' + nodeId + '-' + a.dir,
        });

        dot.on('mouseenter', function() {
            dot.radius(9);
            dot.fill('#60a5fa');
            mainLayer.batchDraw();
            stage.container().style.cursor = 'crosshair';
        });

        dot.on('mouseleave', function() {
            dot.radius(6);
            dot.fill('#3b82f6');
            mainLayer.batchDraw();
            stage.container().style.cursor = 'pointer';
        });

        dot.on('dragend', function() {
            // TODO: handle edge drawing from connector
        });

        uiLayer.add(dot);
        _connectorDots.push(dot);
    });

    uiLayer.batchDraw();
}

function hideConnectorDots() {
    _connectorDots.forEach(function(d) { d.destroy(); });
    _connectorDots = [];
    uiLayer.batchDraw();
}

function updateConnectorDots(nodeId) {
    hideConnectorDots();
    showConnectorDots(nodeId);
}

// ============================================================
// Box Selection
// ============================================================
function startBoxSelect(sx, sy) {
    _boxSelecting = true;
    _boxStartPos = {x: sx, y: sy};

    _selRect = new Konva.Rect({
        x: sx,
        y: sy,
        width: 0,
        height: 0,
        stroke: '#2563eb',
        strokeWidth: 1.5,
        fill: 'rgba(37,99,235,0.1)',
        dash: [5, 3],
        name: 'sel-rect',
    });
    uiLayer.add(_selRect);
}

function updateBoxSelect(sx, sy) {
    if (!_boxSelecting || !_selRect) return;

    var x = Math.min(_boxStartPos.x, sx);
    var y = Math.min(_boxStartPos.y, sy);
    var w = Math.abs(sx - _boxStartPos.x);
    var h = Math.abs(sy - _boxStartPos.y);

    _selRect.setAttrs({x: x, y: y, width: w, height: h});
    uiLayer.batchDraw();
}

function finishBoxSelect() {
    if (!_boxSelecting || !_selRect) return;
    _boxSelecting = false;

    var rect = _selRect.getClientRect({});
    var scale = stage.scaleX();
    var pan = stage.position();

    // Convert to world coordinates
    var worldX = (rect.x - pan.x) / scale;
    var worldY = (rect.y - pan.y) / scale;
    var worldW = rect.width / scale;
    var worldH = rect.height / scale;

    // Find nodes within selection box
    deselectAll();
    mainLayer.find('.device-node, .shape-node, .textbox-node').forEach(function(group) {
        var pos = group.position();
        var nodeData = group.getAttr('nodeData') || {};
        var w = nodeData.w || 120;
        var h = nodeData.h || 70;

        var nodeCenterX = pos.x + w / 2;
        var nodeCenterY = pos.y + h / 2;

        if (nodeCenterX >= worldX && nodeCenterX <= worldX + worldW &&
            nodeCenterY >= worldY && nodeCenterY <= worldY + worldH) {
            _selectedNodes.push(group);
            showKonvaHighlight(group);
        }
    });

    if (_selectedNodes.length > 0 && window.showProps) {
        window.showProps({
            group: function() { return 'nodes'; },
            id: function() { return _selectedNodes[0].id(); },
            data: function(k) { return _selectedNodes[0].getAttr('nodeData')[k]; },
        });
        window.editingId = _selectedNodes[0].id();
    }

    _selRect.destroy();
    _selRect = null;
    uiLayer.batchDraw();
}

// ============================================================
// Public API: addNode
// ============================================================
window.addNode = function(type, x, y, extra) {
    extra = extra || {};
    var id = 'n' + Date.now() + Math.random().toString(36).substr(2, 5);

    // Save undo state before adding
    if (window.saveUndoState) window.saveUndoState();

    var nodeData = {
        id: id,
        type: type,
        label: extra.label || (window.getDeviceConfig ? window.getDeviceConfig(type).label : type) + '-' + (window.nodeCounter ? (window.nodeCounter[type] = (window.nodeCounter[type]||0)+1, window.nodeCounter[type]) : 1),
        ip: extra.ip || '',
        desc: extra.desc || '',
        x: x || 200,
        y: y || 200,
        color: '',
        w: 120,
        h: 70,
    };

    renderNode(nodeData);
    mainLayer.batchDraw();

    // Select newly added node
    selectNode(id);

    // Update connector dots
    showConnectorDots(id);

    // Log
    if (window.addOpLog) window.addOpLog('human', '添加设备：' + nodeData.label);

    return id;
};

// ============================================================
// Public API: deleteNode
// ============================================================
window.deleteNode = function(id) {
    var group = mainLayer.findOne('#' + id);
    if (group) {
        // Remove associated edges
        Object.keys(_topoData.edges).forEach(function(eid) {
            var e = _topoData.edges[eid];
            if (e && (e.source === id || e.target === id)) {
                deleteEdgeById(eid);
            }
        });

        delete _topoData.nodes[id];
        group.destroy();
        mainLayer.batchDraw();
    }
};

function deleteEdgeById(id) {
    var line = mainLayer.findOne('#' + id);
    if (line) {
        var arrow = line.getAttr('edgeArrow');
        if (arrow) arrow.destroy();
        line.destroy();
        delete _topoData.edges[id];
        mainLayer.batchDraw();
    }
}

// ============================================================
// Public API: addEdge
// ============================================================
window.addEdge = function(srcId, tgtId, extra) {
    extra = extra || {};
    var id = 'e' + Date.now() + Math.random().toString(36).substr(2, 5);

    var edgeData = {
        id: id,
        source: srcId,
        target: tgtId,
        srcPort: extra.srcPort || '',
        tgtPort: extra.tgtPort || '',
        bandwidth: extra.bandwidth || '',
        edgeColor: extra.edgeColor || '#374151',
        edgeStyle: extra.edgeStyle || 'solid',
        edgeWidth: extra.edgeWidth || 2,
    };

    renderEdge(edgeData);
    mainLayer.batchDraw();

    if (window.addOpLog) {
        var srcLabel = (_topoData.nodes[srcId] || {}).label || srcId;
        var tgtLabel = (_topoData.nodes[tgtId] || {}).label || tgtId;
        var portInfo = edgeData.srcPort || edgeData.tgtPort ? '（' + edgeData.srcPort + ' → ' + edgeData.tgtPort + '）' : '';
        window.addOpLog('human', '添加连线：' + srcLabel + ' → ' + tgtLabel + ' ' + portInfo);
    }

    return id;
};

// ============================================================
// Public API: getTopoData
// ============================================================
window.getTopoData = function() {
    var nodes = Object.keys(_topoData.nodes).map(function(id) {
        return Object.assign({}, _topoData.nodes[id]);
    });
    var edges = Object.keys(_topoData.edges).map(function(id) {
        return Object.assign({}, _topoData.edges[id]);
    });
    return {
        version: '3-konva',
        savedAt: new Date().toISOString(),
        nodes: nodes,
        edges: edges,
        counters: window.nodeCounter || {},
    };
};

// ============================================================
// Public API: loadTopoData
// ============================================================
window.loadTopoData = function(data) {
    loadTopoKonva(data);
};

function loadTopoKonva(data) {
    // Clear existing
    mainLayer.destroyChildren();
    _topoData.nodes = {};
    _topoData.edges = {};
    _selectedNodes = [];
    _selectedEdges = [];

    // Restore node counters
    if (data.counters) {
        window.nodeCounter = Object.assign({}, data.counters);
    }

    // Render nodes first
    (data.nodes || []).forEach(function(n) {
        if (n.isShape) {
            renderShape(n);
        } else if (n.isTextBox) {
            renderTextBox(n);
        } else {
            renderNode(n);
        }
    });

    // Render edges
    (data.edges || []).forEach(function(e) {
        renderEdge(e);
    });

    mainLayer.batchDraw();
    gridLayer.batchDraw();

    console.log('[Konva] Loaded', Object.keys(_topoData.nodes).length, 'nodes,', Object.keys(_topoData.edges).length, 'edges');
}

// ============================================================
// Public API: clearAll
// ============================================================
window.clearAll = function() {
    if (Object.keys(_topoData.nodes).length === 0) {
        if (window.toast) window.toast('拓扑已为空');
        return;
    }
    if (!confirm('确定清空所有设备？')) return;

    if (window.saveUndoState) window.saveUndoState();

    mainLayer.destroyChildren();
    _topoData.nodes = {};
    _topoData.edges = {};
    _selectedNodes = [];
    _selectedEdges = [];

    if (window.hideProps) window.hideProps();
    mainLayer.batchDraw();

    if (window.toast) window.toast('已清空（可 Ctrl+Z 撤销）');
    if (window.addOpLog) window.addOpLog('human', '清空画布（' + Object.keys(_topoData.nodes).length + '个设备）');
};

// ============================================================
// Public API: refreshCanvas
// ============================================================
window.refreshCanvas = function() {
    if (!stage) return;
    var wrap = document.getElementById('canvasWrap');
    if (wrap) {
        stage.width(wrap.clientWidth);
        stage.height(wrap.clientHeight);
    }
    drawGrid();
    mainLayer.batchDraw();
};

// ============================================================
// Zoom controls
// ============================================================
window.cyZoomIn = function() {
    var newScale = Math.min(4, _zoom * 1.25);
    var center = {x: stage.width()/2, y: stage.height()/2};
    var oldScale = _zoom;
    var mousePointTo = {
        x: (center.x - stage.x()) / oldScale,
        y: (center.y - stage.y()) / oldScale,
    };
    stage.scale({x: newScale, y: newScale});
    stage.position({
        x: center.x - mousePointTo.x * newScale,
        y: center.y - mousePointTo.y * newScale,
    });
    _zoom = newScale;
    _panOffset = stage.position();
    drawGrid();
};

window.cyZoomOut = function() {
    var newScale = Math.max(0.15, _zoom / 1.25);
    var center = {x: stage.width()/2, y: stage.height()/2};
    var oldScale = _zoom;
    var mousePointTo = {
        x: (center.x - stage.x()) / oldScale,
        y: (center.y - stage.y()) / oldScale,
    };
    stage.scale({x: newScale, y: newScale});
    stage.position({
        x: center.x - mousePointTo.x * newScale,
        y: center.y - mousePointTo.y * newScale,
    });
    _zoom = newScale;
    _panOffset = stage.position();
    drawGrid();
};

window.cyPan = function(dx, dy) {
    var p = stage.position();
    stage.position({x: p.x + dx, y: p.y + dy});
    _panOffset = stage.position();
    drawGrid();
};

window.cyZoom = function() { return _zoom; };
window.cyPanValue = function() { return stage ? stage.position() : {x:0,y:0}; };

// ============================================================
// Edge Mode
// ============================================================
window.setEdgeModeKonva = function(mode) {
    _edgeMode = mode;
    updateAllEdges();
};

// ============================================================
// Undo/Redo Support
// ============================================================
window._undoStack = [];
window._redoStack = [];

window.saveUndoState = function() {
    var snapshot = JSON.stringify(window.getTopoData());
    window._undoStack.push(snapshot);
    if (window._undoStack.length > 50) window._undoStack.shift();
    window._redoStack = [];
};

window.undoTopo = function() {
    if (window._undoStack.length < 2) {
        if (window.toast) window.toast('没有可撤销的操作');
        return;
    }
    window._redoStack.push(window._undoStack.pop());
    var state = window._undoStack[window._undoStack.length - 1];
    if (state) {
        var data = JSON.parse(state);
        window.loadTopoData(data);
    }
};

window.redoTopo = function() {
    if (window._redoStack.length === 0) {
        if (window.toast) window.toast('没有可重做的操作');
        return;
    }
    var state = window._redoStack.pop();
    window._undoStack.push(state);
    if (state) {
        var data = JSON.parse(state);
        window.loadTopoData(data);
    }
};

// ============================================================
// Update node property (for live property panel editing)
// ============================================================
window.updateNodeProperty = function(id, key, val) {
    var nodeData = _topoData.nodes[id];
    if (!nodeData) return;
    nodeData[key] = val;

    var group = mainLayer.findOne('#' + id);
    if (!group) return;

    if (key === 'label') {
        var labelText = group.findOne('.label-text');
        if (labelText) labelText.text(val);
    } else if (key === 'ip') {
        // Remove old ip text
        var oldIp = group.findOne('.ip-text');
        if (oldIp) oldIp.destroy();

        if (val) {
            var ipText = new Konva.Text({
                x: 0,
                y: 52,
                width: 120,
                text: val,
                fontSize: 10,
                fill: '#8b949e',
                align: 'center',
                name: 'ip-text',
            });
            // Insert before label-text
            var labelNode = group.findOne('.label-text');
            if (labelNode) ipText.zIndex(labelNode.zIndex() + 1);
            group.add(ipText);
        }
    }

    mainLayer.batchDraw();
};

window.updateEdgeProperty = function(id, key, val) {
    var edgeData = _topoData.edges[id];
    if (!edgeData) return;
    edgeData[key] = val;

    // Re-render the edge
    var oldLine = mainLayer.findOne('#' + id);
    if (oldLine) {
        var arrow = oldLine.getAttr('edgeArrow');
        deleteEdgeById(id);
        renderEdge(edgeData);
        mainLayer.batchDraw();
    }
};

// ============================================================
// Align nodes
// ============================================================
window.doAlign = function(type) {
    var nodes = _selectedNodes.length > 0 ? _selectedNodes : mainLayer.find('.device-node, .shape-node, .textbox-node').toArray();
    if (nodes.length < 2) {
        if (window.toast) window.toast('⚠ 至少需要2个设备才能对齐');
        return;
    }

    // Calculate bounding box
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    nodes.forEach(function(n) {
        var pos = n.position();
        var nd = n.getAttr('nodeData') || {};
        var w = nd.w || 120, h = nd.h || 70;
        minX = Math.min(minX, pos.x);
        maxX = Math.max(maxX, pos.x + w);
        minY = Math.min(minY, pos.y);
        maxY = Math.max(maxY, pos.y + h);
    });
    var midX = (minX + maxX) / 2;
    var midY = (minY + maxY) / 2;

    nodes.forEach(function(n) {
        var pos = n.position();
        var nd = n.getAttr('nodeData') || {};
        var w = nd.w || 120, h = nd.h || 70;
        var newPos;
        if (type === 'left') {
            newPos = {x: minX, y: pos.y};
        } else if (type === 'right') {
            newPos = {x: maxX - w, y: pos.y};
        } else if (type === 'hcenter') {
            newPos = {x: midX - w/2, y: pos.y};
        } else if (type === 'top') {
            newPos = {x: pos.x, y: minY};
        } else if (type === 'bottom') {
            newPos = {x: pos.x, y: maxY - h};
        } else if (type === 'vcenter') {
            newPos = {x: pos.x, y: midY - h/2};
        }
        if (newPos) {
            n.position(newPos);
            var id = n.id();
            _saveNodePos(id, newPos.x, newPos.y);
        }
    });

    updateAllEdges();
    mainLayer.batchDraw();

    if (window.saveUndoState) window.saveUndoState();
    if (window.autoSaveProject) window.autoSaveProject();
    if (window.toast) window.toast('✓ 对齐完成（' + nodes.length + '个）');
};

// ============================================================
// Context menu
// ============================================================
var _ctxNodeId = null;
var _ctxEdgeId = null;

window.showNodeContextMenu = function(nodeId, clientX, clientY) {
    _ctxNodeId = nodeId;
    _ctxEdgeId = null;
    var menu = document.getElementById('ctxMenu');
    if (!menu) return;
    // Show/hide items
    var editItem = document.getElementById('ctxEditItem');
    if (editItem) editItem.style.display = 'none';
    var delItem = document.getElementById('ctxDeleteItem');
    if (delItem) {
        delItem.innerHTML = '<i class="fa-solid fa-trash-alt" style="width:16px"></i> 删除';
    }
    menu.style.left = Math.min(clientX, window.innerWidth - 180) + 'px';
    menu.style.top = Math.min(clientY, window.innerHeight - 160) + 'px';
    menu.classList.add('visible');
};

window.showEdgeContextMenu = function(edgeId, clientX, clientY) {
    _ctxEdgeId = edgeId;
    _ctxNodeId = null;
    var menu = document.getElementById('ctxMenu');
    if (!menu) return;
    var editItem = document.getElementById('ctxEditItem');
    if (editItem) editItem.style.display = 'block';
    var delItem = document.getElementById('ctxDeleteItem');
    if (delItem) {
        delItem.innerHTML = '<i class="fa-solid fa-trash-alt" style="width:16px"></i> 删除';
    }
    menu.style.left = Math.min(clientX, window.innerWidth - 180) + 'px';
    menu.style.top = Math.min(clientY, window.innerHeight - 160) + 'px';
    menu.classList.add('visible');
};

window.ctxDelete = function() {
    var menu = document.getElementById('ctxMenu');
    if (menu) menu.classList.remove('visible');

    if (_ctxNodeId) {
        if (window.saveUndoState) window.saveUndoState();
        var id = _ctxNodeId;
        _ctxNodeId = null;
        window.deleteNode(id);
        if (window.hideProps) window.hideProps();
        if (window.toast) window.toast('已删除（可 Ctrl+Z 撤销）');
    } else if (_ctxEdgeId) {
        if (window.saveUndoState) window.saveUndoState();
        var eid = _ctxEdgeId;
        _ctxEdgeId = null;
        deleteEdgeById(eid);
        if (window.hideProps) window.hideProps();
        if (window.toast) window.toast('已删除连线');
    }
};

// ============================================================
// Canvas click / tap handler (for mode: connect)
// ============================================================
var _connectSource = null;

window.setMode = function(mode) {
    window.currentMode = mode;

    // Reset connect mode state
    if (_connectSource) {
        var oldGroup = mainLayer.findOne('#' + _connectSource);
        if (oldGroup) {
            var bg = oldGroup.getAttr('bgRect');
            var type = oldGroup.getAttr('nodeData').type || 'switch';
            var colors = DEVICE_COLORS[type] || DEVICE_COLORS.default;
            if (bg) { bg.stroke(colors.stroke); bg.strokeWidth(2); }
        }
        _connectSource = null;
    }

    // Update UI buttons
    document.querySelectorAll('.toolbar button').forEach(function(el) {
        el.classList.remove('active');
    });
    if (mode === 'select') {
        var btn = document.getElementById('btn-select');
        if (btn) btn.classList.add('active');
    } else if (mode === 'connect') {
        var btn = document.getElementById('btn-connect');
        if (btn) btn.classList.add('active');
        var badge = document.getElementById('modeBadge');
        if (badge) {
            badge.classList.add('visible');
            var t = badge.querySelector('.mode-text');
            if (t) t.textContent = '点第一个设备（源）';
        }
    }

    var badge = document.getElementById('modeBadge');
    if (badge && mode !== 'connect') badge.classList.remove('visible');
};

window.handleConnectTap = function(nodeId) {
    var nodeGroup = mainLayer.findOne('#' + nodeId);
    if (!nodeGroup) return;

    if (!window.currentMode || window.currentMode !== 'connect') return;

    if (!_connectSource) {
        _connectSource = nodeId;
        var bg = nodeGroup.getAttr('bgRect');
        if (bg) { bg.stroke('#3b82f6'); bg.strokeWidth(3); }
        mainLayer.batchDraw();
        var badge = document.getElementById('modeBadge');
        if (badge) {
            var t = badge.querySelector('.mode-text');
            if (t) t.textContent = '已选源设备，再点目标设备';
            badge.classList.add('visible');
        }
    } else {
        if (_connectSource !== nodeId) {
            window.addEdge(_connectSource, nodeId);
        }
        // Reset source
        var oldGroup = mainLayer.findOne('#' + _connectSource);
        if (oldGroup) {
            var bg = oldGroup.getAttr('bgRect');
            var type = oldGroup.getAttr('nodeData').type || 'switch';
            var colors = DEVICE_COLORS[type] || DEVICE_COLORS.default;
            if (bg) { bg.stroke(colors.stroke); bg.strokeWidth(2); }
        }
        _connectSource = null;
        mainLayer.batchDraw();
        var badge = document.getElementById('modeBadge');
        if (badge) {
            var t = badge.querySelector('.mode-text');
            if (t) t.textContent = '选择模式';
            badge.classList.remove('visible');
        }
        window.setMode && window.setMode('select');
    }
};

// ============================================================
// Shape placement
// ============================================================
window.startPlaceShape = function(shapeType, color) {
    color = color || '#ef4444';
    // In a full implementation, this would enter a placement mode
    // For now, place at center
    var wrap = document.getElementById('canvasWrap');
    var cx = wrap ? wrap.clientWidth / 2 : 400;
    var cy2 = wrap ? wrap.clientHeight / 2 : 300;
    var scale = stage.scaleX();
    var pan = stage.position();
    var wx = (cx - pan.x) / scale;
    var wy = (cy2 - pan.y) / scale;
    if (gridEnabled) {
        wx = snapToGrid(wx);
        wy = snapToGrid(wy);
    }

    var id = 's' + Date.now() + Math.random().toString(36).substr(2, 5);
    var shapeData = {
        id: id,
        type: shapeType,
        isShape: true,
        label: '',
        shapeColor: color,
        shapeBg: 'transparent',
        shapeFg: '#1f2937',
        w: 120,
        h: 80,
        x: wx,
        y: wy,
    };
    renderShape(shapeData);
    mainLayer.batchDraw();
    selectNode(id);
};

// ============================================================
// TextBox placement
// ============================================================
window.confirmTextBox = function() {
    var content = document.getElementById('tbContent').value.trim();
    if (!content) {
        if (window.toast) window.toast('请输入文字内容');
        return;
    }
    var bgColor = document.getElementById('tbBgColor').value || '#ffffff';
    var fgColor = document.getElementById('tbFgColor').value || '#1f2937';

    var wrap = document.getElementById('canvasWrap');
    var cx = wrap ? wrap.clientWidth / 2 : 400;
    var cy2 = wrap ? wrap.clientHeight / 2 : 300;
    var scale = stage.scaleX();
    var pan = stage.position();
    var wx = (cx - pan.x) / scale;
    var wy = (cy2 - pan.y) / scale;
    if (gridEnabled) {
        wx = snapToGrid(wx);
        wy = snapToGrid(wy);
    }

    var id = 't' + Date.now() + Math.random().toString(36).substr(2, 5);
    var tbData = {
        id: id,
        isTextBox: true,
        label: content,
        tbBg: bgColor === '#000000' ? 'transparent' : bgColor,
        tbFg: fgColor,
        w: 180,
        h: 60,
        x: wx,
        y: wy,
    };
    renderTextBox(tbData);
    mainLayer.batchDraw();
    selectNode(id);
    document.getElementById('textBoxDialog').style.display = 'none';
};

// ============================================================
// Quick add device (for palette click)
// ============================================================
window.quickAdd = function(type) {
    if (!stage) {
        if (window.toast) window.toast('画布加载中，请稍候');
        return;
    }
    var wrap = document.getElementById('canvasWrap');
    var cw = wrap ? wrap.clientWidth : 800;
    var ch = wrap ? wrap.clientHeight : 600;
    var scale = stage.scaleX();
    var pan = stage.position();
    var x = (cw / 2 - pan.x) / scale + (Math.random() - 0.5) * 60;
    var y = (ch / 2 - pan.y) / scale + (Math.random() - 0.5) * 60;
    if (gridEnabled) {
        x = snapToGrid(x);
        y = snapToGrid(y);
    }
    window.addNode(type, x, y);
};

// ============================================================
// Konva ready signal
// ============================================================
window.addEventListener('KonvaReady', function() {
    console.log('[Konva] Ready event fired');
});

// ============================================================
// Compatibility: expose cy-like interface for existing code
// ============================================================
window.__cy__ = {
    nodes: function(selector) { return _cyNodes(selector); },
    edges: function(selector) { return _cyEdges(selector); },
    elements: function() {
        var all = [];
        _cyNodes().forEach(function(n) { all.push(n); });
        _cyEdges().forEach(function(e) { all.push(e); });
        var els = {
            unselect: function() { deselectAll(); },
            remove: function() {
                mainLayer.destroyChildren();
                _topoData.nodes = {};
                _topoData.edges = {};
                _selectedNodes = [];
                _selectedEdges = [];
                mainLayer.batchDraw();
            },
            forEach: function(fn) { all.forEach(fn); },
            length: all.length,
            add: function() { return this; },
        };
        els.filter = function(fn) { return Array.prototype.filter.call(all, fn); };
        return els;
    },
    width: function() { return stage ? stage.width() : 800; },
    height: function() { return stage ? stage.height() : 600; },
    zoom: function(z) {
        if (z === undefined) return _zoom;
        return this;
    },
    pan: function(p) {
        if (p === undefined) return stage ? stage.position() : {x:0,y:0};
        if (stage) stage.position(p);
        return this;
    },
    center: function() {
        if (stage) {
            stage.position({x: 0, y: 0});
            stage.scale({x: 1, y: 1});
            _zoom = 1;
            _panOffset = {x: 0, y: 0};
        }
        return this;
    },
    resize: function() {
        if (stage) {
            var wrap = document.getElementById('canvasWrap');
            if (wrap) {
                stage.width(wrap.clientWidth);
                stage.height(wrap.clientHeight);
            }
        }
        return this;
    },
    container: function() { return document.getElementById('canvasWrap'); },
    json: function() { return window.getTopoData(); },
    userPanningEnabled: function(enabled) { canvasLocked = !enabled; },
    on: function(event, selector, handler) { /* Delegate to stage events */ },

    // Add method for AI ops (supports add nodes + edges)
    add: function(eles) {
        if (!Array.isArray(eles)) eles = [eles];
        eles.forEach(function(ele) {
            if (!ele) return;
            if (ele.group === 'nodes' || (ele.data && !ele.data.source && !ele.data.target)) {
                var d = ele.data || ele;
                if (d.isShape) {
                    renderShape(d);
                } else if (d.isTextBox) {
                    renderTextBox(d);
                } else {
                    var pos = ele.position || {};
                    var nodeData = {
                        id: d.id || ('n' + Date.now()),
                        type: d.type || 'switch',
                        label: d.label || d.id || '',
                        ip: d.ip || '',
                        desc: d.desc || '',
                        x: pos.x || 200,
                        y: pos.y || 200,
                        w: d.w || 120,
                        h: d.h || 70,
                    };
                    renderNode(nodeData);
                }
            } else if (ele.group === 'edges' || (ele.data && (ele.data.source || ele.data.target))) {
                var ed = ele.data || ele;
                var edgeData = {
                    id: ed.id || ('e' + Date.now()),
                    source: ed.source,
                    target: ed.target,
                    srcPort: ed.srcPort || '',
                    tgtPort: ed.tgtPort || '',
                    bandwidth: ed.bandwidth || '',
                    edgeColor: ed.edgeColor || '#374151',
                    edgeStyle: ed.edgeStyle || 'solid',
                    edgeWidth: ed.edgeWidth || 2,
                };
                renderEdge(edgeData);
            }
        });
        mainLayer.batchDraw();
        return this;
    },
};

// ============================================================
// Selector parsing helper (shared by shim methods)
// ============================================================
function _parseSelector(selector) {
    if (!selector || selector === '') return null;
    var m = selector.match(/^\[([a-zA-Z_]+)="([^"]+)"\]$/);
    if (m) return { attr: m[1], value: m[2] };
    return null;
}

function _cyNodes(selector) {
    var all = (mainLayer ? mainLayer.find('.device-node, .shape-node, .textbox-node').toArray() : []).map(function(n) { return makeCyNode(n); });

    if (!selector || selector === '') {
        var arr = all;
    } else if (selector === ':selected') {
        arr = _selectedNodes.map(function(n) { return makeCyNode(n); });
    } else {
        // Parse selector and filter
        var parsed = _parseSelector(selector);
        if (parsed) {
            arr = all.filter(function(n) {
                if (parsed.attr === 'id') return n.id() === parsed.value;
                if (parsed.attr === 'label') return n.data('label') === parsed.value;
                return false;
            });
        } else {
            arr = all;
        }
    }

    // Add array methods
    arr.filter = function(fn) { return Array.prototype.filter.call(arr, fn); };
    arr.forEach = function(fn) { return Array.prototype.forEach.call(arr, fn); };
    arr.map = function(fn) { return Array.prototype.map.call(arr, fn); };
    arr.some = function(fn) { return Array.prototype.some.call(arr, fn); };
    arr.every = function(fn) { return Array.prototype.every.call(arr, fn); };
    arr.reduce = function(fn, init) { return Array.prototype.reduce.call(arr, fn, init); };
    arr.find = function(fn) { return Array.prototype.find.call(arr, fn); };
    arr[Symbol.iterator] = function() { return arr.values(); };
    arr.select = function() { arr.forEach(function(n) { if (n.select) n.select(); }); };
    arr.unselect = function() { deselectAll(); };
    arr.remove = function() { arr.forEach(function(n) { if (n.remove) n.remove(); }); };
    return arr;
}

function _cyEdges(selector) {
    var all = Object.keys(_topoData.edges).map(function(id) { return makeCyEdge(id); });

    if (!selector || selector === '') {
        var arr = all;
    } else {
        var parsed = _parseSelector(selector);
        if (parsed) {
            if (parsed.attr === 'source') {
                arr = all.filter(function(e) { return e.source() === parsed.value; });
            } else if (parsed.attr === 'target') {
                arr = all.filter(function(e) { return e.target() === parsed.value; });
            } else {
                arr = all;
            }
        } else {
            arr = all;
        }
    }

    arr.filter = function(fn) { return Array.prototype.filter.call(arr, fn); };
    arr.forEach = function(fn) { return Array.prototype.forEach.call(arr, fn); };
    arr.map = function(fn) { return Array.prototype.map.call(arr, fn); };
    arr.some = function(fn) { return Array.prototype.some.call(arr, fn); };
    arr.every = function(fn) { return Array.prototype.every.call(arr, fn); };
    arr.reduce = function(fn, init) { return Array.prototype.reduce.call(arr, fn, init); };
    arr.find = function(fn) { return Array.prototype.find.call(arr, fn); };
    arr[Symbol.iterator] = function() { return arr.values(); };
    arr.unselect = function() { deselectAll(); };
    arr.remove = function() { arr.forEach(function(e) { if (e.remove) e.remove(); }); };
    return arr;
}
