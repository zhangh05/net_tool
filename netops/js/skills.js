/**
 * js/skills.js - NetOps AI 统一技能契约（前端 JS 版本）
 * 由 AI_sys_prompt/skills.json 自动生成
 * 用途：前端 AI 聊天时了解可用技能，辅助提示词构建
 */
(function(root, factory) {
  if (typeof module === 'object' && typeof module.exports === 'object') {
    module.exports = factory();
  } else {
    root.NetOpsSkills = factory();
  }
}(typeof self !== 'undefined' ? self : this, function() {

  // ─── 技能契约版本 ───────────────────────────────────────────────
  var VERSION = '3.0';
  var UPDATED = '2026-04-10';

  // ─── 拓扑操作技能 ───────────────────────────────────────────────
  var TOPOLOGY_ACTIONS = {
    add_node: {
      label: '添加设备',
      description: '在拓扑中添加一台新设备',
      params: [
        {name: 'id',      type: 'string',  required: true,  description: '设备ID，唯一标识'},
        {name: 'type',    type: 'enum',    required: true,  enum: ['router','switch','firewall','server','PC','cloud','internet'], description: '设备类型'},
        {name: 'x',       type: 'integer', required: false, description: '横坐标'},
        {name: 'y',       type: 'integer', required: false, description: '纵坐标'},
        {name: 'ip',      type: 'string',  required: false, description: 'IP地址'},
        {name: 'label',   type: 'string',  required: false, description: '显示名称'}
      ],
      confirm_required: false,
      example: '[op] add_node:id=R1,type=router,ip=192.168.1.1,label=核心路由器'
    },
    add_edge: {
      label: '添加连线',
      description: '在两个已有设备之间建立连线',
      params: [
        {name: 'from',    type: 'string', required: true,  description: '源设备ID'},
        {name: 'to',      type: 'string', required: true,  description: '目标设备ID'},
        {name: 'srcPort', type: 'string', required: false, description: '源端口，如GE0/0/1'},
        {name: 'tgtPort', type: 'string', required: false, description: '目标端口，如GE0/0/1'}
      ],
      confirm_required: true,
      example: '[op] add_edge:from=R1,to=SW1,srcPort=GE0/0/1,tgtPort=GE0/0/1'
    },
    delete_node: {
      label: '删除设备',
      description: '从拓扑中删除一台设备，同时删除相关所有连线',
      params: [
        {name: 'id', type: 'string', required: true, description: '设备ID'}
      ],
      confirm_required: true,
      example: '[op] delete_node:id=R1'
    },
    delete_edge: {
      label: '删除连线',
      description: '删除两个设备之间的连线',
      params: [
        {name: 'from', type: 'string', required: true, description: '源设备ID'},
        {name: 'to',   type: 'string', required: true, description: '目标设备ID'}
      ],
      confirm_required: true,
      example: '[op] delete_edge:from=R1,to=SW1'
    },
    modify_node: {
      label: '修改设备属性',
      description: '修改设备属性（标签、IP、类型）',
      params: [
        {name: 'id',    type: 'string', required: true, description: '设备ID'},
        {name: 'label',type: 'string', required: false, description: '新显示名称'},
        {name: 'ip',    type: 'string', required: false, description: '新IP地址'},
        {name: 'type', type: 'enum',   required: false, enum: ['router','switch','firewall','server','PC','cloud','internet'], description: '新设备类型'}
      ],
      confirm_required: true,
      example: '[op] modify_node:id=R1,label=边缘路由器,ip=10.0.0.1'
    },
    move_node: {
      label: '移动设备',
      description: '在拓扑图上移动设备位置',
      params: [
        {name: 'id', type: 'string',  required: true, description: '设备ID'},
        {name: 'x',  type: 'integer', required: true, description: '新横坐标'},
        {name: 'y',  type: 'integer', required: true, description: '新纵坐标'}
      ],
      confirm_required: false,
      example: '[op] move_node:id=R1,x=400,y=200'
    },
    clear_topo: {
      label: '清空拓扑',
      description: '清空所有设备和连线',
      params: [],
      confirm_required: true,
      example: '[op] clear_topo'
    }
  };

  // ─── 设备操作技能 ───────────────────────────────────────────────
  var DEVICE_ACTIONS = {
    device_connect: {
      label: '连接设备',
      description: '建立到网络设备的Telnet/SSH连接',
      params: [
        {name: 'protocol', type: 'enum',    required: true,  enum: ['telnet', 'ssh'], description: '连接协议'},
        {name: 'ip',       type: 'string',  required: true,  description: '设备IP'},
        {name: 'port',     type: 'integer', required: true,  description: '端口号'},
        {name: 'user',     type: 'string',  required: false, description: '用户名'},
        {name: 'password', type: 'string',  required: false, description: '密码'}
      ],
      confirm_required: false
    },
    device_send: {
      label: '发送命令',
      description: '向已连接设备发送命令',
      params: [
        {name: 'session_id', type: 'string', required: true, description: '会话ID'},
        {name: 'cmd',        type: 'string', required: true, description: '命令内容'}
      ],
      confirm_required: false
    },
    device_expect: {
      label: '等待确认提示',
      description: '等待设备返回特定模式（如[Y/N]）',
      params: [
        {name: 'session_id', type: 'string', required: true,  description: '会话ID'},
        {name: 'pattern',    type: 'string', required: true,  description: '正则表达式模式'},
        {name: 'timeout_ms', type: 'integer',required: false, description: '超时毫秒'}
      ],
      confirm_required: false
    },
    device_confirm: {
      label: '发送确认',
      description: '向设备发送Y或N确认',
      params: [
        {name: 'session_id', type: 'string', required: true, description: '会话ID'},
        {name: 'answer',     type: 'enum',   required: true, enum: ['Y', 'N'], description: '确认答案'}
      ],
      confirm_required: false
    },
    device_batch: {
      label: '批量执行命令',
      description: '批量发送多条命令',
      params: [
        {name: 'session_id', type: 'string',  required: true,  description: '会话ID'},
        {name: 'commands',   type: 'array',   required: true,  description: '命令数组'},
        {name: 'delay_ms',   type: 'integer', required: false, description: '命令间隔毫秒'}
      ],
      confirm_required: false
    },
    device_close: {
      label: '关闭会话',
      description: '关闭设备连接会话',
      params: [
        {name: 'session_id', type: 'string', required: true, description: '会话ID'}
      ],
      confirm_required: false
    }
  };

  // ─── 查询操作技能 ───────────────────────────────────────────────
  var QUERY_ACTIONS = {
    ping: {
      label: '检测连通性',
      description: 'Ping检测设备是否可达',
      params: [
        {name: 'ip', type: 'string', required: true, description: '目标IP'}
      ],
      confirm_required: false
    },
    get_topology_summary: {
      label: '获取拓扑概览',
      description: '获取拓扑概览信息',
      params: [],
      confirm_required: false
    },
    get_node_ip: {
      label: '获取设备IP',
      description: '根据设备ID获取IP',
      params: [
        {name: 'id', type: 'string', required: true, description: '设备ID'}
      ],
      confirm_required: false
    },
    select_node: {
      label: '选中设备',
      description: '在拓扑图上选中指定设备',
      params: [
        {name: 'id', type: 'string', required: true, description: '设备ID'}
      ],
      confirm_required: false
    },
    fit_view: {
      label: '适应视图',
      description: '缩放视图适应所有设备',
      params: [],
      confirm_required: false
    },
    toast: {
      label: '提示消息',
      description: '显示临时提示消息',
      params: [
        {name: 'message', type: 'string', required: true, description: '消息内容'}
      ],
      confirm_required: false
    },
    save_project: {
      label: '保存项目',
      description: '保存当前项目拓扑',
      params: [],
      confirm_required: false
    }
  };

  // ─── 设备类型定义 ───────────────────────────────────────────────
  var DEVICE_TYPES = {
    router:   {icon: '🌐', label: '路由器',   color: '#3b82f6'},
    switch:   {icon: '🔌', label: '交换机',   color: '#10b981'},
    firewall: {icon: '🛡', label: '防火墙',   color: '#f59e0b'},
    server:   {icon: '🖥', label: '服务器',   color: '#8b5cf6'},
    PC:       {icon: '💻', label: '个人电脑', color: '#6b7280'},
    cloud:    {icon: '☁️', label: '云服务',   color: '#60a5fa'},
    internet: {icon: '🌍', label: '互联网',   color: '#94a3b8'}
  };

  // ─── 规则 ───────────────────────────────────────────────────────
  var RULES = {
    max_batch_size: 20,
    coordinate_range: {min: 0, max: 2000},
    port_format: 'GE0/0/{n}',
    port_range: [0, 3]
  };

  // ─── 辅助函数 ───────────────────────────────────────────────────
  function getAllActions() {
    var result = {};
    Object.keys(TOPOLOGY_ACTIONS).forEach(function(k) { result[k] = TOPOLOGY_ACTIONS[k]; });
    Object.keys(DEVICE_ACTIONS).forEach(function(k) { result[k] = DEVICE_ACTIONS[k]; });
    Object.keys(QUERY_ACTIONS).forEach(function(k) { result[k] = QUERY_ACTIONS[k]; });
    return result;
  }

  function getAction(name) {
    return TOPOLOGY_ACTIONS[name] || DEVICE_ACTIONS[name] || QUERY_ACTIONS[name];
  }

  function getSkillExamples() {
    var lines = [];
    Object.values(TOPOLOGY_ACTIONS).forEach(function(a) {
      if (a.example) lines.push(a.example);
    });
    return lines.join('\n');
  }

  function buildSkillPrompt() {
    var parts = ['## 可用技能（AI 操作契约 v' + VERSION + '）\n'];
    parts.push('【拓扑操作】');
    Object.entries(TOPOLOGY_ACTIONS).forEach(function(entry) {
      var k = entry[0], a = entry[1];
      parts.push('- ' + a.label + '（' + k + '）: ' + a.description);
      a.params.forEach(function(p) {
        var req = p.required ? '[必填]' : '[可选]';
        parts.push('  ' + req + ' ' + p.name + ' (' + p.type + '): ' + p.description);
      });
    });
    parts.push('\n【设备操作】');
    Object.entries(DEVICE_ACTIONS).forEach(function(entry) {
      var k = entry[0], a = entry[1];
      parts.push('- ' + a.label + '（' + k + '）: ' + a.description);
    });
    parts.push('\n【查询操作】');
    Object.entries(QUERY_ACTIONS).forEach(function(entry) {
      var k = entry[0], a = entry[1];
      parts.push('- ' + a.label + '（' + k + '）: ' + a.description);
    });
    parts.push('\n【设备类型】');
    Object.entries(DEVICE_TYPES).forEach(function(entry) {
      var k = entry[0], d = entry[1];
      parts.push('- ' + d.icon + ' ' + d.label + ' (' + k + ')');
    });
    parts.push('\n【操作示例】');
    parts.push(getSkillExamples());
    return parts.join('\n');
  }

  // ─── 导出 ───────────────────────────────────────────────────────
  return {
    version: VERSION,
    updated: UPDATED,
    topologyActions: TOPOLOGY_ACTIONS,
    deviceActions: DEVICE_ACTIONS,
    queryActions: QUERY_ACTIONS,
    deviceTypes: DEVICE_TYPES,
    rules: RULES,
    getAllActions: getAllActions,
    getAction: getAction,
    getSkillExamples: getSkillExamples,
    buildSkillPrompt: buildSkillPrompt
  };
}));
