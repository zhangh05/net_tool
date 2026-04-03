#!/usr/bin/env python3
"""Patch script for NetOps toolbox panel and zone shapes."""

with open('/root/nettool/netops/index.html', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

changes = 0

# 1. Hide the edge-mode select dropdown (连线类型下拉)
old = '''    <select id="edge-mode" onchange="setEdgeMode(this.value)" style="padding:5px 8px;border-radius:6px;border:1px solid #374151;background:#f3f4f6;color:#374151;font-size:12px;cursor:pointer;">
      <option value="bezier" selected>曲线连线</option>
      <option value="straight">直线连线</option>
      <option value="orthogonal">正交连线</option>
    </select>'''
new = '''    <select id="edge-mode" onchange="setEdgeMode(this.value)" style="display:none;padding:5px 8px;border-radius:6px;border:1px solid #374151;background:#f3f4f6;color:#374151;font-size:12px;cursor:pointer;">
      <option value="bezier" selected>曲线连线</option>
      <option value="straight">直线连线</option>
      <option value="orthogonal">正交连线</option>
    </select>'''
if old in content:
    content = content.replace(old, new)
    print("1. Hidden edge-mode dropdown ✓")
    changes += 1
else:
    print("1. edge-mode dropdown NOT FOUND")

# 2. Hide connector dots CSS
old = '''  .connector-dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; background: #3b82f6; border: 2px solid #0d1117; z-index: 100; transform: translate(-50%,-50%); transition: transform 0.15s, opacity 0.15s; opacity: 0; }
  .connector-dot.visible { opacity: 1; }
  .connector-dot:hover { transform: translate(-50%,-50%) scale(1.6) !important; background: #60a5fa; }'''
new = '''  .connector-dot { position: absolute; width: 14px; height: 14px; border-radius: 50%; background: #3b82f6; border: 2px solid #fff; z-index: 100; transform: translate(-50%,-50%); opacity: 0 !important; pointer-events: none; box-shadow: 0 0 6px rgba(59,130,246,0.5); }'''
if old in content:
    content = content.replace(old, new)
    print("2. Hidden connector dots ✓")
    changes += 1
else:
    print("2. connector-dot CSS NOT FOUND")

# 3. Disable mouseover connector dots (connections work by clicking nodes)
old = '''cy.on('mouseover', 'node', function(e) { showConnectors(e.target.id()); });
cy.on('mouseout', 'node', function(e) {
  setTimeout(function() {
    var dots = document.querySelectorAll('.connector-dot');
    var hovered = Array.from(dots).some(function(d) { return d.matches(':hover'); });
    if (!hovered) hideConnectors();
  }, 100);
});
cy.on('pan zoom', function() { updateConnectorPositions(); });'''
new = '''// Connector dots disabled - connections work by clicking nodes directly
cy.on('mouseover', 'node', function(e) { });
cy.on('mouseout', 'node', function(e) { });
cy.on('pan zoom', function() { });'''
if old in content:
    content = content.replace(old, new)
    print("3. Disabled connector dots ✓")
    changes += 1
else:
    print("3. connector dots mouseover/out NOT FOUND")

# 4. Add zone to shape place options - replace ellipse/rectangle buttons with zone button
old = '''        <div style="position:relative;">
          <button class="edit-menu-item" onclick="startPlaceShape('ellipse')">
            <i class="fa-regular fa-circle" style="font-size:14px"></i> 椭圆
            <span style="margin-left:auto;color:#9ca3af;font-size:11px;">▸</span>
            <div class="edit-submenu">
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('ellipse','#ef4444')">🔴 红色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('ellipse','#f59e0b')">🟡 黄色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('ellipse','#10b981')">🟢 绿色</div>
            </div>
          </button>
        </div>
        <div style="position:relative;">
          <button class="edit-menu-item" onclick="startPlaceShape('rectangle')">
            <i class="fa-regular fa-square" style="font-size:14px"></i> 方形
            <span style="margin-left:auto;color:#9ca3af;font-size:11px;">▸</span>
            <div class="edit-submenu">
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('rectangle','#ef4444')">🔴 红色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('rectangle','#f59e0b')">🟡 黄色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('rectangle','#10b981')">🟢 绿色</div>
            </div>
          </button>
        </div>
        <div class="edit-menu-divider"></div>'''
new = '''        <div style="position:relative;">
          <button class="edit-menu-item" onclick="startPlaceShape('zone')">
            <i class="fa-regular fa-square" style="font-size:14px"></i> 区域（虚线边框）
            <span style="margin-left:auto;color:#9ca3af;font-size:11px;">▸</span>
            <div class="edit-submenu">
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('zone','#ef4444')">🔴 红色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('zone','#f59e0b')">🟡 黄色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('zone','#10b981')">🟢 绿色</div>
              <div class="edit-submenu-item" onclick="event.stopPropagation(); startPlaceShape('zone','#3b82f6')">🔵 蓝色</div>
            </div>
          </button>
        </div>
        <div class="edit-menu-divider"></div>'''
if old in content:
    content = content.replace(old, new)
    print("4. Replaced shape buttons with zone button ✓")
    changes += 1
else:
    print("4. Shape buttons NOT FOUND")

# 5. Update makeShapeSVG to support zone styling
old = '''  function makeShapeSVG(type, color, w, h, label, bg, fg) {
    var bgFill = (bg === 'transparent' || !bg) ? 'fill="none"' : 'fill="' + bg + '"';
    var txtColor = fg || '#1f2937';
    var labelSvg = '';
    if (label) {
      var escaped = label.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      labelSvg = '<text x="' + (w/2) + '" y="' + (h/2) + '" text-anchor="middle" dominant-baseline="middle" font-size="12" fill="' + txtColor + '" font-family="sans-serif">' + escaped + '</text>';
    }
    var shape;
    if (type === 'ellipse') {
      shape = '<ellipse cx="' + (w/2) + '" cy="' + (h/2) + '" rx="' + (w/2-2) + '" ry="' + (h/2-2) + '" ' + bgFill + ' stroke="' + color + '" stroke-width="2"/>';
    } else {
      shape = '<rect x="2" y="2" width="' + (w-4) + '" height="' + (h-4) + '" ' + bgFill + ' stroke="' + color + '" stroke-width="2" rx="4"/>';
    }
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' + shape + labelSvg + '</svg>');
  }'''
new = '''  function makeShapeSVG(type, color, w, h, label, bg, fg) {
    var bgFill = (bg === 'transparent' || !bg) ? 'fill="none"' : 'fill="' + bg + '"';
    var txtColor = fg || '#1f2937';
    var labelSvg = '';
    var isZone = (type === 'zone');
    if (label) {
      var escaped = label.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      if (isZone) {
        // Zone: label at top-left, bold
        labelSvg = '<text x="8" y="20" font-size="13" font-weight="bold" fill="' + txtColor + '" font-family="sans-serif">' + escaped + '</text>';
      } else {
        labelSvg = '<text x="' + (w/2) + '" y="' + (h/2) + '" text-anchor="middle" dominant-baseline="middle" font-size="12" fill="' + txtColor + '" font-family="sans-serif">' + escaped + '</text>';
      }
    }
    var strokeDash = isZone ? 'stroke-dasharray="8,4" ' : '';
    var strokeWidth = isZone ? '2' : '2';
    var shape;
    if (type === 'ellipse') {
      shape = '<ellipse cx="' + (w/2) + '" cy="' + (h/2) + '" rx="' + (w/2-2) + '" ry="' + (h/2-2) + '" ' + bgFill + ' stroke="' + color + '" stroke-width="' + strokeWidth + '" ' + strokeDash + '/>';
    } else {
      shape = '<rect x="2" y="2" width="' + (w-4) + '" height="' + (h-4) + '" ' + bgFill + ' stroke="' + color + '" stroke-width="' + strokeWidth + '" rx="6" ' + strokeDash + '/>';
    }
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' + shape + labelSvg + '</svg>');
  }'''
if old in content:
    content = content.replace(old, new)
    print("5. Updated makeShapeSVG for zones ✓")
    changes += 1
else:
    print("5. makeShapeSVG NOT FOUND")

# 6. Update placeShape for zone default size and styling
old = '''  function placeShape(x, y, type, color) {
    var id = 'shape-' + Date.now();
    var w = 120, h = 80;
    var svgUri = makeShapeSVG(type, color, w, h, '', 'transparent', '#1f2937');
    cy.add({
      group: 'nodes',
      data: { id: id, type: type, label: '', shapeColor: color, w: w, h: h, isShape: true },
      css: {
        'width': w, 'height': h,
        'background-image': svgUri,
        'background-fit': 'contain',
        'background-width': w, 'background-height': h,
        'background-opacity': 0,
        'label': '',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'text-halign': 'center',
        'shape': 'rectangle',
        'text-events': 'no', 'events': 'yes',
      },
      position: { x: x, y: y }
    }).lower();
    saveUndoState && saveUndoState();
    autoSaveProject && autoSaveProject();
    addOpLog && addOpLog('human', '添加形状：' + (type === 'ellipse' ? '椭圆' : '方形'));
    toast('✓ 已添加形状');
  }'''
new = '''  function placeShape(x, y, type, color) {
    var id = 'shape-' + Date.now();
    var isZone = (type === 'zone');
    var w = isZone ? 420 : 120;
    var h = isZone ? 260 : 80;
    var bg = isZone ? 'rgba(59,130,246,0.06)' : 'transparent';
    var svgUri = makeShapeSVG(type, color, w, h, '', bg, '#1f2937');
    cy.add({
      group: 'nodes',
      data: { id: id, type: type, label: '', shapeColor: color, w: w, h: h, isShape: true, isZone: isZone },
      css: {
        'width': w, 'height': h,
        'background-image': svgUri,
        'background-fit': 'contain',
        'background-width': w, 'background-height': h,
        'background-opacity': 0,
        'label': '',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'text-halign': 'center',
        'shape': 'rectangle',
        'text-events': 'no', 'events': 'yes',
      },
      position: { x: x, y: y }
    });
    saveUndoState && saveUndoState();
    autoSaveProject && autoSaveProject();
    addOpLog && addOpLog('human', '添加区域：' + (type === 'zone' ? '区域' : type === 'ellipse' ? '椭圆' : '方形'));
    toast('✓ 已添加区域');
  }'''
if old in content:
    content = content.replace(old, new)
    print("6. Updated placeShape for zones ✓")
    changes += 1
else:
    print("6. placeShape NOT FOUND")

# 7. Replace network operations section with simplified Ping + Telnet + SSH forms
old = '''      <div class="prop-group">
        <div class="prop-label">网络操作</div>
        <div style="display:flex;gap:6px;">
          <button onclick="openNetopsPing()" style="flex:1;background:#fef2f2;color:#ef4444;border:1px solid #fca5a5;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> Ping
          </button>
          <button onclick="openNetopsTelnet()" style="flex:1;background:#f0fdf4;color:#22c55e;border:1px solid #86efac;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> Telnet
          </button>
          <button onclick="openNetopsSSH()" style="flex:1;background:#eff6ff;color:#3b82f6;border:1px solid #93c5fd;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> SSH
          </button>
        </div>
      </div>
      <div class="prop-group" id="anchor-ops-section" style="display:none">
        <div class="anchor-section-title"><i class="fa-solid fa-anchor"></i> 锚点设备</div>
        <div id="anchor-info-loading" class="anchor-loading">⏳ 加载锚点数据...</div>
        <div id="anchor-info-content"></div>
        <div id="anchor-no-anchor-msg" style="display:none">
          <div class="anchor-pending-add">⚠️ 该 IP 尚未注册到锚点</div>
          <button class="anchor-btn anchor-btn-add" id="anchor-add-btn" onclick="doAddToAnchor()">
            <i class="fa-solid fa-plus"></i> 加入锚点
          </button>
        </div>
        <div class="anchor-btns" id="anchor-action-btns" style="display:none">
          <button class="anchor-btn anchor-btn-ping" id="anchor-ping-btn" onclick="doAnchorPing()">
            <i class="fa-solid fa-circle" style="font-size:7px"></i> Ping
          </button>
          <button class="anchor-btn anchor-btn-term" onclick="openNetopsTerminal()">
            <i class="fa-solid fa-terminal"></i> 终端
          </button>
          <button class="anchor-btn anchor-btn-backup" id="anchor-backup-btn" onclick="doAnchorBackup()">
            <i class="fa-solid fa-floppy-disk"></i> 备份
          </button>
        </div>
        <div id="anchor-result" class="anchor-result"></div>
      </div>
      <div class="prop-group">
        <button onclick="openNetopsTerminal()" style="width:100%;background:#1a1a2e;color:#e0e0e0;border:1px solid #3b82f6;border-radius:7px;padding:9px;font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;">
          <i class="fa-solid fa-terminal" style="color:#3b82f6"></i> 🖥️ 终端
        </button>
      </div>
      <div class="prop-group">'''

# The new network ops section
new_section = '''      <div class="prop-group">
        <div class="prop-label">网络操作</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <button onclick="openNetopsPing()" style="flex:1;background:#fef2f2;color:#ef4444;border:1px solid #fca5a5;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> Ping
          </button>
        </div>
        <div id="netops-ping-result" class="anchor-result" style="display:none;margin-bottom:6px;"></div>

        <!-- Telnet -->
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;">
          <button onclick="toggleSshTelForm('telnet')" id="btn-telnet-toggle" style="flex:1;background:#f0fdf4;color:#22c55e;border:1px solid #86efac;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> Telnet
          </button>
        </div>
        <div id="telnet-form" style="display:none;background:#f0fdf4;border:1px solid #86efac;border-radius:7px;padding:8px;margin-bottom:6px;">
          <div style="display:flex;gap:4px;margin-bottom:4px;">
            <input class="prop-input" id="t-ip" placeholder="IP" style="flex:2;font-size:11px;padding:4px 6px;">
            <input class="prop-input" id="t-port" placeholder="端口" value="23" style="flex:1;font-size:11px;padding:4px 6px;">
          </div>
          <input class="prop-input" id="t-user" placeholder="用户名（可选）" style="width:100%;font-size:11px;padding:4px 6px;margin-bottom:4px;">
          <input class="prop-input" id="t-pass" type="password" placeholder="密码（可选）" style="width:100%;font-size:11px;padding:4px 6px;margin-bottom:6px;">
          <button onclick="doConnectTelnet()" style="width:100%;background:#22c55e;color:#fff;border:none;border-radius:6px;padding:7px;font-size:12px;font-weight:600;cursor:pointer;">连接</button>
        </div>

        <!-- SSH -->
        <div style="display:flex;gap:6px;align-items:center;">
          <button onclick="toggleSshTelForm('ssh')" id="btn-ssh-toggle" style="flex:1;background:#eff6ff;color:#3b82f6;border:1px solid #93c5fd;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> SSH
          </button>
        </div>
        <div id="ssh-form" style="display:none;background:#eff6ff;border:1px solid #93c5fd;border-radius:7px;padding:8px;margin-top:4px;">
          <div style="display:flex;gap:4px;margin-bottom:4px;">
            <input class="prop-input" id="s-ip" placeholder="IP" style="flex:2;font-size:11px;padding:4px 6px;">
            <input class="prop-input" id="s-port" placeholder="端口" value="22" style="flex:1;font-size:11px;padding:4px 6px;">
          </div>
          <input class="prop-input" id="s-user" placeholder="用户名" value="root" style="width:100%;font-size:11px;padding:4px 6px;margin-bottom:4px;">
          <input class="prop-input" id="s-pass" type="password" placeholder="密码（可选）" style="width:100%;font-size:11px;padding:4px 6px;margin-bottom:6px;">
          <button onclick="doConnectSSH()" style="width:100%;background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:7px;font-size:12px;font-weight:600;cursor:pointer;">连接</button>
        </div>
      </div>
      <div class="prop-group">'''

if old in content:
    content = content.replace(old, new_section)
    print("7. Replaced network ops section ✓")
    changes += 1
else:
    print("7. Network ops section NOT FOUND")
    # Try to find anchor section
    idx = content.find('anchor-ops-section')
    if idx > 0:
        print(f"   Found anchor-ops-section at index {idx}")

# 8. Add JS functions for Ping, Telnet, SSH at the end of script
js_additions = '''
// ── Network Ops Functions ──────────────────────────────────────
function _getNodeIp() {
  var node = cy && cy.$(':selected')[0];
  var ip = node && node.data('ip');
  if (!ip) {
    var ipInput = document.getElementById('p-ip');
    ip = ipInput ? ipInput.value.trim() : '';
  }
  return ip;
}

function _fillSshTelForms(ip) {
  if (!ip) return;
  var tIp = document.getElementById('t-ip');
  var sIp = document.getElementById('s-ip');
  if (tIp && !tIp.value) tIp.value = ip;
  if (sIp && !sIp.value) sIp.value = ip;
}

function toggleSshTelForm(type) {
  var ip = _getNodeIp();
  if (type === 'telnet') {
    var el = document.getElementById('telnet-form');
    var wasOpen = el.style.display !== 'none';
    el.style.display = wasOpen ? 'none' : 'block';
    document.getElementById('ssh-form').style.display = 'none';
    if (!wasOpen && ip) { document.getElementById('t-ip').value = ip; }
  } else {
    var el = document.getElementById('ssh-form');
    var wasOpen = el.style.display !== 'none';
    el.style.display = wasOpen ? 'none' : 'block';
    document.getElementById('telnet-form').style.display = 'none';
    if (!wasOpen && ip) { document.getElementById('s-ip').value = ip; }
  }
}

function doConnectTelnet() {
  var ip = document.getElementById('t-ip').value.trim();
  var port = document.getElementById('t-port').value.trim() || 23;
  var user = document.getElementById('t-user').value.trim();
  var pass = document.getElementById('t-pass').value;
  if (!ip) { toast('请输入 IP 地址'); return; }
  toast('正在连接 telnet ' + ip + ':' + port + ' ...');
  _doOpenTermXterm('telnet', ip, parseInt(port), user, pass);
}

function doConnectSSH() {
  var ip = document.getElementById('s-ip').value.trim();
  var port = document.getElementById('s-port').value.trim() || 22;
  var user = document.getElementById('s-user').value.trim() || 'root';
  var pass = document.getElementById('s-pass').value;
  if (!ip) { toast('请输入 IP 地址'); return; }
  toast('正在 SSH ' + ip + ':' + port + ' ...');
  _doOpenTermXterm('ssh', ip, parseInt(port), user, pass);
}

function openNetopsPing() {
  var ip = _getNodeIp();
  if (!ip) { toast('请先设置 IP 地址'); return; }
  _fillSshTelForms(ip);
  var resultEl = document.getElementById('netops-ping-result');
  if (resultEl) { resultEl.textContent = '⏳ 正在 Ping ' + ip + ' ...'; resultEl.className = 'anchor-result'; resultEl.style.display = 'block'; }
  fetch('/api/ping?ip=' + encodeURIComponent(ip))
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (d.success) {
        if (resultEl) { resultEl.textContent = '✅ Ping 成功\\n' + (d.output||'').split('\\n').slice(-4).join('\\n'); resultEl.className = 'anchor-result show'; }
        else toast('✅ Ping 成功: ' + ip);
      } else {
        if (resultEl) { resultEl.textContent = '❌ Ping 失败: ' + (d.output||'目标不可达').split('\\n').slice(-3).join('\\n'); resultEl.className = 'anchor-result show error'; }
        else toast('❌ Ping 失败: ' + ip);
      }
    })
    .catch(function(e){
      if (resultEl) { resultEl.textContent = '❌ 错误: ' + e.message; resultEl.className = 'anchor-result show error'; }
      else toast('❌ Ping 错误: ' + e.message);
    });
}

// Hook showProps to auto-fill IP in ssh/telnet forms
var _origShowProps_anchor = showProps;
showProps = function(ele) {
  _origShowProps_anchor(ele);
  setTimeout(function() {
    var ip = ele && ele.data && ele.data('ip');
    if (ip) _fillSshTelForms(ip);
  }, 100);
};
'''

# Find the </script> at the end and insert JS before it
script_end = content.rfind('</script>')
if script_end > 0:
    content = content[:script_end] + js_additions + '\\n' + content[script_end:]
    print("8. Added network ops JS functions ✓")
    changes += 1
else:
    print("8. </script> NOT FOUND at expected location")

print(f"\\nTotal changes: {changes}/8")
with open('/root/nettool/netops/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("File written.")