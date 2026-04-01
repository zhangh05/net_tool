/**
 * Konva.js interaction layer for NetOps topology editor
 * Handles click, selection, highlight, and delete operations
 */

// Selected nodes/edges on Konva canvas
var _selectedNodes = [];
var _selectedEdges = [];

/**
 * Show highlight ring around a Konva node
 */
function showKonvaHighlight(konvaGroup) {
  if (!konvaGroup || !mainLayer) return;
  // Remove existing highlight
  hideKonvaHighlight(konvaGroup);
  var rect = konvaGroup.findOne('Rect');
  if (rect) {
    var highlight = new Konva.Rect({
      x: rect.x() - 4,
      y: rect.y() - 4,
      width: rect.width() + 8,
      height: rect.height() + 8,
      cornerRadius: rect.cornerRadius() + 4,
      stroke: '#fbbf24',
      strokeWidth: 3,
      fill: 'transparent',
      name: 'highlight-ring',
      listening: false
    });
    konvaGroup.add(highlight);
    konvaGroup.moveToTop();
    mainLayer.batchDraw();
  }
}

/**
 * Remove highlight ring from a Konva node
 */
function hideKonvaHighlight(konvaGroup) {
  if (!konvaGroup) return;
  var ring = konvaGroup.findOne('.highlight-ring');
  if (ring) {
    ring.destroy();
    mainLayer.batchDraw();
  }
}

/**
 * Deselect all selected nodes and edges
 */
function deselectAll() {
  _selectedNodes.forEach(function(n) {
    hideKonvaHighlight(n);
  });
  _selectedNodes = [];
  _selectedEdges = [];
}

/**
 * Delete an edge by its ID
 */
function deleteEdgeById(eid) {
  if (!mainLayer || !_topoData) return;
  var edge = mainLayer.findOne('#' + eid);
  if (edge) {
    edge.destroy();
    mainLayer.batchDraw();
  }
  if (_topoData.edges && _topoData.edges[eid]) {
    delete _topoData.edges[eid];
  }
}

/**
 * Setup click interactions on Konva nodes
 */
function setupKonvaInteractions() {
  if (!mainLayer) return;

  // Make all device/shape nodes clickable
  mainLayer.on('click', '.device-node, .shape-node, .textbox-node', function(e) {
    var target = e.target;
    // Walk up to group if clicking on child shape
    var group = target.getParent();
    if (!group || !group.hasName('device-node') && !group.hasName('shape-node') && !group.hasName('textbox-node')) {
      group = target;
    }

    // Multi-select with Ctrl
    if (e.evt && e.evt.ctrlKey) {
      var idx = _selectedNodes.indexOf(group);
      if (idx >= 0) {
        hideKonvaHighlight(group);
        _selectedNodes.splice(idx, 1);
      } else {
        _selectedNodes.push(group);
        showKonvaHighlight(group);
         }
    } else {
      // Single select - deselect others
      deselectAll();
      _selectedNodes.push(group);
      showKonvaHighlight(group);
    }
  });

  // Click on empty space deselects
  mainLayer.on('click', function(e) {
    if (e.target === mainLayer || e.target.getParent() === gridLayer) {
      deselectAll();
    }
  });
}
