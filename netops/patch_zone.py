#!/usr/bin/env python3
"""Add zone support to makeShapeSVG and placeShape."""
with open('/root/nettool/netops/index.html', 'r') as f:
    content = f.read()

# Fix makeShapeSVG - add zone support
# Find the function and replace its body
start = content.find("function makeShapeSVG(type, color, w, h, label, bg, fg) {")
end = content.find("\n  }", start) + 4  # closing }
old_func = content[start:end]
print("Found makeShapeSVG at:", start, "length:", len(old_func))
print("Content:", repr(old_func[:200]))

# The new body
new_body = """function makeShapeSVG(type, color, w, h, label, bg, fg) {
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

# Actually we need to replace using the exact byte pattern
# Since the content uses \' for escaped quotes, let's try
old_pattern = "var labelSvg = '';\n    if (label) {"
if old_pattern in content:
    print("Found old_pattern at:", content.find(old_pattern))
else:
    print("old_pattern not found!")
    # Find what IS there
    idx = content.find("var labelSvg")
    print("Context:", repr(content[idx:idx+100]))
