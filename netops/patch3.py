#!/usr/bin/env python3
"""Patch script v3 - precise insertion of network ops."""
with open('/root/nettool/netops/index.html', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# The pattern - device properties template after p-desc, before save button
# Using bytes to avoid escaping issues
old_bytes = (
    b"      <div class=\"prop-group\">\n"
    b"        <div class=\"prop-label\">\\xe6\\x8f\\x8f\\xe8\\xaf\\x9d</div>\n"  # 描述
    b"        <input class=\"prop-input\" id=\"p-desc\" value=\"${d.desc||''}\" placeholder=\"\\xe8\\xae\\xbe\\xe5\\x80\\x99\\xe6\\x8f\\x8f\\xe8\\xaf\\x9d\" oninput=\"upd('desc',this.value)\">\n"
    b"      </div>\n"
    b"      <div class=\"prop-group\">\n"
    b"        <button onclick=\"saveNodeProps()\""
)

new_bytes = (
    b"      <div class=\"prop-group\">\n"
    b"        <div class=\"prop-label\">\\xe6\\x8f\\x8f\\xe8\\xaf\\x9d</div>\n"
    b"        <input class=\"prop-input\" id=\"p-desc\" value=\"${d.desc||''}\" placeholder=\"\\xe8\\xae\\xbe\\xe5\\x80\\x99\\xe6\\x8f\\x8f\\xe8\\xaf\\x9d\" oninput=\"upd('desc',this.value)\">\n"
    b"      </div>\n"
    b"      <div class=\"prop-group\">\n"
    b"        <div class=\"prop-label\">\\xe7\\xbd\\x91\\xe7\\xbb\\x9c\\xe6\\x93\\x8d\\xe4\\xbd\\x9c</div>\n"  # 网络操作
    b"        <div style=\"display:flex;gap:6px;margin-bottom:6px;\">\n"
    b"          <button onclick=\"openNetopsPing()\" style=\"flex:1;background:#fef2f2;color:#ef4444;border:1px solid #fca5a5;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;\">\n"
    b"            <i class=\"fa-solid fa-circle\" style=\"font-size:8px\"></i> Ping\n"
    b"          </button>\n"
    b"        </div>\n"
    b"        <div id=\"netops-ping-result\" class=\"anchor-result\" style=\"display:none;margin-bottom:6px;\"></div>\n"
    b"        <div style=\"display:flex;gap:6px;align-items:center;margin-bottom:4px;\">\n"
    b"          <button onclick=\"toggleSshTelForm('telnet')\" id=\"btn-telnet-toggle\" style=\"flex:1;background:#f0fdf4;color:#22c55e;border:1px solid #86efac;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;\">\n"
    b"            <i class=\"fa-solid fa-circle\" style=\"font-size:8px\"></i> Telnet\n"
    b"          </button>\n"
    b"        </div>\n"
    b"        <div id=\"telnet-form\" style=\"display:none;background:#f0fdf4;border:1px solid #86efac;border-radius:7px;padding:8px;margin-bottom:6px;\">\n"
    b"          <div style=\"display:flex;gap:4px;margin-bottom:4px;\">\n"
    b"            <input class=\"prop-input\" id=\"t-ip\" placeholder=\"IP\" style=\"flex:2;font-size:11px;padding:4px 6px;\">\n"
    b"            <input class=\"prop-input\" id=\"t-port\" placeholder=\"\\xe7\\xab\\xaf\\xe5\\x8f\\xa3\" value=\"23\" style=\"flex:1;font-size:11px;padding:4px 6px;\">\n"  # 端口
    b"          </div>\n"
    b"          <input class=\"prop-input\" id=\"t-user\" placeholder=\"\\xe7\\x94\\xa8\\xe6\\x88\\xb7\\xe5\\x90\\x8d\\xef\\xbc\\x88\\xe5\\x8f\\xaf\\xe9\\x80\\x89\\xef\\xbc\\x89\" style=\"width:100%;font-size:11px;padding:4px 6px;margin-bottom:4px;\">\n"  # 用户名（可选）
    b"          <input class=\"prop-input\" id=\"t-pass\" type=\"password\" placeholder=\"\\xe5\\xaf\\x86\\xe7\\xa0\\x81\\xef\\xbc\\x88\\xe5\\x8f\\xaf\\xe9\\x80\\x89\\xef\\xbc\\x89\" style=\"width:100%;font-size:11px;padding:4px 6px;margin-bottom:6px;\">\n"  # 密码（可选）
    b"          <button onclick=\"doConnectTelnet()\" style=\"width:100%;background:#22c55e;color:#fff;border:none;border-radius:6px;padding:7px;font-size:12px;font-weight:600;cursor:pointer;\">\\xe8\\xbf\\x9e\\xe6\\x8e\\xa5</button>\n"  # 连接
    b"        </div>\n"
    b"        <div style=\"display:flex;gap:6px;align-items:center;margin-bottom:4px;\">\n"
    b"          <button onclick=\"toggleSshTelForm('ssh')\" id=\"btn-ssh-toggle\" style=\"flex:1;background:#eff6ff;color:#3b82f6;border:1px solid #93c5fd;border-radius:7px;padding:8px 4px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:4px;\">\n"
    b"            <i class=\"fa-solid fa-circle\" style=\"font-size:8px\"></i> SSH\n"
    b"          </button>\n"
    b"        </div>\n"
    b"        <div id=\"ssh-form\" style=\"display:none;background:#eff6ff;border:1px solid #93c5fd;border-radius:7px;padding:8px;margin-top:4px;\">\n"
    b"          <div style=\"display:flex;gap:4px;margin-bottom:4px;\">\n"
    b"            <input class=\"prop-input\" id=\"s-ip\" placeholder=\"IP\" style=\"flex:2;font-size:11px;padding:4px 6px;\">\n"
    b"            <input class=\"prop-input\" id=\"s-port\" placeholder=\"\\xe7\\xab\\xaf\\xe5\\x8f\\xa3\" value=\"22\" style=\"flex:1;font-size:11px;padding:4px 6px;\">\n"
    b"          </div>\n"
    b"          <input class=\"prop-input\" id=\"s-user\" placeholder=\"\\xe7\\x94\\xa8\\xe6\\x88\\xb7\\xe5\\x90\\x8d\" value=\"root\" style=\"width:100%;font-size:11px;padding:4px 6px;margin-bottom:4px;\">\n"  # 用户名
    b"          <input class=\"prop-input\" id=\"s-pass\" type=\"password\" placeholder=\"\\xe5\\xaf\\x86\\xe7\\xa0\\x81\\xef\\xbc\\x88\\xe5\\x8f\\xaf\\xe9\\x80\\x89\\xef\\xbc\\x89\" style=\"width:100%;font-size:11px;padding:4px 6px;margin-bottom:6px;\">\n"
    b"          <button onclick=\"doConnectSSH()\" style=\"width:100%;background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:7px;font-size:12px;font-weight:600;cursor:pointer;\">\\xe8\\xbf\\x9e\\xe6\\x8e\\xa5</button>\n"
    b"        </div>\n"
    b"      </div>\n"
    b"      <div class=\"prop-group\">\n"
    b"        <button onclick=\"saveNodeProps()\""
)

pos = content.encode('utf-8').find(old_bytes)
if pos >= 0:
    print(f"Found pattern at byte position {pos}")
    # Decode to know where to split
    content_decoded = content
    content_bytes = content.encode('utf-8')
    
    # Find the end of the old pattern (save button)
    # The new content is the old up to old_bytes, then new_bytes, then from after old_bytes
    new_content = content_bytes[:pos] + new_bytes + content_bytes[pos + len(old_bytes):]
    
    with open('/root/nettool/netops/index.html', 'wb') as f:
        f.write(new_content)
    print(f"Done! File size: {len(new_content)} bytes (was {len(content_bytes)})")
else:
    print("Pattern not found!")
    print("Trying to find the p-desc context...")
    idx = content.find("p-desc")
    print(f"p-desc at: {idx}")
    if idx > 0:
        print(repr(content[idx-50:idx+300]))
