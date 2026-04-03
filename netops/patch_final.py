#!/usr/bin/env python3
"""Final clean patch for NetOps toolbox and zone support."""
with open('/root/nettool/netops/index.html', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

changes = 0

# 1. Fix the malformed 'n' line at end of JS - replace literal '\n' with empty
old_end = "    if (ip) _fillSshTelForms(ip);\n  }, 100);\n};\n'\\n'"
new_end = "    if (ip) _fillSshTelForms(ip);\n  }, 100);\n};\n"
if old_end in content:
    content = content.replace(old_end, new_end)
    print("1. Fixed malformed end of JS ✓")
    changes += 1
else:
    print("1. Malformed end pattern not found - trying alternate")
    # Try finding the actual content
    idx = content.find("_fillSshTelForms(ip)")
    if idx > 0:
        end_idx = content.find("</script>", idx)
        print(f"  Found _fillSshTelForms at {idx}, </script> at {end_idx}")
        print(f"  Content around end: {repr(content[end_idx-50:end_idx+30])}")

# 2. Add zone support to makeShapeSVG
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
    print("2. Added zone support to makeShapeSVG ✓")
    changes += 1
else:
    print("2. makeShapeSVG pattern not found (may already have zone support)")

# 3. Update placeShape for zones
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
    print("3. placeShape pattern not found (may already have zone support)")
    # Check current placeShape
    idx = content.find('function placeShape')
    if idx > 0:
        print(f"   Current: {repr(content[idx:idx+200])}")

# 4. Replace ellipse/rectangle with zone in edit menu
old_menu = """        <div style="position:relative;">
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
        <div class="edit-menu-divider"></div>"""

new_menu = """        <div style="position:relative;">
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
        <div class="edit-menu-divider"></div>"""

if old_menu in content:
    content = content.replace(old_menu, new_menu)
    print("4. Replaced shape menu with zone button ✓")
    changes += 1
else:
    print("4. Edit menu pattern not found")
    # Check if zone already exists
    if 'startPlaceShape(' in content:
        idx = content.find("startPlaceShape('")
        print(f"   Found startPlaceShape at: {idx}")
        print(f"   {repr(content[idx:idx+200])}")

print(f"\nTotal changes: {changes}/4")
with open('/root/nettool/netops/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("File written.")
