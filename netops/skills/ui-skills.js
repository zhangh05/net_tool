/**
 * UI / 工具类 OpSkills
 * 封装前端常用工具函数为 AI 可调用的 OpSkill
 */
(function() {
  if (typeof OpSkills === 'undefined') return;

  // ── 工具函数 ──────────────────────────────────────────

  /** 获取选中设备或指定设备的 IP */
  function getNodeIp(nodeId) {
    if (!cy) return null;
    var node;
    if (nodeId) {
      node = cy.getElementById(nodeId);
      if (node.empty()) node = cy.nodes('[label="' + nodeId + '"]');
    } else {
      node = cy.$(':selected');
      if (node.empty()) node = cy.nodes().first();
    }
    return node.empty() ? null : (node.data('ip') || null);
  }

  /** 获取拓扑概览 */
  function getTopoSummary() {
    if (!cy) return { nodes: 0, edges: 0, devices: [] };
    var nodes = cy.nodes().filter('[!isShape][!isTextBox]');
    var edges = cy.edges();
    var devices = nodes.map(function(n) {
      return {
        id: n.id(),
        label: n.data('label') || n.id(),
        type: n.data('type') || 'unknown',
        ip: n.data('ip') || '',
        x: Math.round(n.position().x),
        y: Math.round(n.position().y)
      };
    });
    return {
      nodeCount: nodes.length,
      edgeCount: edges.length,
      devices: devices,
      projectId: window.currentProjectId || null,
      projectName: window.currentProjectName || null
    };
  }

  /** 获取设备会话列表（终端 PTY） */
  function listDeviceSessions() {
    // 通过 WebSocket 9011 获取活动会话
    return new Promise(function(resolve) {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', window.location.protocol + '//' + window.location.hostname + ':9011/api/sessions', true);
      xhr.onload = function() {
        if (xhr.status === 200) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch (e) { resolve({ sessions: [] }); }
        } else { resolve({ sessions: [] }); }
      };
      xhr.onerror = function() { resolve({ sessions: [] }); };
      xhr.send();
    });
  }

  // ── 注册 OpSkills ─────────────────────────────────────

  /** 获取设备 IP */
  OpSkills.get_node_ip = {
    name: 'get_node_ip',
    description: '获取拓扑中某设备的管理 IP',
    params: ['node_id'],
    execute: function(op) {
      var ip = getNodeIp(op.node_id || null);
      if (!ip) return { ok: false, error: '未找到设备 IP，请确认设备已设置 IP 地址' };
      return { ok: true, ip: ip, node_id: op.node_id || null };
    }
  };

  /** 获取拓扑概览 */
  OpSkills.get_topology_summary = {
    name: 'get_topology_summary',
    description: '获取当前拓扑的全局信息（节点数、边数、所有设备列表）',
    params: [],
    execute: function() {
      var summary = getTopoSummary();
      return { ok: true, summary: summary };
    }
  };

  /** 选中指定设备 */
  OpSkills.select_node = {
    name: 'select_node',
    description: '在拓扑图中选中指定设备（高亮）',
    params: ['node_id*'],
    execute: function(op) {
      if (!op.node_id) return { ok: false, error: 'node_id 不能为空' };
      var node = cy.getElementById(op.node_id);
      if (node.empty()) node = cy.nodes('[label="' + op.node_id + '"]');
      if (node.empty()) return { ok: false, error: '设备不存在：' + op.node_id };
      cy.elements().unselect();
      node.select();
      if (typeof showProps === 'function') showProps(node);
      return { ok: true, node_id: op.node_id, label: node.data('label') };
    }
  };

  /** 视图缩放到所有设备 */
  OpSkills.fit_view = {
    name: 'fit_view',
    description: '自动缩放视图，让所有设备都可见',
    params: ['padding'],
    execute: function(op) {
      if (!cy) return { ok: false, error: '画布未就绪' };
      var padding = parseInt(op.padding) || 50;
      cy.fit(undefined, padding);
      return { ok: true };
    }
  };

  /** 显示设备属性面板 */
  OpSkills.show_node_props = {
    name: 'show_node_props',
    description: '显示选中设备或指定设备的属性编辑面板',
    params: ['node_id'],
    execute: function(op) {
      var node;
      if (op.node_id) {
        node = cy.getElementById(op.node_id);
        if (node.empty()) node = cy.nodes('[label="' + op.node_id + '"]');
      } else {
        node = cy.$(':selected');
      }
      if (node.empty()) return { ok: false, error: '没有选中设备' };
      if (typeof showProps === 'function') showProps(node);
      return { ok: true, node_id: node.id(), label: node.data('label') };
    }
  };

  /** 隐藏设备属性面板 */
  OpSkills.hide_node_props = {
    name: 'hide_node_props',
    description: '隐藏属性面板',
    params: [],
    execute: function() {
      if (typeof hideProps === 'function') hideProps();
      return { ok: true };
    }
  };

  /** Ping 设备 */
  OpSkills.ping = {
    name: 'ping',
    description: '检测设备 IP 是否可达',
    params: ['ip*'],
    execute: function(op) {
      var ip = op.ip;
      if (!ip) return { ok: false, error: 'ip 不能为空' };
      // 同步执行 ping（利用现有 API）
      var xhr = new XMLHttpRequest();
      var result;
      xhr.open('GET', '/api/ping?ip=' + encodeURIComponent(ip), false); // 同步
      try {
        xhr.send(null);
        if (xhr.status === 200) {
          var d = JSON.parse(xhr.responseText);
          result = { ok: true, success: d.success, output: d.output || '', ip: ip };
        } else {
          result = { ok: false, error: 'Ping 请求失败: HTTP ' + xhr.status };
        }
      } catch(e) {
        result = { ok: false, error: e.message };
      }
      return result;
    }
  };

  OpSkills.read_project_file = {
    name: 'read_project_file',
    description: '读取项目文件库中的文件内容',
    params: ['filename*'],
    execute: function(op) {
      var filename = op.filename;
      if (!filename) return { ok: false, error: 'filename 不能为空' };
      var xhr = new XMLHttpRequest();
      xhr.open('GET', '/api/projects/' + encodeURIComponent(currentProjectId) + '/files/' + encodeURIComponent(filename), false);
      try {
        xhr.send(null);
        if (xhr.status === 200) {
          var d = JSON.parse(xhr.responseText);
          return { ok: true, name: d.name, content: d.content || '', size: (d.content || '').length };
        } else if (xhr.status === 404) {
          return { ok: false, error: '文件不存在：' + filename };
        } else {
          return { ok: false, error: '读取失败: HTTP ' + xhr.status };
        }
      } catch(e) {
        return { ok: false, error: e.message };
      }
    }
  };

  OpSkills.list_project_files = {
    name: 'list_project_files',
    description: '列出项目文件库中的所有文件',
    params: [],
    execute: function(op) {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', '/api/projects/' + encodeURIComponent(currentProjectId) + '/files', false);
      try {
        xhr.send(null);
        if (xhr.status === 200) {
          return { ok: true, files: JSON.parse(xhr.responseText) };
        }
        return { ok: false, error: '获取文件列表失败: HTTP ' + xhr.status };
      } catch(e) {
        return { ok: false, error: e.message };
      }
    }
  };

  /** Toast 提示 */
  OpSkills.toast = {
    name: 'toast',
    description: '在页面底部显示一条临时提示消息',
    params: ['message*'],
    execute: function(op) {
      if (!op.message) return { ok: false, error: 'message 不能为空' };
      if (typeof toast === 'function') toast(op.message);
      return { ok: true, message: op.message };
    }
  };

  /** 列出活动终端会话 */
  OpSkills.list_sessions = {
    name: 'list_sessions',
    description: '列出当前所有活动的 Telnet/SSH 会话',
    params: [],
    async execute() {
      var sessions = await listDeviceSessions();
      return { ok: true, sessions: sessions.sessions || [] };
    }
  };

  /** 保存当前项目拓扑 */
  OpSkills.save_project = {
    name: 'save_project',
    description: '立即保存当前拓扑到服务器',
    params: [],
    execute: function() {
      if (typeof autoSaveProject === 'function') autoSaveProject();
      return { ok: true };
    }
  };

  /** 刷新画布 */
  OpSkills.refresh_canvas = {
    name: 'refresh_canvas',
    description: '重新渲染画布（清除选择、隐藏悬浮框）',
    params: [],
    execute: function() {
      if (typeof refreshCanvas === 'function') refreshCanvas();
      if (typeof hideResizeHandles === 'function') hideResizeHandles();
      return { ok: true };
    }
  };

  console.log('[UI-Skills] 已注册 ' + Object.keys(OpSkills).length + ' 个 OpSkills');
})();
