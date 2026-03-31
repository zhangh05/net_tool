#!/usr/bin/env python3
# NetTool - Application bootstrapping tool
# Usage: python3 newapp.py <appname> [--title T] [--port N] [--desc D]
import os, sys, json, re
from datetime import datetime

NETTOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVER_TPL = (
    '#!/usr/bin/env python3\n'
    '# {{title}} - NetTool app  port: {{port}}\n'
    'import os, http.server, socketserver, json, mimetypes\n'
    'from urllib.parse import unquote\n'
    '\n'
    'PORT = {{port}}\n'
    'BASE = os.path.dirname(os.path.abspath(__file__))\n'
    '\n'
    'class H(http.server.BaseHTTPRequestHandler):\n'
    '    def log(self, *a): print(f"[{self.log_date_time_string()}]", *a)\n'
    '    def reply(self, code, ct, body):\n'
    '        b = body if isinstance(body, bytes) else body.encode()\n'
    '        self.send_response(code)\n'
    '        self.send_header("Content-Type", ct)\n'
    '        self.send_header("Content-Length", len(b))\n'
    '        self.end_headers()\n'
    '        self.wfile.write(b)\n'
    '    def do_GET(self):\n'
    '        path = unquote(self.path.split("?")[0])\n'
    '        # Portal handles static (/appname/static/...) - app server gets paths WITHOUT prefix\n'
    '        if path in ("/", "", "/index.html"):\n'
    '            with open(os.path.join(BASE, "index.html"), encoding="utf-8") as f:\n'
    '                self.reply(200, "text/html; charset=utf-8", f.read())\n'
    '            return\n'
    '        if path == "/api/info":\n'
    '            self.reply(200, "application/json", json.dumps({"name":"{{title}}","version":"1.0.0","app":"{{app}}","status":"ok"}))\n'
    '            return\n'
    '        self.reply(404, "text/plain", "Not Found")\n'
    '\n'
    'if __name__ == "__main__":\n'
    '    socketserver.TCPServer.allow_reuse_address = True\n'
    '    print("{{title}} running on http://0.0.0.0:" + str(PORT))\n'
    '    socketserver.TCPServer(("0.0.0.0", PORT), H).serve_forever()\n'
)

def render_manifest(app, title, desc, port, emoji):
    return json.dumps({
        "name": title,
        "version": "1.0.0",
        "description": desc,
        "path": app + "/",
        "port": port,
        "icon_emoji": emoji,
        "order": 99,
        "author": "NetTool"
    }, ensure_ascii=False, indent=2) + "\n"

def to_emoji(app):
    m = {
        "ipcalc":"🔢","subnet":"🔢","ip":"🔢",
        "config":"📋","backup":"💾","bak":"💾",
        "monitor":"📊","status":"📊",
        "topo":"🌐","netops":"🌐","network":"🌐",
        "user":"👥","admin":"👥","manage":"👥",
        "learn":"📖","study":"📖",
        "calc":"🧮","tool":"🛠","tools":"🛠",
        "vlan":"🔀","route":"🔀",
        "log":"📝","ticket":"🎫"
    }
    for k,v in m.items():
        if k in app.lower(): return v
    return "📦"

def main():
    argv = sys.argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__); sys.exit(0)
    app = argv[0]
    if not re.match(r'^[a-z][a-z0-9]*$', app):
        print("Error: app name must be lowercase letters+numbers"); sys.exit(1)
    title = app; desc = app + " app"; port = None
    i = 1
    while i < len(argv):
        if argv[i] == "--title" and i+1 < len(argv): title = argv[i+1]; i += 2
        elif argv[i] == "--desc" and i+1 < len(argv): desc = argv[i+1]; i += 2
        elif argv[i] == "--port" and i+1 < len(argv): port = int(argv[i+1]); i += 2
        else: i += 1
    # Auto-assign port
    if port is None:
        used = set()
        for d in [NETTOOL, "/root"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    mf = os.path.join(d, f, "manifest.json")
                    if os.path.exists(mf):
                        try: used.add(json.load(open(mf))["port"])
                        except: pass
        for p in range(9001, 9100):
            if p not in used: port = p; break
        if port is None: port = 9001
    emoji = to_emoji(app)
    date = datetime.now().strftime("%Y-%m-%d")
    app_dir = os.path.join(NETTOOL, app)
    os.makedirs(os.path.join(app_dir, "static"), exist_ok=True)
    with open(os.path.join(app_dir, "manifest.json"), "w") as f:
        f.write(render_manifest(app, title, desc, port, emoji))
    tpl = open(os.path.join(os.path.dirname(__file__), "templates", "app_template.html"), encoding="utf-8").read()
    for k, v in dict(app=app, title=title, desc=desc, port=str(port), date=date).items():
        tpl = tpl.replace("{{" + k + "}}", v)
    with open(os.path.join(app_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl)
    srv = SERVER_TPL
    for k, v in dict(app=app, title=title, port=str(port)).items():
        srv = srv.replace("{{" + k + "}}", v)
    with open(os.path.join(app_dir, "server.py"), "w") as f:
        f.write(srv)
    print()
    print("=" * 50)
    print("SUCCESS: App created at", app_dir)
    print("Port:", port)
    print("URL: http://IP:9000/" + app + "/")
    print("=" * 50)
    cfg = "[program:nettool-" + app + "]\ncommand=python3 " + app_dir + "/server.py\ndirectory=" + app_dir + "\nautostart=true\nautorestart=true\nuser=root\nstdout_logfile=/var/log/nettool-" + app + ".log\nstderr_logfile=/var/log/nettool-" + app + ".error.log\n"
    open("/etc/supervisor/conf.d/nettool-" + app + ".conf", "w").write(cfg)
    import subprocess
    subprocess.run(["supervisorctl", "update"], capture_output=True, text=True)
    subprocess.run(["supervisorctl", "restart", "nettool-" + app], capture_output=True, text=True)
    subprocess.run(["supervisorctl", "restart", "nettool-portal"], capture_output=True, text=True)
    print("\nAuto-started via supervisord!")

if __name__ == "__main__": main()
