/**
 * Manage — Coordination Platform
 * app.js — Main Application Logic
 */

// ── State ─────────────────────────────────────────────
let agents = [];
let currentProject = localStorage.getItem('manage_project') || 'default';

// ── Workflow Tracker State ──────────────────────────────
// Stages: idle | thinking | planning | waiting_confirm | executing | done | error
const WORKFLOW_STAGES = [
  { key: 'thinking',      icon: '💭', label: '理解需求',   color: '#8b949e' },
  { key: 'planning',      icon: '📡', label: '调用 NetOps', color: '#8b949e' },
  { key: 'waiting_confirm', icon: '🔒', label: '等待确认',   color: '#8b949e' },
  { key: 'executing',     icon: '⚡', label: '执行操作',   color: '#8b949e' },
  { key: 'done',          icon: '✅', label: '完成',       color: '#8b949e' },
];
// ── U-Shaped Flow Card ──────────────────────────────────
// Three-layer architecture: 用户层 → 协调层 → 实施层 → 回流
//
// Flow phases:
//   下发 (going):    用户层 → 协调层 → 实施层
//   回流 (return):   实施层 → 协调层 → 用户层
//
// Stages: idle | going:coord | going:exec | return:coord | return:user
//
let _flow = {
  phase: 'idle',   // idle | going | return
  activeLayer: null, // user | coord | exec
  message: ''
};

function _updateFlow(stage) {
  // Map server stage names to flow state
  const stageMap = {
    'idle':            { phase: 'idle',    activeLayer: null },
    'coord:planning':  { phase: 'going',  activeLayer: 'coord' },
    'coord:dispatching': { phase: 'going', activeLayer: 'coord' },
    'coord:summarizing': { phase: 'going', activeLayer: 'coord' },
    'coord:waiting':   { phase: 'going',  activeLayer: 'coord' },
    'coord:error':     { phase: 'going',  activeLayer: 'coord' },
    'exec:executing':  { phase: 'going',  activeLayer: 'exec' },
    'exec:complete':   { phase: 'return', activeLayer: 'coord' },
    'user:streaming':  { phase: 'return', activeLayer: 'user' },
    'user:done':       { phase: 'return', activeLayer: 'user' },
  };
  const mapped = stageMap[stage] || { phase: 'going', activeLayer: 'coord' };
  _flow = { phase: mapped.phase, activeLayer: mapped.activeLayer, message: '' };
  _renderFlowCard();
}

function _renderFlowCard() {
  // Reset the new dual-layer flow card to idle state
  resetFlowCards();
}

function setWorkflowStage(stage, error) {
  _updateFlow(stage);
  _renderFlowCard();
}

function _workflowPlanning()  { _updateFlow('coord:planning'); }
function _workflowWaiting()  { _updateFlow('coord:waiting'); }
function _workflowExecuting(){ _updateFlow('exec:executing'); }
function _workflowDone()    { _updateFlow('user:streaming'); setTimeout(() => { _updateFlow('idle'); _renderFlowCard(); }, 3000); }
function _workflowError(msg){ _updateFlow('coord:error'); }
function _workflowReset()   { _updateFlow('idle'); }

function renderWorkflowTracker() { _renderFlowCard(); }  // backward compat


// ── Chat History Persistence ───────────────────────────
function saveChatToStorage(role, text, time) {
  try {
    const key = _chatKey();
    const raw = localStorage.getItem(key);
    const msgs = raw ? JSON.parse(raw) : [];
    msgs.push({ role, text, time, _ts: Date.now() });
    if (msgs.length > 200) msgs.splice(0, msgs.length - 200);  // cap at 200
    localStorage.setItem(key, JSON.stringify(msgs));
  } catch(e) {}
}


async function loadChatFromServer() {
  // 优先从服务器加载聊天历史（跨设备同步）
  try {
    const d = await api('GET', '/api/manage/history?project_id=' + encodeURIComponent(currentProject));
    const msgs = d.messages || [];
    if (msgs.length > 0) {
      const area = document.getElementById('chatArea');
      removeEmptyState();
      msgs.forEach(m => {
        const div = document.createElement('div');
        div.className = 'msg msg-' + (m.role === 'user' ? 'user' : 'bot');
        div.innerHTML = '<div class="msg-avatar">' + (m.role === 'user' ? '👤' : '🤖') + '</div>' +
          '<div class="msg-content"><div class="bubble">' + md2html(m.content || '') + '</div>' +
          '<div class="msg-time">' + (m.time || '') + '</div></div>';
        area.appendChild(div);
      });
      scrollChat();
      // 同步到 localStorage 作为本地缓存
      try {
        const key = _chatKey();
        const cache = msgs.map(m => ({ role: m.role === 'user' ? 'user' : 'bot', text: m.content || '', time: m.time || '' }));
        localStorage.setItem(key, JSON.stringify(cache));
      } catch(e2) {}
      return;
    }
  } catch(e) {
    console.warn('[loadChatFromServer] failed, falling back to localStorage:', e.message);
  }
  // Fallback: 从 localStorage 加载
  try {
    const key = _chatKey();
    const raw = localStorage.getItem(key);
    if (!raw) return;
    const msgs = JSON.parse(raw);
    if (!msgs.length) return;
    const area = document.getElementById('chatArea');
    removeEmptyState();
    msgs.forEach(m => {
      const div = document.createElement('div');
      div.className = 'msg msg-' + (m.role === 'user' ? 'user' : 'bot');
      div.innerHTML = '<div class="msg-avatar">' + (m.role === 'user' ? '👤' : '🤖') + '</div>' +
        '<div class="msg-content"><div class="bubble">' + md2html(m.text || '') + '</div>' +
        '<div class="msg-time">' + (m.time || '') + '</div></div>';
      area.appendChild(div);
    });
    scrollChat();
  } catch(e2) {}
}



// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadProjects();   // 加载 NetOps 项目列表
  await loadSettings();
  await loadAgents();
  renderAgents();
  attachEventListeners();
  await loadChatFromServer();  // 优先从服务器恢复聊天历史（跨设备同步）
  restoreExecLogFromStorage();  // 恢复执行日志
  renderWorkflowTracker();  // 初始化流程追踪
  initWebSocket();  // 初始化 WebSocket 客户端
  refreshDeviceList();  // 加载设备列表
});

// ── Project Management ─────────────────────────────────
async function loadProjects() {
  const sel = document.getElementById('projectSelect');
  const saved = localStorage.getItem('manage_project') || '';
  try {
    const d = await api('GET', '/api/manage/projects');
    const projects = d.projects || [];
    sel.innerHTML = '';
    if (!projects.length) {
      sel.innerHTML = '<option value="">无项目</option>';
      return;
    }
    projects.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id || p.name || '';
      opt.textContent = p.name || p.id || '';
      sel.appendChild(opt);
    });
    // Restore saved selection or default to first project
    if (saved && projects.some(p => (p.id || p.name || '') === saved)) {
      sel.value = saved;
      currentProject = saved;
    } else if (projects.length > 0) {
      sel.value = projects[0].id || projects[0].name || '';
      currentProject = projects[0].id || projects[0].name || '';
      localStorage.setItem('manage_project', currentProject);
    }
  } catch(e) {
    console.warn('[loadProjects]', e.message);
    sel.innerHTML = '<option value="">加载失败</option>';
  }
}


// ── API ───────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

// ── Load Settings ─────────────────────────────────────
async function loadSettings() {
  try {
    const d = await api('GET', '/api/settings');
    if (d.api_key) {
      document.getElementById('aiKeyField').value = d.api_key || '';
      document.getElementById('aiUrlField').value = d.api_url || '';
      document.getElementById('aiModelField').value = d.model || '';
      document.getElementById('aiTempField').value = d.temperature || 0.7;
      document.getElementById('manageStatus').textContent = 'Manage AI: 已连接';
      document.getElementById('manageStatus').classList.add('connected');
    }
  } catch(e) {
    console.warn('[loadSettings]', e.message);
  }
}

// ── Load Agents ───────────────────────────────────────
async function loadAgents() {
  try {
    const d = await api('GET', '/api/agents');
    agents = d.agents || [];
    renderAgents();
  } catch(e) {
    console.warn('[loadAgents]', e.message);
  }
}

// ── Render Agents ──────────────────────────────────────
function renderAgents() {
  const el = document.getElementById('agentList');
  if (!agents.length) {
    el.innerHTML = '<div class="log-empty" style="padding:16px">暂无 Agent</div>';
    return;
  }
  el.innerHTML = agents.map(a => {
    const cls = a.id || 'netops';
    const online = a.online !== false;
    return `<div class="agent-card" data-id="${a.id}">
      <div class="agent-icon ${cls}">${(a.name||'?')[0]}</div>
      <div class="agent-meta">
        <div class="agent-name">${a.name || a.id}</div>
        <div class="agent-status ${online ? 'online' : 'offline'}">${online ? '在线' : '离线'}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Event Listeners ───────────────────────────────────
function attachEventListeners() {
  const input = document.getElementById('msgInput');
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMsg();
    }
  });
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  document.getElementById('sendBtn').addEventListener('click', sendMsg);
}

// ── Send Message ──────────────────────────────────────
async function sendMsg() {
  const input = document.getElementById('msgInput');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';

  appendBubble('user', text);

  // 启动 Flow 流程追踪：协调层理解意图
  updateDualLayerFlowCard('coord', 'understanding', 10, '🔍 协调层正在理解需求...');
  showTyping();

  try {
    const d = await api('POST', '/api/manage/chat', {
      message: text,
      project_id: currentProject
    });

    hideTyping();

    if (d.error) {
      appendBubble('bot', '错误: ' + d.error);
      updateDualLayerFlowCard('coord', 'reporting', 50, '❌ 出错了');
      return;
    }

    // 显示 AI 回复
    appendBubble('bot', d.reply || '(无内容)');
    refreshDeviceList();  // 更新设备列表

    // Flow 完成：汇报用户
    setTimeout(() => {
      updateDualLayerFlowCard('coord', 'reporting', 95, '✅ 完成');
      setTimeout(() => {
        // 重置所有步骤到初始状态
        const all = document.querySelectorAll('.flow-step');
        all.forEach(el => el.classList.remove('active', 'done'));
      }, 2000);
    }, 500);

  } catch(e) {
    hideTyping();
    updateStreamingBubble(botBubbleId, '请求失败: ' + e.message);
    finishStreamingBubble(botBubbleId);
  }
}

// ── Message Bubbles ───────────────────────────────────
function appendBubble(role, text) {
  removeEmptyState();
  const area = document.getElementById('chatArea');
  const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const avatar = role === 'user' ? '👤' : '🤖';

  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  div.innerHTML = `<div class="msg-avatar">${avatar}</div>
    <div class="msg-content">
      <div class="bubble">${md2html(text)}</div>
      <div class="msg-time">${time}</div>
    </div>`;
  area.appendChild(div);
  scrollChat();
  // Persist to localStorage
  saveChatToStorage(role, text, time);
}

function showTyping() {
  removeEmptyState();
  const area = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.className = 'msg msg-bot';
  div.id = 'thinking';
  div.innerHTML = `<div class="msg-avatar">🤖</div>
    <div class="msg-content">
      <div class="bubble thinking">
        <div class="thinking-dot"></div>
        <div class="thinking-dot"></div>
        <div class="thinking-dot"></div>
      </div>
      <div class="msg-time">思考中...</div>
    </div>`;
  area.appendChild(div);
  scrollChat();
}

function hideTyping() {
  document.getElementById('thinking')?.remove();
}

function removeEmptyState() {
  document.querySelector('.empty-state')?.remove();
}

function scrollChat() {
  const area = document.getElementById('chatArea');
  area.scrollTop = area.scrollHeight;
}

// ── Markdown → HTML ────────────────────────────────────
function md2html(md) {
  if (!md) return '';
  let h = md;

  // Strip internal stage markers before rendering
  h = h.replace(/^\[\w+:\w+\]\s*/gm, '');  // [coord:understanding], [coord:planning], etc.
  h = h.replace(/^\[user\]\s*/i, '');
  h = h.replace(/^\[bot\]\s*/i, '');
  h = h.replace(/^\[AI\]\s*/i, '');

  // Code blocks
  h = h.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang}">${esc(code.trim())}</code></pre>`);

  // Headings
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold / italic
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');
  h = h.replace(/__(.+?)__/g, '<strong>$1</strong>');
  h = h.replace(/_(.+?)_/g, '<em>$1</em>');

  // Inline code
  h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // Blockquote
  h = h.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // Horizontal rule
  h = h.replace(/^---+$/gm, '<hr>');

  // Tables (basic)
  h = h.replace(/^(\|.+\|)\s*\n\|[-: |]+\|[\s\S]*?(?=\n\n|\n[^|]|$)/gm, m => {
    const rows = m.split('\n').filter(r => /^\|/.test(r));
    const sepIdx = rows.findIndex(r => /^\|[-: ]+\|/.test(r));
    if (sepIdx < 0) return m;
    const hdr = rows[0].split('|').slice(1,-1).map(c =>
      `<th>${c.trim().replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')}</th>`).join('');
    const body = rows.slice(sepIdx+1).map(row =>
      `<tr>${row.split('|').slice(1,-1).map(c =>
        `<td>${c.trim().replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>')}</td>`
      ).join('')}</tr>`
    ).join('');
    return `<table><thead><tr>${hdr}</tr></thead><tbody>${body}</tbody></table>`;
  });

  // Lists
  h = h.replace(/((?:^[-*] .+$\n?)+)/gm, m =>
    `<ul>${m.trim().split('\n').map(l => `<li>${l.replace(/^[-*] /,'')}</li>`).join('')}</ul>`);
  h = h.replace(/((?:^\d+\. .+$\n?)+)/gm, m =>
    `<ol>${m.trim().split('\n').map(l => `<li>${l.replace(/^\d+\. /,'')}</li>`).join('')}</ol>`);

  // Paragraphs and line breaks
  h = h.replace(/\n\n+/g, '</p><p>');
  h = `<p>${h}</p>`;
  h = h.replace(/<p><\/p>/g, '');
  h = h.replace(/(?!<br>)([^\n])\n([^\n])/g, '$1<br>$2');

  return h;
}

function esc(s) {
  if (!s && s !== 0) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}


// ── Settings Modal ────────────────────────────────────
function showSettings() {
  document.getElementById('settingsModal').classList.add('show');
}
function closeSettings() {
  document.getElementById('settingsModal').classList.remove('show');
}

async function testAI() {
  const el = document.getElementById('testResult');
  el.textContent = '测试中...';
  el.className = 'test-result';
  try {
    const d = await api('POST', '/api/settings/test', {
      api_url: document.getElementById('aiUrlField').value.trim(),
      api_key: document.getElementById('aiKeyField').value.trim(),
      model: document.getElementById('aiModelField').value.trim() || 'MiniMax-M2.5-highspeed'
    });
    if (d.ok) {
      el.textContent = '✅ 连接成功';
      el.className = 'test-result ok';
    } else {
      el.textContent = '❌ ' + (d.error || '失败');
      el.className = 'test-result fail';
    }
  } catch(e) {
    el.textContent = '❌ ' + e.message;
    el.className = 'test-result fail';
  }
}

async function saveSettings() {
  const settings = {
    api_key: document.getElementById('aiKeyField').value.trim(),
    api_url: document.getElementById('aiUrlField').value.trim(),
    model: document.getElementById('aiModelField').value.trim(),
    temperature: parseFloat(document.getElementById('aiTempField').value) || 0.7
  };
  try {
    await api('POST', '/api/settings', settings);
    closeSettings();
    await loadSettings();
  } catch(e) {
    alert('保存失败: ' + e.message);
  }
}

// ── Save Dropdown ─────────────────────────────────────
function toggleSaveMenu() {
  const menu = document.getElementById('saveMenu');
  const wasOpen = menu.classList.contains('open');
  // Close all first (in case of multiple clicks)
  menu.classList.remove('open');
  if (!wasOpen) {
    menu.classList.add('open');
    // Close on outside click
    setTimeout(() => {
      const closeHandler = function(e) {
        const btn = document.getElementById('saveBtn');
        if (!menu.contains(e.target) && !btn.contains(e.target)) {
          menu.classList.remove('open');
          document.removeEventListener('click', closeHandler);
        }
      };
      document.addEventListener('click', closeHandler);
    }, 0);
  }
}

// ── File Download Utility ──────────────────────────────
function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type: type || 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Execution Log Persistence ─────────────────────────
function saveLogToStorage(logs) {
  localStorage.setItem('manage_exec_log_' + currentProject, JSON.stringify(logs));
}

function loadLogFromStorage() {
  try {
    const raw = localStorage.getItem('manage_exec_log_' + currentProject);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function getDisplayLogs() {
  const el = document.getElementById('logList');
  const items = el.querySelectorAll('.log-item');
  const logs = [];
  items.forEach(item => {
    const t = item.querySelector('.log-time');
    const a = item.querySelector('.log-agent');
    const ac = item.querySelector('.log-action');
    const r = item.querySelector('.log-result');
    if (t && a && ac && r) {
      logs.push({
        time: t.textContent.trim(),
        agent: a.textContent.trim(),
        action: ac.textContent.trim(),
        result: r.textContent.trim()
      });
    }
  });
  return logs;
}

// ── Clear: Chat History ───────────────────────────────
function clearChatHistory() {
  if (!confirm('确定要清空当前项目的聊天记录吗？此操作不可撤销。')) return;
  fetch('/api/manage/clear_history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: currentProject })
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      // 清空前端显示
      const area = document.getElementById('chatArea');
      area.innerHTML = '<div class="empty-state"><div class="icon">🧠</div><p>聊天记录已清空<br>告诉我想做什么</p></div>';
      // 清空 localStorage 缓存
      localStorage.removeItem('manage_chat_' + currentProject);
      localStorage.removeItem('manage_exec_log_' + currentProject);
    } else {
      alert('清空失败');
    }
  }).catch(e => alert('清空失败: ' + e));
}

function gotoTopology() {
  // 跳转到 NetOps 拓扑编辑页面
  var proj = currentProject || 'default';
  window.open('http://192.168.32.72:9000/?proj=' + encodeURIComponent(proj), '_blank');
}

// ── Device List ──────────────────────────────────────
async function refreshDeviceList() {
  const wrap = document.getElementById('device-list-wrap');
  if (!wrap) return;
  try {
    const d = await api('GET', '/api/manage/topology?project_id=' + encodeURIComponent(currentProject));
    const nodes = d.topology && d.topology.nodes ? d.topology.nodes : [];
    const countEl = document.getElementById('device-count');
    if (countEl) countEl.textContent = '(' + nodes.length + '台)';
    if (nodes.length === 0) {
      wrap.innerHTML = '<div class="device-empty">暂无设备<br><span style="font-size:11px;color:#475569">告诉我想做什么，我来帮你规划网络</span></div>';
      return;
    }
    // 类型徽章
    function typeBadge(type) {
      var cls = {
        router: 'badge-router', switch: 'badge-switch',
        firewall: 'badge-firewall', server: 'badge-server',
        PC: 'badge-PC', cloud: 'badge-cloud'
      }[type] || 'badge-default';
      return '<span class="device-badge ' + cls + '">' + (type || 'unknown') + '</span>';
    }
    var html = '<table class="device-table"><thead><tr>' +
      '<th>名称</th><th>类型</th><th>IP</th>' +
      '</tr></thead><tbody>';
    nodes.forEach(function(n) {
      html += '<tr>' +
        '<td title="' + esc(n.label || n.id) + '">' + esc(n.label || n.id) + '</td>' +
        '<td class="type-cell">' + typeBadge(n.type) + '</td>' +
        '<td class="ip-cell" title="' + esc(n.ip || '-') + '">' + (n.ip || '-') + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;
  } catch(e) {
    wrap.innerHTML = '<div class="device-empty">加载失败</div>';
  }
}

// ── Save: Chat History ────────────────────────────────
function saveChatHistory() {
  toggleSaveMenu();
  const msgs = [];
  document.querySelectorAll('.msg').forEach(el => {
    const bubble = el.querySelector('.bubble');
    const time = el.querySelector('.msg-time');
    if (!bubble) return;
    const isUser = el.classList.contains('user');
    msgs.push({
      role: isUser ? 'user' : 'assistant',
      content: bubble.textContent.trim(),
      time: time ? time.textContent.trim() : ''
    });
  });

  if (!msgs.length) {
    alert('暂无聊天记录可导出');
    return;
  }

  const now = new Date().toLocaleString('zh-CN');
  const md = ['# 聊天记录\n', `> 导出时间：${now}  |  项目：${currentProject}\n`, '---', ''];
  msgs.forEach(m => {
    const label = m.role === 'user' ? '👤 用户' : '🤖 AI';
    md.push(`### ${label}  ${m.time}`);
    md.push(m.content);
    md.push('');
  });

  const filename = `chat_${currentProject}_${new Date().toISOString().slice(0,10)}.md`;
  downloadFile(filename, md.join('\n'), 'text/markdown');
}


// ── Add Log Entry ───────────────────────────────────
function addLog(agent, action, result) {
  const el = document.getElementById('logList');
  const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  // Remove empty state if present
  const empty = el.querySelector('.log-empty');
  if (empty) empty.remove();
  // Create log entry
  const div = document.createElement('div');
  div.className = 'log-item';
  div.innerHTML = '<div class="log-time">' + time + '</div>' +
    '<div class="log-agent">' + (agent || '') + '</div>' +
    '<div class="log-action">' + (action || '') + '</div>' +
    '<div class="log-result ' + (result === 'ok' || result === '成功' ? 'success' : 'fail') + '">' +
    (result === 'ok' || result === '成功' ? '成功' : '失败') + '</div>';
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
  // Persist to localStorage
  const logs = getDisplayLogs();
  saveLogToStorage(logs);
}

// ── Save: Execution Log ──────────────────────────────
function saveExecLog() {
  toggleSaveMenu();
  const logs = getDisplayLogs();
  if (!logs.length) {
    alert('暂无执行日志可导出');
    return;
  }

  const now = new Date().toLocaleString('zh-CN');
  const data = {
    project: currentProject,
    exportedAt: now,
    total: logs.length,
    successCount: logs.filter(l => l.result === '成功').length,
    failCount: logs.filter(l => l.result === '失败').length,
    logs: logs
  };

  const filename = `exec_log_${currentProject}_${new Date().toISOString().slice(0,10)}.json`;
  downloadFile(filename, JSON.stringify(data, null, 2), 'application/json');
}

// ── Save: Topology Snapshot ───────────────────────────
async function saveTopologySnapshot() {
  toggleSaveMenu();
  try {
    // Get current topology from NetOps
    const topoData = await api('GET', '/api/manage/topology?project_id=' + encodeURIComponent(currentProject));
    if (!topoData || topoData.nodeCount === undefined) {
      alert('获取拓扑失败');
      return;
    }
    const now = new Date().toLocaleString('zh-CN');
    const data = {
      project: currentProject,
      savedAt: now,
      nodeCount: topoData.nodeCount,
      edgeCount: topoData.edgeCount,
      topology: topoData
    };
    const filename = `topo_${currentProject}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.json`;
    downloadFile(filename, JSON.stringify(data, null, 2), 'application/json');
  } catch(e) {
    alert('保存拓扑快照失败: ' + e.message);
  }
}

// ── Clear: Execution Log ────────────────────────────
function clearExecLog() {
  toggleSaveMenu();
  localStorage.removeItem('manage_exec_log_' + currentProject);

// ── Update addLog to persist ────────────────────────
const _logStorageKey = () => 'manage_exec_log_' + currentProject;


// ── Update switchProject to load saved log ───────────

// ── Restore Execution Log on Init ──────────────────────
function restoreExecLogFromStorage() {
  const logs = loadLogFromStorage();
  const el = document.getElementById('logList');
  el.innerHTML = '';
  if (!logs.length) {
    el.innerHTML = '<div class="log-empty">暂无记录</div>';
    return;
  }
  logs.slice(0, 100).forEach(log => {
    const div = document.createElement('div');
    div.className = 'log-item';
    div.innerHTML = `<div class="log-time">${log.time || ''}</div>
      <div class="log-agent">${log.agent || ''}</div>
      <div class="log-action">${log.action || ''}</div>
      <div class="log-result ${log.result}">${log.result === 'ok' || log.result === '成功' ? '成功' : '失败'}</div>`;
    el.appendChild(div);
  });
}

// ── Project Switch ────────────────────────────────────
async function switchProject(id) {
  if (!id) return;
  currentProject = id;
  localStorage.setItem('manage_project', id);

  // 清空聊天区，从服务器加载历史（跨设备同步）
  const area = document.getElementById('chatArea');
  area.innerHTML = '';
  area.innerHTML = '<div class="empty-state"><div class="icon">🧠</div><p>加载中...</p></div>';
  await loadChatFromServer();
  // 如果没有消息，显示空状态
  if (!area.querySelector('.msg')) {
    area.innerHTML = '<div class="empty-state"><div class="icon">🧠</div><p>已切换到项目：' + esc(id) + '<br>告诉我想做什么</p></div>';
  }
  restoreExecLogFromStorage();
  refreshDeviceList();  // 刷新设备列表
  scrollChat();
}

// ── WebSocket Client ─────────────────────────────────
let ws = null;
let wsReconnectTimer = null;

function initWebSocket() {
  const wsUrl = 'ws://' + window.location.hostname + ':9012';
  console.log('[WS] Connecting to', wsUrl);
  
  try {
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      console.log('[WS] Connected');
      // 清除重连定时器
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
      // 发送心跳
      setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({type: 'ping'}));
        }
      }, 30000);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWSMessage(data);
      } catch(e) {
        console.error('[WS] Parse error:', e);
      }
    };
    
    ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };
    
    ws.onclose = () => {
      console.log('[WS] Disconnected, reconnecting in 3s...');
      wsReconnectTimer = setTimeout(initWebSocket, 3000);
    };
  } catch(e) {
    console.error('[WS] Connection error:', e);
    wsReconnectTimer = setTimeout(initWebSocket, 3000);
  }
}

/**
 * Update the dual-layer flow card for a specific layer and stage.
 * layer: 'coord' | 'netops'
 * stage: 'understanding' | 'planning' | 'dispatching' | 'reporting'
 *        | 'planning' | 'executing' | 'done'
 */
function updateDualLayerFlowCard(layer, stage, progress, message) {
  // Map stage name to step element ID
  const stepId = 'step-' + layer + '-' + stage;

  // Stage order for each layer
  const coordOrder = ['understanding', 'planning', 'dispatching', 'reporting'];
  const netopsOrder = ['planning', 'executing', 'done'];
  const order = layer === 'netops' ? netopsOrder : coordOrder;

  // Clear all steps for this layer first, then mark done/active
  order.forEach(s => {
    const el = document.getElementById('step-' + layer + '-' + s);
    if (el) {
      el.classList.remove('active', 'done');
    }
  });

  // Mark stages up to (but not including) current as done, current as active
  const idx = order.indexOf(stage);
  if (idx >= 0) {
    for (let i = 0; i < idx; i++) {
      const el = document.getElementById('step-' + layer + '-' + order[i]);
      if (el) el.classList.add('done');
    }
    const curEl = document.getElementById(stepId);
    if (curEl) curEl.classList.add('active');
  }
}

/**
 * Reset all flow card steps to idle.
 */
function resetFlowCards() {
  const allSteps = document.querySelectorAll('.flow-step');
  allSteps.forEach(el => {
    el.classList.remove('active', 'done');
  });
  const details = document.getElementById('exec-details');
  if (details) details.style.display = 'none';
  const taskId = document.getElementById('task-id');
  if (taskId) taskId.textContent = '';
}

/**
 * Append streaming text token.
 */
function appendMessageToken(token, done) {
  if (currentStreamingBubble) {
    appendToStreamingBubble(currentStreamingBubble, token);
  }
}

/**
 * Finalize message after done signal.
 */
function finalizeMessage(reply, taskId) {
  if (currentStreamingBubble) {
    finishStreamingBubble(currentStreamingBubble);
    currentStreamingBubble = null;
  }
  // Also finalize any flow card
  const allSteps = document.querySelectorAll('.flow-step');
  allSteps.forEach(el => el.classList.remove('active'));
}

/**
 * Append an AI message to the chat (for non-streaming responses like goal execute result).
 */
function appendAiMessage(content) {
  const chat = document.getElementById('chatMessages');
  if (!chat) return;
  const div = document.createElement('div');
  div.className = 'message bot-message';
  div.textContent = content;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function handleWSMessage(data) {
  console.log('[WS] Message:', data);

  // Token: append to streaming bubble
  if (data.type === 'token' && data.content) {
    if (currentStreamingBubble) {
      appendToStreamingBubble(currentStreamingBubble, data.content);
    }
  }

  // Stage update with layer: {type:"stage", layer:"coord", stage:"understanding", progress:10, message:"...", steps:[...]}
  if (data.type === 'stage' && data.layer) {
    updateDualLayerFlowCard(data.layer, data.stage, data.progress, data.message, data.steps);
    return;
  }

  // Legacy stage/progress (backward compat)
  if (data.type === 'stage' || data.type === 'progress') {
    const fullStage = (data.stage || data.substage || '') + ':' + (data.substage || '');
    _updateFlow(fullStage);
    const el = document.getElementById('workflowTracker');
    if (el && data.message) {
      let msgEl = el.querySelector('.flow-message');
      if (!msgEl) { msgEl = document.createElement('div'); msgEl.className = 'flow-message'; el.appendChild(msgEl); }
      msgEl.textContent = data.message;
    }
    return;
  }

  // Done
  if (data.type === 'done') {
    if (currentStreamingBubble) {
      finishStreamingBubble(currentStreamingBubble);
    }
    finalizeMessage(null, null);
    // 重置 flow 到 idle
    setTimeout(() => {
      const all = document.querySelectorAll('.flow-step');
      all.forEach(el => el.classList.remove('active', 'done'));
    }, 3000);
  }
}

function updateProgressUI(data) {
  const { stage, message, steps, result } = data;
  
  // 隐藏虚化面板，显示实化面板
  const frosted = document.getElementById('progressFrosted');
  const active = document.getElementById('progressPanelActive');
  if (frosted) frosted.style.display = 'none';
  if (active) active.style.display = 'block';
  
  // 阶段映射
  const stageMap = {
    'thinking': 'coord',
    'dispatch': 'coord',
    'executing': 'exec',
    'complete': null,
    'error': null
  };
  
  const currentStage = stageMap[stage];
  
  // 重置所有阶段
  ['user', 'coord', 'exec'].forEach(s => {
    const el = document.getElementById('stage-' + s);
    if (el) {
      el.classList.remove('active', 'done');
      const statusEl = el.querySelector('.stage-status');
      if (statusEl) statusEl.textContent = '○';
    }
  });
  
  // 高亮当前活跃阶段
  if (currentStage) {
    const activeEl = document.getElementById('stage-' + currentStage);
    if (activeEl) {
      activeEl.classList.add('active');
      const statusEl = activeEl.querySelector('.stage-status');
      if (statusEl) statusEl.textContent = '●';
    }
  }
  
  // 标记已完成阶段
  if (currentStage === 'exec') {
    const coordEl = document.getElementById('stage-coord');
    if (coordEl) {
      coordEl.classList.add('done');
      coordEl.classList.remove('active');
      const statusEl = coordEl.querySelector('.stage-status');
      if (statusEl) statusEl.textContent = '✓';
    }
  }
  if (currentStage === null && (stage === 'complete' || stage === 'error')) {
    ['user', 'coord', 'exec'].forEach(s => {
      const el = document.getElementById('stage-' + s);
      if (el) {
        el.classList.add('done');
        const statusEl = el.querySelector('.stage-status');
        if (statusEl) statusEl.textContent = '✓';
      }
    });
  }
  
  // 更新详情消息
  const detailEl = document.getElementById('progressDetailInline');
  if (detailEl) {
    detailEl.textContent = message;
    detailEl.style.display = message ? 'block' : 'none';
  }
  
  // 更新步骤列表
  const stepsEl = document.getElementById('progressStepsInline');
  if (stepsEl) {
    if (steps && steps.length > 0) {
      stepsEl.style.display = 'flex';
      stepsEl.innerHTML = steps.map(step => '<div class="step-item ' + step.status + '"><span class="step-icon">' + (step.status === 'done' ? '☑' : step.status === 'running' ? '◐' : '○') + '</span><span class="step-text">' + step.text + '</span></div>').join('');
    } else {
      stepsEl.style.display = 'none';
    }
  }
  
  // 完成或错误时延迟隐藏
  if (stage === 'complete' || stage === 'error') {
    setTimeout(() => {
      hideProgressPanel();
    }, stage === 'complete' ? 3000 : 5000);
  }
}

  if (frosted) frosted.style.display = 'block';
  if (active) active.style.display = 'none';
  
  // 重置状态
  ['user', 'coord', 'exec'].forEach(s => {
    const el = document.getElementById('stage-' + s);
    if (el) {
      el.classList.remove('active', 'done');
      const statusEl = el.querySelector('.stage-status');
      if (statusEl) statusEl.textContent = '○';
    }
  });
  
  const detailEl = document.getElementById('progressDetailInline');
  if (detailEl) {
    detailEl.textContent = '';
    detailEl.style.display = 'none';
  }
  
  const stepsEl = document.getElementById('progressStepsInline');
  if (stepsEl) stepsEl.innerHTML = '';
}

function hideProgressPanel() {
  const panel = document.getElementById('progressPanelRight');
  if (panel) panel.style.display = 'none';
  
  ['user', 'coord', 'exec'].forEach(s => {
    const el = document.getElementById('stage-' + s);
    if (el) {
      el.classList.remove('active', 'done');
      el.querySelector('.stage-status').textContent = '○';
    }
  });
  
  const detailEl = document.getElementById('progressDetailRight');
  if (detailEl) {
    detailEl.textContent = '';
    detailEl.classList.remove('show');
  }
  
  const stepsEl = document.getElementById('progressStepsRight');
  if (stepsEl) stepsEl.innerHTML = '';
}

function closeProgressIndicator() {
  const el = document.getElementById('progressIndicator');
  if (el) {
    el.remove();
  }
}

// ── Flow Card Controller ─────────────────────────────────
// ── Streaming Bubble Functions ───────────────────────────
let currentStreamingBubble = null;

function createStreamingBubble() {
  removeEmptyState();
  const area = document.getElementById('chatArea');
  const id = 'streaming-' + Date.now();
  const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  
  const div = document.createElement('div');
  div.className = 'msg msg-bot';
  div.id = id;
  div.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-content"><div class="bubble" style="min-width:60px;"></div><div class="bubble-time">' + time + '</div></div>';
  
  area.appendChild(div);
  scrollChat();
  
  currentStreamingBubble = id;
  return id;
}

function updateStreamingBubble(id, text) {
  const bubble = document.getElementById(id);
  if (bubble) {
    const contentDiv = bubble.querySelector('.bubble');
    if (contentDiv) {
      contentDiv.textContent = text;
    }
  }
  scrollChat();
}

function appendToStreamingBubble(id, token) {
  const bubble = document.getElementById(id);
  if (bubble) {
    const contentDiv = bubble.querySelector('.bubble');
    if (contentDiv) {
      contentDiv.textContent += token;
    }
  }
  scrollChat();
}

function finishStreamingBubble(id) {
  currentStreamingBubble = null;
  scrollChat();
}
