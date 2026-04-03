/**
 * NetOps AI 操作技能注册表 v2
 * 每新增一个 AI 操作能力，在这里加一个 skill 即可
 * AI 通过 action name 找到对应 skill 来执行
 *
 * execute(op, _cy) 接受第二个参数 _cy，
 * 由 executeTopoOps 传入本地快照（避免执行期间 cy 被置 null）
 */
var OpSkills = (function() {

  function getCY(_cy) { return (_cy && typeof _cy.nodes === 'function') ? _cy : cy; }

  // ── 添加设备 ──────────────────────────────────────────
  function add_node_exe(op, _cy) {
    var $cy = getCY(_cy);
    var label = op.label || op.id || ('设备-' + Date.now());
    var type = op.type || 'switch';
    var x = parseInt(op.x) || 400;
    var y = parseInt(op.y) || 300;
    var id = op.id || label;
    var ip = op.ip || '';
    var color = op.color || null;
    if ($cy.getElementById(id).length > 0 || $cy.nodes('[label="' + id + '"]').length > 0) {
      return { ok: true, action: 'add_node', id, label, note: '设备已存在，跳过' };
    }
    var dev = (typeof getDeviceConfig === 'function') ? getDeviceConfig(type) : { w: 80, h: 80, color: '#3b82f6', label: type, icon: 'switch.png' };
    var w = dev.w || 80, h = dev.h || 80;
    var svg = (typeof makeDeviceSVG === 'function')
      ? makeDeviceSVG(type, color || dev.color, w, h, label, '/icons/' + dev.icon)
      : '';
    $cy.add({
      group: 'nodes',
      data: { id: id, type: type, label: label, icon: svg, color: color || dev.color, w: w, h: h, ip: ip, desc: dev.label, mac: '', port: '', bandwidth: '' },
      position: { x: x, y: y }
    });
    if (typeof addOpLog === 'function') addOpLog('ai', '添加设备：' + label);
    return { ok: true, action: 'add_node', id, label, type, x, y };
  }

  // ── 添加连线 ──────────────────────────────────────────
  function add_edge_exe(op, _cy) {
    var $cy = getCY(_cy);
    var srcId = op.from || op.src;
    var tgtId = op.to || op.tgt;
    if (!srcId || !tgtId) return { error: 'from 和 to 不能为空' };
    var srcNode = $cy.getElementById(srcId);
    var tgtNode = $cy.getElementById(tgtId);
    if (srcNode.empty()) srcNode = $cy.nodes('[label="' + srcId + '"]');
    if (tgtNode.empty()) tgtNode = $cy.nodes('[label="' + tgtId + '"]');
    if (srcNode.empty()) return { error: '源设备不存在：' + srcId };
    if (tgtNode.empty()) return { error: '目标设备不存在：' + tgtId };
    var realSrcId = srcNode.id(), realTgtId = tgtNode.id();
    var exists = $cy.edges().some(function(e) {
      return e.source().id() === realSrcId && e.target().id() === realTgtId;
    });
    if (exists) return { ok: true, action: 'add_edge', src: srcId, tgt: tgtId, note: '连线已存在，跳过' };
    var edgeColor = op.edgeColor || op.color || '#374151';
    var edgeStyle = op.edgeStyle || 'solid';
    var newEdge = $cy.add({
      group: 'edges',
      data: {
        source: realSrcId, target: realTgtId,
        label: '', srcPort: op.srcPort || '', tgtPort: op.tgtPort || '',
        edgeStyle: edgeStyle, edgeColor: edgeColor,
        edgeWidth: op.edgeWidth || 2, edgeBandwidth: op.bandwidth || ''
      }
    });
    newEdge.style({ 'curve-style': 'bezier', 'line-color': edgeColor, 'line-style': edgeStyle, 'width': op.edgeWidth || 2 });
    if (typeof addOpLog === 'function') addOpLog('ai', '添加连线：' + srcId + ' → ' + tgtId);
    return { ok: true, action: 'add_edge', src: srcId, tgt: tgtId };
  }

  // ── 移动设备 ──────────────────────────────────────────
  function move_node_exe(op, _cy) {
    var $cy = getCY(_cy);
    var id = op.id || op.label || '';
    if (!id) return { error: 'id 不能为空' };
    var node = $cy.getElementById(id);
    if (node.empty()) node = $cy.nodes('[label="' + id + '"]');
    if (node.empty()) return { error: '节点不存在：' + id };
    node.position({ x: parseInt(op.x) || 300, y: parseInt(op.y) || 200 });
    if (typeof addOpLog === 'function') addOpLog('ai', '移动设备：' + id);
    return { ok: true, action: 'move_node', id, x: op.x, y: op.y };
  }

  // ── 删除设备 ──────────────────────────────────────────
  function delete_node_exe(op, _cy) {
    var $cy = getCY(_cy);
    var id = op.id || op.label || '';
    if (!id) return { error: 'id 不能为空' };
    var node = $cy.getElementById(id);
    if (node.empty()) node = $cy.nodes('[label="' + id + '"]');
    if (node.empty()) return { error: '节点不存在：' + id };
    node.connectedEdges().remove();
    node.remove();
    if (typeof addOpLog === 'function') addOpLog('ai', '删除设备：' + id);
    return { ok: true, action: 'delete_node', id };
  }

  // ── 删除连线 ──────────────────────────────────────────
  function delete_edge_exe(op, _cy) {
    var $cy = getCY(_cy);
    var srcId = op.from || op.src;
    var tgtId = op.to || op.tgt;
    if (!srcId || !tgtId) return { error: 'from 和 to 不能为空' };
    var edge = $cy.edges().filter(function(e) {
      return (e.source().id() === srcId && e.target().id() === tgtId) ||
             (e.source().id() === tgtId && e.target().id() === srcId);
    });
    if (edge.empty()) return { error: '连线不存在：' + srcId + ' ↔ ' + tgtId };
    edge.remove();
    if (typeof addOpLog === 'function') addOpLog('ai', '删除连线：' + srcId + ' ↔ ' + tgtId);
    return { ok: true, action: 'delete_edge', src: srcId, tgt: tgtId };
  }

  // ── 修改设备属性 ──────────────────────────────────────
  function modify_node_exe(op, _cy) {
    var $cy = getCY(_cy);
    var id = op.id || op.label || '';
    if (!id) return { error: 'id 不能为空' };
    var node = $cy.getElementById(id);
    if (node.empty()) node = $cy.nodes('[label="' + id + '"]');
    if (node.empty()) return { error: '节点不存在：' + id };
    if (op.label) {
      node.data('label', op.label);
      if (typeof makeDeviceSVG === 'function' && !node.data('isShape') && !node.data('isTextBox')) {
        var nd = node.data(), nt = nd.type || 'switch';
        var nw = nd.w || 80, nh = nd.h || 80;
        var ncol = nd.color || '#3b82f6';
        var nicon = nd.icon || '/icons/switch.png';
        node.css({ 'background-image': makeDeviceSVG(nt, ncol, nw, nh, op.label, nicon) });
      }
    }
    if (op.ip) node.data('ip', op.ip);
    if (op.mac) node.data('mac', op.mac);
    if (op.desc) node.data('desc', op.desc);
    if (op.port) node.data('port', op.port);
    if (op.bandwidth) node.data('bandwidth', op.bandwidth);
    if (op.color) node.style('border-color', op.color);
    if (typeof addOpLog === 'function') addOpLog('ai', '修改设备属性：' + id);
    return { ok: true, action: 'modify_node', id };
  }

  var skills = {
    add_node:    { name: 'add_node',    execute: add_node_exe },
    add_device:  { name: 'add_device',  execute: add_node_exe },
    'add':       { name: 'add',         execute: add_node_exe },
    add_edge:    { name: 'add_edge',   execute: add_edge_exe },
    add_link:    { name: 'add_link',    execute: add_edge_exe },
    move_node:   { name: 'move_node',  execute: move_node_exe },
    delete_node: { name: 'delete_node', execute: delete_node_exe },
    remove_node: { name: 'remove_node', execute: delete_node_exe },
    'delete':    { name: 'delete',      execute: delete_node_exe },
    'del':       { name: 'del',         execute: delete_node_exe },
    delete_edge: { name: 'delete_edge', execute: delete_edge_exe },
    remove_edge: { name: 'remove_edge', execute: delete_edge_exe },
    modify_node: { name: 'modify_node', execute: modify_node_exe },
    update_node: { name: 'update_node', execute: modify_node_exe },
  };

  function resolveSkill(action) {
    if (skills[action]) return skills[action];
    for (var k in skills) {
      if (skills[k].name === action) return skills[k];
    }
    return null;
  }

  /** 通用执行入口（供 executeTopoOps 调用） */
  function executeOp(op, _cy) {
    if (!op || !op.action) return { error: '操作格式错误：缺少 action 字段' };
    var skill = resolveSkill(op.action);
    if (!skill) return { error: '未知操作类型：' + op.action + '，可用：' + Object.keys(skills).join(', ') };
    try {
      return skill.execute(op, _cy);
    } catch (e) {
      return { error: '执行失败：' + e.message, action: op.action };
    }
  }

  /** 返回所有技能描述（供 AI system prompt 使用） */
  function getSkillDescriptions() {
    var seen = {};
    var lines = [];
    var _params = {
      add_node:    'id|label*, type, x, y, ip, color',
      add_edge:    'from|src*, to|tgt*, srcPort, tgtPort, bandwidth',
      move_node:   'id*, x*, y*',
      delete_node: 'id*',
      delete_edge: 'from|src*, to|tgt*',
      modify_node: 'id*, label, ip, color',
    };
    for (var k in skills) {
      if (seen[skills[k].name]) continue;
      seen[skills[k].name] = true;
      var p = _params[skills[k].name] || '';
      lines.push('  - ' + skills[k].name + (p ? '(' + p + ')' : ''));
    }
    return lines.join('\n');
  }

  return { execute: executeOp, getSkillDescriptions: getSkillDescriptions, resolveSkill: resolveSkill };
})();
