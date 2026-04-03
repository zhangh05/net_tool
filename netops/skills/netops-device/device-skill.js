/**
 * NetOps Device Skill - 设备操控技能
 * AI 通过这些函数连接和控制网络设备（Telnet/SSH）
 *
 * 使用方式：
 *   const result = await DeviceSkill.connect({ protocol, ip, port, user, password });
 *   const output = await DeviceSkill.send({ session_id, cmd });
 *   await DeviceSkill.close({ session_id });
 */

const DeviceSkill = (function() {

  // ── 会话存储 ──────────────────────────────────────────
  // 浏览器端会话缓存（实际连接信息在服务器端 PTY）
  const _sessions = {};

  // ── API 基础 ──────────────────────────────────────────
  const _apiBase = () => window.location.protocol + '//' + window.location.hostname + ':' + window.location.port;

  // ── 连接设备 ──────────────────────────────────────────
  /**
   * 建立 Telnet/SSH 会话
   * @param {object} opts
   * @param {string} opts.protocol - 'telnet' | 'ssh'
   * @param {string} opts.ip
   * @param {number} [opts.port] - 端口，默认 23(telnet) 或 22(ssh)
   * @param {string} [opts.user] - 用户名
   * @param {string} [opts.password] - 密码
   * @returns {Promise<{ok, session_id, prompt, error}>}
   */
  async function connect(opts) {
    const { protocol, ip, port, user, password } = opts;
    const sessPort = port || (protocol === 'ssh' ? 22 : 23);
    try {
      const resp = await fetch(_apiBase() + '/api/term/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: protocol, ip, port: sessPort, user: user || '', password: password || '' })
      });
      if (!resp.ok) {
        const err = await resp.text();
        return { ok: false, error: '连接失败: ' + err };
      }
      const data = await resp.json();
      const sid = data.id;

      // 等待首次提示符出现（最多 5 秒）
      const prompt = await _waitForPrompt(sid, 5000);

      _sessions[sid] = {
        id: sid, ip, port: sessPort, protocol,
        user, password,
        prompt: prompt || '',
        history: [],
        created_at: new Date().toISOString()
      };

      return { ok: true, session_id: sid, prompt: prompt || '' };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  }

  // ── 等待提示符 ────────────────────────────────────────
  /**
   * 等待设备返回提示符
   * @param {string} sid - session_id
   * @param {number} timeoutMs
   * @returns {Promise<string|null>} 提示符字符串
   */
  async function _waitForPrompt(sid, timeoutMs) {
    return new Promise((resolve) => {
      let timer;
      const wsUrl = 'ws://' + window.location.hostname + ':9011/ws/' + sid;
      let ws;
      let resolved = false;

      const done = (prompt) => {
        if (resolved) return;
        resolved = true;
        clearTimeout(timer);
        if (ws && ws.readyState === WebSocket.OPEN) ws.close();
        resolve(prompt);
      };

      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          timer = setTimeout(() => done(null), timeoutMs);
        };
        ws.onmessage = (evt) => {
          const d = evt.data;
          if (typeof d !== 'string') return;
          // 尝试从累积输出中提取提示符
          const prompt = _extractPrompt(d);
          if (prompt) {
            done(prompt);
          } else {
            // 还在等待，延长一点
            clearTimeout(timer);
            timer = setTimeout(() => done(null), 2000);
          }
        };
        ws.onerror = () => done(null);
      } catch (e) {
        done(null);
      }
    });
  }

  // ── 发送命令 ──────────────────────────────────────────
  /**
   * 发送一条命令，等待回显
   * @param {object} opts
   * @param {string} opts.session_id
   * @param {string} opts.cmd
   * @param {number} [opts.timeout_ms] - 等待输出的超时，默认 8000ms
   * @returns {Promise<{ok, output, prompt, error}>}
   */
  async function send(opts) {
    const { session_id, cmd, timeout_ms = 8000 } = opts;
    const sid = session_id;
    const sess = _sessions[sid];
    if (!sess) return { ok: false, error: '会话不存在或已关闭: ' + sid };

    return new Promise((resolve) => {
      let timer;
      let ws;
      let resolved = false;
      let output = '';

      var _waitTimer = null;
      const done = (result) => {
        if (resolved) return;
        resolved = true;
        if (_waitTimer) { clearTimeout(_waitTimer); _waitTimer = null; }
        clearTimeout(timer);
        if (ws && ws.readyState === WebSocket.OPEN) ws.close();
        if (result.prompt) {
          sess.prompt = result.prompt;
          sess.history.push({ cmd, output: result.output || '' });
        }
        resolve({ ok: !result.error, output: result.output || '', prompt: result.prompt || '' });
      };

      try {
        const wsUrl = 'ws://' + window.location.hostname + ':9011/ws/' + sid;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          // 发送命令（自动加回车）
          ws.send(JSON.stringify({ type: 'input', data: cmd + '\r' }));
          timer = setTimeout(() => done({ output, prompt: _extractPrompt(output) || sess.prompt, error: null }), timeout_ms);
        };

        ws.onmessage = (evt) => {
          if (typeof evt.data !== 'string') return;
          output += evt.data;
          // 检查是否出现了提示符（命令执行完了）
          const prompt = _extractPrompt(output);
          if (prompt) {
            // 去掉命令回显，只留输出
            const clean = _cleanOutput(cmd, output);
            done({ output: clean, prompt });
          }
        };

        ws.onerror = () => done({ error: 'WebSocket 错误', output });
      } catch (e) {
        done({ error: e.message, output });
      }
    });
  }

  // ── 期望特定输出 ──────────────────────────────────────
  /**
   * 等待特定模式出现（如 [Y/N] 确认提示）
   * @param {object} opts
   * @param {string} opts.session_id
   * @param {string} opts.pattern - 正则或字符串
   * @param {number} [opts.timeout_ms]
   * @returns {Promise<{ok, matched, error}>}
   */
  async function expect(opts) {
    const { session_id, pattern, timeout_ms = 5000 } = opts;
    const sess = _sessions[session_id];
    if (!sess) return { ok: false, error: '会话不存在: ' + session_id };

    const re = typeof pattern === 'string' ? new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') : pattern;

    return new Promise((resolve) => {
      let timer;
      let ws;
      let resolved = false;
      let output = '';

      const done = (matched) => {
        if (resolved) return;
        resolved = true;
        clearTimeout(timer);
        if (ws && ws.readyState === WebSocket.OPEN) ws.close();
        resolve({ ok: true, matched: !!matched });
      };

      try {
        ws = new WebSocket('ws://' + window.location.hostname + ':9011/ws/' + session_id);
        ws.onopen = () => { timer = setTimeout(() => done(false), timeout_ms); };
        ws.onmessage = (evt) => {
          if (typeof evt.data !== 'string') return;
          output += evt.data;
          if (re.test(output)) done(true);
        };
        ws.onerror = () => done(false);
      } catch (e) {
        done(false);
      }
    });
  }

  // ── 发送确认 ──────────────────────────────────────────
  /**
   * 发送确认（Y/N）
   * @param {string} session_id
   * @param {string} confirm - 'Y' 或 'N'
   */
  async function confirm(session_id, confirm = 'Y') {
    const wsUrl = 'ws://' + window.location.hostname + ':9011/ws/' + session_id;
    return new Promise((resolve) => {
      const ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'input', data: confirm + '\r' }));
        setTimeout(() => { ws.close(); resolve({ ok: true }); }, 500);
      };
      ws.onerror = () => resolve({ ok: false, error: 'ws error' });
    });
  }

  // ── 延时等待 ──────────────────────────────────────────
  /**
   * 等待一段时间
   * @param {number} ms
   */
  function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ── 关闭会话 ──────────────────────────────────────────
  /**
   * 关闭设备会话
   * @param {string} session_id
   */
  async function close(session_id) {
    const sess = _sessions[session_id];
    if (!sess) return { ok: false, error: '会话不存在' };

    try {
      // 先退出到用户视图再退出
      const wsUrl = 'ws://' + window.location.hostname + ':9011/ws/' + session_id;
      await new Promise((resolve) => {
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          // 发送 quit
          ws.send(JSON.stringify({ type: 'input', data: 'quit\r' }));
          setTimeout(() => {
            ws.send(JSON.stringify({ type: 'input', data: 'quit\r' }));
            setTimeout(() => {
              ws.send(JSON.stringify({ type: 'disconnect', data: '' }));
              ws.close();
              resolve();
            }, 500);
          }, 3000);  // 等3s 给设备处理时间
        };
      });
    } catch (e) {}

    delete _sessions[session_id];
    return { ok: true };
  }

  // ── 批量执行命令 ──────────────────────────────────────
  /**
   * 顺序执行多条命令
   * @param {string} session_id
   * @param {string[]} commands
   * @param {number} delay_ms - 每条命令之间的等待
   * @returns {Promise<{ok, results: [{cmd, output}]}>}
   */
  async function batch(session_id, commands, delay_ms = 500) {
    const results = [];
    for (const cmd of commands) {
      await wait(delay_ms);
      const r = await send({ session_id, cmd, timeout_ms: 10000 });
      results.push({ cmd, output: r.output, ok: r.ok });
    }
    return { ok: true, results };
  }

  // ── 辅助函数 ──────────────────────────────────────────
  function _extractPrompt(output) {
    if (!output) return null;
    const lines = output.split('\n');
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trimRight();
      // 华为/华三: [设备名] <设备名> [设备名-视图]
      const m = line.match(/^([<\[][\w\-\.\s]+[>\]])\s*$/) || line.match(/^([<\[][\w\-\.]+(?:-[\w\-\.]+)?[>\]])$/);
      if (m) return m[1];
      // 思科: 设备名> 设备名#
      const c = line.match(/^([\w\-\.]+(?:\(config[^\)]*\))?[#>])\s*$/);
      if (c) return c[1];
    }
    return null;
  }

  function _cleanOutput(cmd, output) {
    const lines = output.split('\n');
    // 去掉命令回显行（和命令相同的行）
    const clean = lines.filter(l => {
      const t = l.trim();
      return t !== cmd.trim() && t !== '' && !/^[<\[][\w\-\.\s]+[>\]]/.test(t.trimRight());
    });
    return clean.join('\n').trim();
  }

  // ── 注册到 OpSkills ──────────────────────────────────
  if (typeof OpSkills !== 'undefined') {
    OpSkills.device_connect = {
      name: 'device_connect',
      description: '建立 Telnet/SSH 会话连接到网络设备',
      params: ['device_id', 'protocol*', 'ip*', 'port', 'user', 'password'],
      async execute(op) {
        const r = await connect(op);
        return r;
      }
    };
    OpSkills.device_send = {
      name: 'device_send',
      description: '向已连接的设备发送一条命令并等待回显',
      params: ['session_id*', 'cmd*', 'timeout_ms'],
      async execute(op) {
        const r = await send(op);
        return r;
      }
    };
    OpSkills.device_expect = {
      name: 'device_expect',
      description: '等待设备返回特定输出（如 [Y/N] 确认提示）',
      params: ['session_id*', 'pattern*', 'timeout_ms'],
      async execute(op) {
        return await expect(op);
      }
    };
    OpSkills.device_confirm = {
      name: 'device_confirm',
      description: '向设备发送 Y 或 N 确认',
      params: ['session_id*', 'answer'],
      async execute(op) {
        return await confirm(op.session_id, op.answer || 'Y');
      }
    };
    OpSkills.device_wait = {
      name: 'device_wait',
      description: '等待一段时间（毫秒）',
      params: ['ms*'],
      async execute(op) {
        await wait(op.ms || 1000);
        return { ok: true };
      }
    };
    OpSkills.device_close = {
      name: 'device_close',
      description: '关闭设备会话',
      params: ['session_id*'],
      async execute(op) {
        return await close(op.session_id);
      }
    };
    OpSkills.device_batch = {
      name: 'device_batch',
      description: '批量执行多条命令',
      params: ['session_id*', 'commands*', 'delay_ms'],
      async execute(op) {
        return await batch(op.session_id, op.commands, op.delay_ms || 500);
      }
    };
  }

  // ── 暴露 API ──────────────────────────────────────────
  return {
    connect, send, expect, confirm, wait, close, batch,
    getSession: (sid) => _sessions[sid] || null,
    listSessions: () => Object.keys(_sessions)
  };

})();

// 兼容全局引用
window.DeviceSkill = DeviceSkill;
