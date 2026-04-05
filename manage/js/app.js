/**
 * Manage — Coordination Platform
 * app.js — Main Application Logic
 */

// ── State ─────────────────────────────────────────────
let agents = [];
let currentProject = localStorage.getItem('manage_project') || 'default';
let pendingTask = null;   // { steps, results }
let stepResults = {};     // stepIndex -> { ok, result, error }
let _chatKey = () => 'manage_chat_' + (currentProject || 'default');

// ── Workflow Tracker State ──────────────────────────────
// Stages: idle | thinking | planning | waiting_confirm | executing | done | error
const WORKFLOW_STAGES = [
  { key: 'thinking',      icon: '💭', label: '理解需求',   color: '#8b949e' },
  { key: 'planning',      icon: '📡', label: '调用 NetOps', color: '#8b949e' },
  { key: 'waiting_confirm', icon: '🔒', label: '等待确认',   color: '#8b949e' },
  { key: 'executing',     icon: '⚡', label: '执行操作',   color: '#8b949e' },
  { key: 'done',          icon: '✅', label: '完成',       color: '#8b949e' },
];
let _workflow = { stage: 'idle', error: null };

function setWorkflowStage(stage, error) {
  _workflow = { stage, error: error || null };
  renderWorkflowTracker();
}

function renderWorkflowTracker() {
  const el = document.getElementById('workflowTracker');
  if (!el) return;

  // Idle state - show placeholder
  if (_workflow.stage === 'idle') {
    el.innerHTML = `<div class="wf-empty">💭 告诉我想做什么</div>`;
    return;
  }

  const stages = [
    { key: 'thinking',        icon: '💭', label: '理解需求' },
    { key: 'planning',        icon: '📡', label: '调用 NetOps' },
    { key: 'waiting_confirm', icon: '🔒', label: '等待确认' },
    { key: 'executing',       icon: '⚡', label: '执行操作' },
    { key: 'done',            icon: '✅', label: '完成' },
  ];
  const stageIdx = { thinking: 0, planning: 1, waiting_confirm: 2, executing: 3, done: 4 };
  const currentStageIdx = stageIdx[_workflow.stage] ?? -1;

  let html = `<div class="wf-title">流程追踪</div>`;

  stages.forEach((s, i) => {
    const isDone = i < currentStageIdx || _workflow.stage === 'done';
    const isActive = i === currentStageIdx;
    const isPending = i > currentStageIdx && _workflow.stage !== 'done' && _workflow.stage !== 'error';

    let cls = 'wf-step';
    let icon = s.icon;
    let labelStyle = '';
    if (isDone) { cls += ' wf-done'; labelStyle = 'color:#10b950;'; icon = '✅'; }
    else if (isActive) { cls += ' wf-active'; labelStyle = 'color:#3b82f6;font-weight:600;'; }
    else if (_workflow.stage === 'error') { cls += ' wf-error'; labelStyle = 'color:#ef4444;'; }
    else { cls += ' wf-pending'; labelStyle = 'color:#9aa3b5;'; }

    // Connector line between steps
    if (i > 0) {
      const lineDone = i <= currentStageIdx || _workflow.stage === 'done';
      html += `<div class="wf-connector ${lineDone ? 'wf-connector-done' : ''}"></div>`;
    }

    html += `<div class="${cls}">
      <div class="wf-icon">${icon}</div>
      <div class="wf-label" style="${labelStyle}">${s.label}</div>
    </div>`;
  });

  // Error message
  if (_workflow.stage === 'error' && _workflow.error) {
    html += `<div class="wf-error-msg">❌ ${esc(_workflow.error)}</div>`;
  }

  el.innerHTML = html;
}

// Call workflow stage at key points in the app
function _workflowThinking()  { setWorkflowStage('thinking'); }
function _workflowPlanning()  { setWorkflowStage('planning'); }
function _workflowWaiting()  { setWorkflowStage('waiting_confirm'); }
function _workflowExecuting(){ setWorkflowStage('executing'); }
function _workflowDone()    { setWorkflowStage('done'); setTimeout(() => setWorkflowStage('idle'), 3000); }
function _workflowError(msg){ setWorkflowStage('error', msg); }
function _workflowReset()   { setWorkflowStage('idle'); }

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

function loadChatFromStorage() {
  try {
    const key = _chatKey();
    const raw = localStorage.getItem(key);
    if (!raw) return;
    const msgs = JSON.parse(raw);
    if (!msgs.length) return;
    const area = document.getElementById('chatArea');
    // Remove empty state if present
    removeEmptyState();
    msgs.forEach(m => {
      const div = document.createElement('div');
      div.className = `msg msg-${m.role}`;
      div.innerHTML = `<div class="msg-avatar">${m.role === 'user' ? '👤' : '🤖'}</div>
        <div class="msg-content">
          <div class="bubble">${md2html(m.text || '')}</div>
          <div class="msg-time">${m.time || ''}</div>
        </div>`;
      area.appendChild(div);
    });
    scrollChat();
  } catch(e) {}
}

// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadProjects();   // 加载 NetOps 项目列表
  await loadSettings();
  await loadAgents();
  renderAgents();
  attachEventListeners();
  loadChatFromStorage();  // 恢复聊天记录
  restoreExecLogFromStorage();  // 恢复执行日志
  renderWorkflowTracker();  // 初始化流程追踪
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
  _workflowThinking();  // 开始理解需求
  showTyping();

  try {
    const d = await api('POST', '/api/manage/chat', {
      message: text,
      project_id: currentProject
    });

    hideTyping();

    if (d.error) {
      appendBubble('bot', '错误: ' + d.error);
      return;
    }

    appendBubble('bot', d.reply || '');

    if (d.steps && d.steps.length > 0) {
      pendingTask = { steps: d.steps, reply: d.reply };
      // Auto-exec: backend already ran steps and returned results
      // Manual-exec: results are null, will be filled by execSteps()
      stepResults = {};
      window._pendingGoalSummary = d.goal_summary || null;
      window._pendingTopoChange = d.topology_change || null;
      // Pass results if auto_exec=true (already executed), null if pending confirmation
      renderTaskCard(d.steps, d.results || null, d.auto_exec);
    } else if (d.summary) {
      renderSummary(d.summary);
    }

  } catch(e) {
    hideTyping();
    appendBubble('bot', '请求失败: ' + e.message);
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

// ── Task Card ──────────────────────────────────────────
function renderTaskCard(steps, results, autoExec) {
  const cardId = 'tc-' + Date.now();
  const area = document.getElementById('chatArea');

  const total = steps.length;
  let doneCount = results ? results.filter(r => r && r.ok).length : 0;

  // Detect goal mode
  const isGoalMode = steps.some(s => s.goal_mode);
  const goalSummary = window._pendingGoalSummary;
  const topoChange = window._pendingTopoChange;

  const card = document.createElement('div');
  card.className = 'task-card';
  card.id = cardId;

  // Build topology change summary HTML
  const topoChangeHtml = topoChange
    ? `<div class="tc-topo-change">
        ${(topoChange['新增设备'] || []).length ? `<div>➕ ${(topoChange['新增设备'] || []).join('、')}</div>` : ''}
        ${(topoChange['新增连线'] || []).length ? `<div>🔗 ${(topoChange['新增连线'] || []).join('、')}</div>` : ''}
        ${(topoChange['删除设备'] || []).length ? `<div>➖ ${(topoChange['删除设备'] || []).join('、')}</div>` : ''}
        ${(topoChange['删除连线'] || []).length ? `<div>✂️ ${(topoChange['删除连线'] || []).join('、')}</div>` : ''}
        ${topoChange['IP分配'] ? `<div>🌐 IP：${esc(String(topoChange['IP分配']))}</div>` : ''}
        ${topoChange['端口分配'] ? `<div>🔌 端口：${esc(String(topoChange['端口分配']))}</div>` : ''}
       </div>`
    : '';

  card.innerHTML = `
    <div class="tc-header" onclick="toggleCard('${cardId}')">
      <span class="tc-title">📋 执行计划 ${isGoalMode ? '⚡ Goal模式' : ''} ${autoExec ? '(自动执行中)' : '— 待确认'}</span>
      <div class="tc-progress">
        <span class="tc-done-count">${doneCount}/${total}</span>
        <div class="tc-progress-bar"><div class="tc-progress-fill" style="width:${doneCount/total*100}%"></div></div>
      </div>
    </div>
    ${goalSummary || topoChange ? `<div class="tc-goal-summary">
      ${goalSummary ? `<div class="tc-goal-text">🎯 目标：${esc(goalSummary)}</div>` : ''}
      ${topoChangeHtml}
    </div>` : ''}
    <div class="tc-body" id="${cardId}-body">
      ${steps.map((s, i) => buildStepHTML(cardId, i, s, results ? results[i] : null)).join('')}
    </div>
    ${!autoExec ? `<div class="tc-actions">
      <button class="btn btn-primary" onclick="execSteps('${cardId}')">▶ 执行全部</button>
      <button class="btn btn-ghost" onclick="cancelSteps('${cardId}')">取消</button>
    </div>` : ''}
  `;

  area.appendChild(card);
  scrollChat();
  pendingTask.cardId = cardId;
}

function buildStepHTML(cardId, i, step, result) {
  const num = i + 1;
  const status = getStepStatus(step, result);
  const icon = STATUS_CONFIG[status]?.icon || '⏳';
  const statusLabel = STATUS_CONFIG[status]?.label || '等待';
  const isGoal = step.goal_mode;

  // Goal mode: show reason instead of raw params
  let paramsHtml;
  if (isGoal) {
    const reason = step.reason || step.label || 'NetOps 自动规划执行步骤';
    paramsHtml = `<div style="font-size:12px;color:#39c5ff;margin-bottom:6px;">💡 ${esc(reason)}</div>
      <div style="font-size:11px;color:var(--text-muted);">NetOps 将自动计算坐标、端口、IP</div>`;
  } else if (Object.keys(step.params || {}).length > 0) {
    paramsHtml = `<table class="tc-param-table">
        ${Object.entries(step.params || {}).map(([k,v]) =>
          `<tr><td>${k}</td><td>${esc(String(v))}</td></tr>`).join('')}
       </table>`;
  } else {
    paramsHtml = '<div style="font-size:12px;color:var(--text-muted)">无参数</div>';
  }

  const resultHtml = result
    ? `<div class="tc-step-result">${formatResult(result)}</div>`
    : '';

  const detailId = `${cardId}-step-${i}`;

  return `
    <div class="tc-step" onclick="toggleStep('${detailId}')">
      <div class="tc-step-num" style="background:${STATUS_CONFIG[status]?.bg};color:${STATUS_CONFIG[status]?.color}">${num}</div>
      <div class="tc-step-info">
        <div class="tc-step-agent">${isGoal ? '⚡ netops' : '['+step.agent+']'}</div>
        <div class="tc-step-label">${step.action}</div>
      </div>
      <div class="tc-step-status" style="color:${STATUS_CONFIG[status]?.color}">${icon} ${statusLabel}</div>
    </div>
    <div class="tc-step-detail" id="${detailId}">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">${isGoal ? '执行说明' : '参数'}</div>
      ${paramsHtml}
      ${resultHtml}
    </div>`;
}

const STATUS_CONFIG = {
  done:    { icon: '✅', color: '#3fb950', bg: '#3fb95022', label: '成功' },
  fail:    { icon: '❌', color: '#f85149', bg: '#f8514922', label: '失败' },
  confirm: { icon: '🔒', color: '#d29922', bg: '#d2992222', label: '待确认' },
  auto:    { icon: '⚡', color: '#39c5ff', bg: '#39c5ff22', label: '自动' },
  running: { icon: '🔄', color: '#39c5ff', bg: '#39c5ff22', label: '执行中' },
  pending: { icon: '⏳', color: '#8b949e', bg: '#8b949e22', label: '等待' },
};

function getStepStatus(step, result) {
  if (result) return result.ok ? 'done' : 'fail';
  if (step.confirm === false) return 'auto';
  if (step.confirm) return 'confirm';
  return 'pending';
}

function formatResult(result) {
  if (!result) return '';
  if (result.error) return `❌ 错误: ${esc(result.error)}`;
  if (result.topology) {
    const t = result.topology;
    return `✅ 拓扑更新：${t.nodes?.length || 0} 台设备，${t.edges?.length || 0} 条连线`;
  }
  if (typeof result === 'object') {
    const lines = Object.entries(result).slice(0, 5).map(([k, v]) =>
      `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`
    ).join('\n');
    return esc(lines);
  }
  return esc(String(result));
}

// ── Toggle Functions ───────────────────────────────────
function toggleCard(cardId) {
  const body = document.getElementById(cardId + '-body');
  if (body) body.style.display = body.style.display === 'none' ? '' : 'none';
}

function toggleStep(detailId) {
  const el = document.getElementById(detailId);
  if (!el) return;
  el.classList.toggle('open');
}

// ── Execute Steps ─────────────────────────────────────
async function execSteps(cardId) {
  _workflowExecuting();  // 开始执行
  const { steps } = pendingTask;
  const body = document.getElementById(cardId + '-body');
  if (!body) return;

  const isGoalMode = steps.some(s => s.goal_mode);

  // ── Goal Mode: call /api/manage/goal/execute ──
  if (isGoalMode) {
    // Build plan from steps (NetOps format)
    const plan = steps.map((s, i) => ({
      step: i + 1,
      action: s.action,
      reason: s.reason || s.label || '',
      params: s.params || {}
    }));

    // Mark all steps as running
    for (let i = 0; i < steps.length; i++) {
      updateStepStatus(`${cardId}-step-${i}`, 'running', '');
    }

    try {
      const d = await api('POST', '/api/manage/goal/execute', {
        project_id: currentProject,
        plan: plan
      });

      const results = d.results || [];
      // Update each step status
      for (let i = 0; i < steps.length; i++) {
        const r = results[i] || {};
        const ok = r.ok !== false;
        stepResults[i] = { ok, result: r, error: r.error };
        updateStepStatus(`${cardId}-step-${i}`, ok ? 'done' : 'fail', stepResults[i]);
        addLog('netops', steps[i].action, ok ? 'ok' : 'fail');
      }
      updateCardProgress(cardId, results.filter(r => r.ok !== false).length, steps.length);

      if (d.topology) {
        _workflowDone();
        renderSummary('✅ 执行完成，拓扑已更新');
      }

    } catch(e) {
      // All steps failed
      for (let i = 0; i < steps.length; i++) {
        stepResults[i] = { ok: false, error: e.message };
        updateStepStatus(`${cardId}-step-${i}`, 'fail', stepResults[i]);
      }
    }
    return;
  }

  // ── Traditional Mode: step-by-step ──
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const detailId = `${cardId}-step-${i}`;

    updateStepStatus(detailId, 'running', '');

    try {
      const d = await api('POST', '/api/agent/execute', {
        agent: step.agent,
        action: step.action,
        params: step.params || {},
        project_id: currentProject
      });

      const ok = d.ok !== false;
      stepResults[i] = { ok, result: d.result, error: d.error };

      updateStepStatus(detailId, ok ? 'done' : 'fail', stepResults[i]);
      updateCardProgress(cardId, Object.keys(stepResults).length, steps.length);

      addLog(step.agent, step.action, ok ? 'ok' : 'fail');

    } catch(e) {
      stepResults[i] = { ok: false, error: e.message };
      updateStepStatus(detailId, 'fail', stepResults[i]);
      addLog(step.agent, step.action, 'fail');
    }
  }

  // Generate summary
  const summaryD = await api('POST', '/api/manage/summary', {
    results: Object.entries(stepResults).map(([i, r]) => ({ step: Number(i)+1, ...r })),
    project_id: currentProject
  });

  if (summaryD.summary) {
    _workflowDone();
    renderSummary(summaryD.summary);
  } else {
    _workflowDone();
  }
}

function updateStepStatus(detailId, status, result) {
  const el = document.getElementById(detailId);
  if (!el) return;
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const statusEl = el.previousElementSibling?.querySelector('.tc-step-status');
  if (statusEl) statusEl.textContent = cfg.icon + ' ' + cfg.label;
  if (result !== '') {
    const existingResult = el.querySelector('.tc-step-result');
    if (existingResult) existingResult.remove();
    if (result && result.result || result?.error) {
      const resultDiv = document.createElement('div');
      resultDiv.className = 'tc-step-result';
      resultDiv.textContent = result.error
        ? '❌ 错误: ' + result.error
        : formatResult(result.result);
      el.appendChild(resultDiv);
    }
  }
}

function updateCardProgress(cardId, done, total) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const fill = card.querySelector('.tc-progress-fill');
  const count = card.querySelector('.tc-done-count');
  if (fill) fill.style.width = (done / total * 100) + '%';
  if (count) count.textContent = `${done}/${total}`;
}

function cancelSteps(cardId) {
  document.getElementById(cardId)?.remove();
  pendingTask = null;
  stepResults = {};
}

// ── Summary ───────────────────────────────────────────
function renderSummary(text) {
  removeEmptyState();
  const area = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.className = 'summary-panel';
  div.innerHTML = `<h3>📊 执行汇报</h3>${md2html(text)}`;
  area.appendChild(div);
  scrollChat();
}

// ── Execution Log ─────────────────────────────────────

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
  const el = document.getElementById('logList');
  el.innerHTML = '<div class="log-empty">暂无记录</div>';
}

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
function switchProject(id) {
  if (!id) return;
  currentProject = id;
  localStorage.setItem('manage_project', id);

  // Clear chat area and reload
  const area = document.getElementById('chatArea');
  area.innerHTML = '';
  // Restore saved chat for new project
  const raw = localStorage.getItem('manage_chat_' + id);
  if (raw) {
    try {
      const msgs = JSON.parse(raw);
      msgs.forEach(m => {
        const div = document.createElement('div');
        div.className = `msg msg-${m.role}`;
        div.innerHTML = `<div class="msg-avatar">${m.role === 'user' ? '👤' : '🤖'}</div>
          <div class="msg-content">
            <div class="bubble">${md2html(m.text || '')}</div>
            <div class="msg-time">${m.time || ''}</div>
          </div>`;
        area.appendChild(div);
      });
    } catch(e) {}
  }
  if (!area.querySelector('.msg')) {
    area.innerHTML = `<div class="empty-state">
      <div class="icon">🧠</div>
      <p>已切换到项目：${esc(id)}<br>告诉我想做什么</p>
    </div>`;
  }
  pendingTask = null;
  stepResults = {};
  restoreExecLogFromStorage();
  scrollChat();
}
