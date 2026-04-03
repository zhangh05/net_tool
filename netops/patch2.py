#!/usr/bin/env python3
"""Patch script v2 - insert network ops into device properties template."""
with open('/root/nettool/netops/index.html', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

print(f"File size: {len(content)} chars")

# FIND: The device properties template has after p-desc input:
# </div>
# <div class="prop-group">
#   <button onclick="saveNodeProps()"
# INSERT: Network ops section before the save button

# The pattern to find: after description input, before save button
old = """      <div class="prop-group">
        <div class="prop-label">描述</div>
        <input class="prop-input" id="p-desc" value="${d.desc||''}" placeholder="设备描述" oninput="upd('desc',this.value)">
      </div>
      <div class="prop-group">
        <button onclick="saveNodeProps()" style="width:100%;background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:10px;font-size:13px;font-weight:600;cursor:pointer">
          <i class="fa-solid fa-check"></i> 保存修改
        </button>
      </div>
    `;
  }

  saveNodeProps ="""

new = """      <div class="prop-group">
        <div class="prop-label">描述</div>
        <input class="prop-input" id="p-desc" value="${d.desc||''}" placeholder="设备描述" oninput="upd('desc',this.value)">
      </div>
      <div class="prop-group">
        <div class="prop-label">网络操作</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <button onclick="openNetopsPing()" style="flex:1;background:#fef2f2;color:#ef4444;border:1px solid #fca5a5;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;">
            <i class="fa-solid fa-circle" style="font-size:8px"></i> Ping
          </button>
        </div>
        <div id="netops-ping-result" class="anchor-result" style="display:none;margin-bottom:6px;"></div>
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
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;">
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
      <div class="prop-group">
        <button onclick="saveNodeProps()" style="width:100%;background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:10px;font-size:13px;font-weight:600;cursor:pointer">
          <i class="fa-solid fa-check"></i> 保存修改
        </button>
      </div>
    `;
  }

  saveNodeProps ="""

if old in content:
    content = content.replace(old, new)
    print("1. Inserted network ops HTML into device template ✓")
    changes = 1
else:
    print("1. Pattern not found in device template")
    # Let's see what's actually there
    idx = content.find("设备描述")
    if idx > 0:
        print(repr(content[idx:idx+500]))
    changes = 0

# 2. Check makeShapeSVG - need to add zone support
old_make = """  function makeShapeSVG(type, color, w, h, label, bg, fg) {
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
  }"""

new_make = """  function makeShapeSVG(type, color, w, h, label, bg, fg) {
    var bgFill = (bg === 'transparent' || !bg) ? 'fill="none"' : 'fill="' + bg + '"';
    var txtColor = fg || '#1f2937';
    var labelSvg = '';
    var isZone = (type === 'zone');
    if (label) {
      var escaped = label.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      if (isZone) {
        labelSvg = '<text x="8" y="20" font-size="13" font-weight="bold" fill="' + txtColor + '" font-family="sans-serif">' + escaped + '</text>';
      } else {
        labelSvg = '<text x="' + (w/2) + '" y="' + (h/2) + '" text-anchor="middle" dominant-baseline="middle" font-size="12" fill="' + txtColor + '" font-family="sans-serif">' + escaped + '</text>';
      }
    }
    var strokeDash = isZone ? 'stroke-dasharray="8,4" ' : '';
    var strokeWidth = '2';
    var shape;
    if (type === 'ellipse') {
      shape = '<ellipse cx="' + (w/2) + '" cy="' + (h/2) + '" rx="' + (w/2-2) + '" ry="' + (h/2-2) + '" ' + bgFill + ' stroke="' + color + '" stroke-width="' + strokeWidth + '" ' + strokeDash + '/>';
    } else {
      shape = '<rect x="2" y="2" width="' + (w-4) + '" height="' + (h-4) + '" ' + bgFill + ' stroke="' + color + '" stroke-width="' + strokeWidth + '" rx="6" ' + strokeDash + '/>';
    }
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' + shape + labelSvg + '</svg>');
  }"""

if old_make in content:
    content = content.replace(old_make, new_make)
    print("2. Updated makeShapeSVG for zones ✓")
    changes += 1
else:
    print("2. makeShapeSVG pattern not found")
    # Check if zone support already exists
    if 'isZone' in content and 'zone' in content[content.find('function makeShapeSVG'):content.find('function makeShapeSVG')+2000]:
        print("   Zone support may already exist")

# 3. Update placeShape
old_place = """  function placeShape(x, y, type, color) {
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
  }"""

new_place = """  function placeShape(x, y, type, color) {
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
  }"""

if old_place in content:
    content = content.replace(old_place, new_place)
    print("3. Updated placeShape for zones ✓")
    changes += 1
else:
    print("3. placeShape pattern not found")
    # Check if zone version exists
    if 'isZone' in content and 'placeShape' in content:
        p_idx = content.find('function placeShape')
        print("   Current placeShape:", repr(content[p_idx:p_idx+200]))

# 4. Make sure the JS functions are at the end of the script (not duplicated)
if 'function _getNodeIp()' in content:
    # Check if it's already in the right place (near end of script)
    idx = content.find('function _getNodeIp()')
    end_idx = content.rfind('</script>')
    if idx < end_idx:
        # It's in the middle, which is good (it's where it should be)
        print("4. Network ops JS functions already present ✓")
    else:
        print("4. _getNodeIp found but location unusual")
else:
    # Functions not found - need to add them
    print("4. Network ops JS functions NOT found - need to add")

# 5. Check if connector dots are hidden
if '.connector-dot' in content:
    dot_idx = content.find('.connector-dot {')
    if dot_idx > 0:
        print("5. Connector dot CSS found at:", dot_idx)
        print("   ", repr(content[dot_idx:dot_idx+100]))
else:
    print("5. No connector-dot CSS found")

print(f"\nTotal changes: {changes}")
with open('/root/nettool/netops/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("File written.")
