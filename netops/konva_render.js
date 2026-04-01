/**
 * Konva.js rendering layer for NetOps topology editor
 * Coexists alongside Cytoscape.js - does NOT replace it
 */

// Global Konva stage and layers
var stage = null;
var gridLayer = null;
var mainLayer = null;
var uiLayer = null;

// Device type colors and icons
var DEVICE_COLORS = {
  router:   '#60a5fa',
  switch:   '#34d399',
  firewall: '#f87171',
  server:   '#a78bfa',
  pc:       '#fbbf24',
  cloud:    '#67e8f9'
};

var DEVICE_ICONS = {
  router:   '📡',
  switch:   '🔌',
  firewall: '🔥',
  server:   '🖥',
  pc:       '💻',
  cloud:    '☁️'
};

var GRID_SIZE = 48;
var MIN_SCALE = 0.15;
var MAX_SCALE = 4;

/**
 * Initialize Konva Stage inside #canvasWrap div
 * Creates gridLayer, mainLayer, uiLayer
 */
function initKonvaCanvas() {
  var container = document.getElementById('canvasWrap');
  if (!container) {
    console.error('[Konva] #canvasWrap not found');
    return;
  }

  // Create stage with same dimensions as container
  stage = new Konva.Stage({
    container: container,
    width: container.offsetWidth || 800,
    height: container.offsetHeight || 600
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

  // Zoom via wheel
  stage.on('wheel', function(e) {
    e.evt.preventDefault();
    var oldScale = stage.scaleX();
    var pointer = stage.getPointerPosition();
    var mousePointTo = {
      x: (pointer.x - stage.x()) / oldScale,
      y: (pointer.y - stage.y()) / oldScale
    };
    var direction = e.evt.deltaY > 0 ? -1 : 1;
    var newScale = direction > 0 ? oldScale * 1.1 : oldScale / 1.1;
    newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
    stage.scale({ x: newScale, y: newScale });
    stage.position({
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale
    });
  });

  // Pan via drag on empty space
  stage.on('dragmove', function(e) {
    // Only pan if dragging the stage itself (not a shape)
  });

  // Enable stage dragging for panning
  stage.draggable(true);
  stage.on('dragend', function() {
    // Pan complete
  });

  console.log('[Konva] initialized, stage:', stage);
}

/**
 * Draw 48px grid dots on gridLayer
 */
function drawGrid() {
  if (!gridLayer || !stage) return;

  gridLayer.destroyChildren();

  var width = stage.width();
  var height = stage.height();
  var scale = stage.scaleX();
  var stagePos = stage.position();

  // Calculate visible area in canvas coordinates
  var startX = Math.floor(-stagePos.x / scale / GRID_SIZE) * GRID_SIZE - GRID_SIZE;
  var startY = Math.floor(-stagePos.y / scale / GRID_SIZE) * GRID_SIZE - GRID_SIZE;
  var endX = startX + Math.ceil(width / scale / GRID_SIZE + 2) * GRID_SIZE;
  var endY = startY + Math.ceil(height / scale / GRID_SIZE + 2) * GRID_SIZE;

  for (var x = startX; x <= endX; x += GRID_SIZE) {
    for (var y = startY; y <= endY; y += GRID_SIZE) {
      var dot = new Konva.Circle({
        x: x,
        y: y,
        radius: 1.5,
        fill: '#9ca3af',
        listening: false
      });
      gridLayer.add(dot);
    }
  }

  gridLayer.batchDraw();
}

/**
 * Render a device node as Konva Group
 * @param {Object} nodeData - { id, type, label, x, y }
 * @returns {Konva.Group}
 */
function renderNode(nodeData) {
  var type = nodeData.type || 'server';
  var color = DEVICE_COLORS[type] || '#a78bfa';
  var icon = DEVICE_ICONS[type] || '🖥';
  var label = nodeData.label || nodeData.id || '';
  var x = nodeData.x || 0;
  var y = nodeData.y || 0;

  var group = new Konva.Group({
    x: x,
    y: y,
    draggable: false
  });

  // Node background
  var rect = new Konva.Rect({
    x: -40,
    y: -40,
    width: 80,
    height: 80,
    cornerRadius: 8,
    fill: color,
    shadowColor: 'rgba(0,0,0,0.2)',
    shadowBlur: 8,
    shadowOffset: { x: 2, y: 2 },
    shadowOpacity: 0.3
  });
  group.add(rect);

  // Icon text
  var iconText = new Konva.Text({
    x: -40,
    y: -32,
    width: 80,
    height: 50,
    text: icon,
    fontSize: 32,
    align: 'center',
    verticalAlign: 'middle',
    listening: false
  });
  group.add(iconText);

  // Label below node
  var labelText = new Konva.Text({
    x: -60,
    y: 45,
    width: 120,
    text: label,
    fontSize: 12,
    fill: '#6b7280',
    align: 'center',
    listening: false
  });
  group.add(labelText);

  return group;
}

/**
 * Render an edge as bezier curve with arrow
 * @param {Object} edgeData - { id, source, target, sourceNode, targetNode }
 * @returns {Konva.Group}
 */
function renderEdge(edgeData) {
  var group = new Konva.Group();

  var sx = edgeData.sourceNode ? edgeData.sourceNode.x : 0;
  var sy = edgeData.sourceNode ? edgeData.sourceNode.y : 0;
  var tx = edgeData.targetNode ? edgeData.targetNode.x : 0;
  var ty = edgeData.targetNode ? edgeData.targetNode.y : 0;

  // Calculate bezier control points
  var dx = tx - sx;
  var dy = ty - sy;
  var cx1 = sx + dx * 0.4;
  var cy1 = sy;
  var cx2 = tx - dx * 0.4;
  var cy2 = ty;

  // Create bezier line
  var line = new Konva.Line({
    points: [sx, sy, cx1, cy1, cx2, cy2, tx, ty],
    bezier: true,
    stroke: '#374151',
    strokeWidth: 2,
    lineCap: 'round',
    listening: false
  });
  group.add(line);

  // Calculate arrow angle at target end
  // Use the tangent at t=1 of bezier curve
  var t = 0.98;
  var t2 = 1 - t;
  // Bezier derivative at t
  var arrowX = 3 * t2 * t2 * (cx1 - sx) + 6 * t2 * t * (cx2 - cx1) + 3 * t * t * (tx - cx2);
  var arrowY = 3 * t2 * t2 * (cy1 - sy) + 6 * t2 * t * (cy2 - cy1) + 3 * t * t * (ty - cy2);
  var angle = Math.atan2(arrowY, arrowX) * 180 / Math.PI;

  // Arrow head at target
  var arrow = new Konva.Arrow({
    points: [tx - 15 * Math.cos(angle * Math.PI / 180), ty - 15 * Math.sin(angle * Math.PI / 180), tx, ty],
    stroke: '#374151',
    strokeWidth: 2,
    fill: '#374151',
    pointerLength: 10,
    pointerWidth: 8,
    listening: false
  });
  group.add(arrow);

  return group;
}

/**
 * Get topology data from current _topoData (Cytoscape format)
 * @returns {Object} { nodes: {...}, edges: {...} }
 */
function getTopoData() {
  var nodes = {};
  var edges = {};

  // Access Cytoscape instance if available
  if (typeof cy !== 'undefined' && cy) {
    cy.nodes().forEach(function(node) {
      var id = node.id();
      nodes[id] = node.data();
      nodes[id]._cyPosition = node.position();
    });
    cy.edges().forEach(function(edge) {
      var id = edge.id();
      edges[id] = edge.data();
    });
  } else if (typeof _topoData !== 'undefined' && _topoData) {
    // Fallback to global _topoData
    nodes = JSON.parse(JSON.stringify(_topoData.nodes || {}));
    edges = JSON.parse(JSON.stringify(_topoData.edges || {}));
  }

  return { nodes: nodes, edges: edges };
}

/**
 * Load topology data into Konva canvas
 * @param {Object} data - { nodes: {...}, edges: {...} }
 */
function loadTopoKonva(data) {
  if (!mainLayer || !stage) {
    console.error('[Konva] Stage not initialized');
    return;
  }

  // Clear existing nodes/edges
  mainLayer.destroyChildren();

  var nodeObjects = {};
  var nodeData = data.nodes || {};
  var edgeData = data.edges || {};

  // First pass: render all nodes
  for (var nodeId in nodeData) {
    var nd = nodeData[nodeId];
    var pos = nd._cyPosition || { x: nd.x || 100, y: nd.y || 100 };
    var nodeGroup = renderNode({
      id: nodeId,
      type: nd.deviceType || nd.type || 'server',
      label: nd.label || nd.name || nodeId,
      x: pos.x,
      y: pos.y
    });
    nodeGroup.id(nodeId);
    mainLayer.add(nodeGroup);
    nodeObjects[nodeId] = nodeGroup;
  }

  // Second pass: render all edges
  for (var edgeId in edgeData) {
    var ed = edgeData[edgeId];
    var sourceNode = nodeObjects[ed.source];
    var targetNode = nodeObjects[ed.target];
    if (sourceNode && targetNode) {
      var edgeGroup = renderEdge({
        id: edgeId,
        source: ed.source,
        target: ed.target,
        sourceNode: { x: sourceNode.x(), y: sourceNode.y() },
        targetNode: { x: targetNode.x(), y: targetNode.y() }
      });
      mainLayer.add(edgeGroup);
    }
  }

  mainLayer.batchDraw();
  console.log('[Konva] Loaded', Object.keys(nodeData).length, 'nodes,', Object.keys(edgeData).length, 'edges');
}

/**
 * Wrap a Konva Group as Cytoscape-like node
 * @param {Konva.Group} konvaGroup
 * @returns {Object} Cytoscape-like interface
 */
function makeCyNode(konvaGroup) {
  var nodeData = {};
  var nodePosition = { x: 0, y: 0 };

  // Initialize from existing group position
  if (konvaGroup) {
    nodePosition.x = konvaGroup.x() || 0;
    nodePosition.y = konvaGroup.y() || 0;
  }

  return {
    data: function(key, val) {
      if (val === undefined) {
        return nodeData[key];
      }
      nodeData[key] = val;
      return this;
    },
    position: function(x, y) {
      if (x === undefined) {
        return { x: nodePosition.x, y: nodePosition.y };
      }
      nodePosition.x = x;
      nodePosition.y = y;
      if (konvaGroup) {
        konvaGroup.position({ x: x, y: y });
        if (mainLayer) mainLayer.batchDraw();
      }
      return this;
    },
    select: function() {
      // No-op for compatibility
      return this;
    },
    remove: function() {
      if (konvaGroup && mainLayer) {
        konvaGroup.destroy();
        mainLayer.batchDraw();
      }
      return this;
    },
    id: function(newId) {
      if (newId === undefined) {
        return nodeData.id;
      }
      nodeData.id = newId;
      if (konvaGroup) {
        konvaGroup.id(newId);
      }
      return this;
    },
    _konvaGroup: konvaGroup
  };
}

/**
 * Wrap an edge for Cytoscape-like interface
 * @param {string} edgeId
 * @returns {Object} Cytoscape-like edge interface
 */
function makeCyEdge(edgeId) {
  var edgeData = { id: edgeId };

  return {
    data: function(key, val) {
      if (val === undefined) {
        return edgeData[key];
      }
      edgeData[key] = val;
      return this;
    },
    id: function(newId) {
      if (newId === undefined) {
        return edgeData.id;
      }
      edgeData.id = newId;
      return this;
    },
    remove: function() {
      return this;
    },
    source: function(newSource) {
      if (newSource === undefined) {
        return edgeData.source;
      }
      edgeData.source = newSource;
      return this;
    },
    target: function(newTarget) {
      if (newTarget === undefined) {
        return edgeData.target;
      }
      edgeData.target = newTarget;
      return this;
    }
  };
}
