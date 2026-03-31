#!/usr/bin/env python3
"""
NetTool - Application bootstrapping tool
用法:
  python3 newapp.py <appname> [--title T] [--port N] [--desc D] [--blank]
  python3 newapp.py list
  python3 newapp.py delete <appname>
  python3 newapp.py start <appname>
  python3 newapp.py stop <appname>
  python3 newapp.py new      (interactive mode)
"""
import os, sys, json, re, subprocess
from datetime import datetime

NETTOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(TOOLS_DIR, "templates")


def _load_tpl(name):
    with open(os.path.join(TPL_DIR, name), encoding="utf-8") as f:
        return f.read()


def tpl_manifest(app, title, desc, port, emoji):
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


def tpl_index_html(app, title, desc, port, date, template):
    fname = "feature.html" if template == "feature" else "app_template.html"
    t = _load_tpl(fname)
    subs = {"app": app, "title": title, "desc": desc, "port": str(port), "date": date}
    for k, v in subs.items():
        t = t.replace("{{" + k + "}}", v)
    return t


def tpl_server_py(app, title, port, has_api):
    api_code = API_CODE if has_api else '        self.reply(404, "text/plain", "Not Found")'
    # First expand api_code placeholders
    for k, v in dict(app=app, title=title, port=str(port)).items():
        api_code = api_code.replace("{{" + k + "}}", v)
    # Then merge into server template
    t = SERVER_TPL
    for k, v in dict(app=app, title=title, port=str(port), api_code=api_code).items():
        t = t.replace("{{" + k + "}}", v)
    return t


SERVER_TPL = (
    "#!/usr/bin/env python3\n"
    "# {{title}} - NetTool app  port: {{port}}\n"
    "import os, http.server, socketserver, json, mimetypes\n"
    "from urllib.parse import parse_qs, unquote\n"
    "\n"
    "PORT = {{port}}\n"
    "BASE = os.path.dirname(os.path.abspath(__file__))\n"
    "\n"
    "\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    "    def log(self, *a): print(f\"[{self.log_date_time_string()}]\", *a)\n"
    "\n"
    "    def reply(self, code, ct, body):\n"
    "        b = body if isinstance(body, bytes) else body.encode()\n"
    "        self.send_response(code)\n"
    "        self.send_header(\"Content-Type\", ct + \"; charset=utf-8\")\n"
    "        self.send_header(\"Content-Length\", len(b))\n"
    "        self.send_header(\"Access-Control-Allow-Origin\", \"*\")\n"
    "        self.end_headers()\n"
    "        self.wfile.write(b)\n"
    "\n"
    "    def options(self):\n"
    "        self.send_response(200)\n"
    "        self.send_header(\"Access-Control-Allow-Origin\", \"*\")\n"
    "        self.send_header(\"Access-Control-Allow-Methods\", \"GET, POST, PUT, DELETE, OPTIONS\")\n"
    "        self.send_header(\"Access-Control-Allow-Headers\", \"Content-Type\")\n"
    "        self.end_headers()\n"
    "\n"
    "    def do_GET(self):\n"
    "        path = unquote(self.path.split(\"?\")[0])\n"
    "        if path in (\"/\", \"\", \"/index.html\"):\n"
    "            with open(os.path.join(BASE, \"index.html\"), encoding=\"utf-8\") as f:\n"
    "                self.reply(200, \"text/html\", f.read())\n"
    "            return\n"
    "\n"
    "{{api_code}}\n"
    "\n"
    "        self.reply(404, \"text/plain\", \"Not Found\")\n"
    "\n"
    "    def do_POST(self):\n"
    "        path = unquote(self.path.split(\"?\")[0])\n"
    "        length = int(self.headers.get(\"Content-Length\", 0))\n"
    "        body = self.rfile.read(length).decode() if length else \"\"\n"
    "        params = {}\n"
    "        for kv in body.split(\"&\"):\n"
    "            k, _, v = kv.partition(\"=\")\n"
    "            params[unquote(k)] = unquote(v)\n"
    "\n"
    "        if path == \"/api/echo\":\n"
    "            self.reply(200, \"application/json\", json.dumps({\"ok\": True, \"received\": params}))\n"
    "            return\n"
    "\n"
    "        self.reply(404, \"text/plain\", \"Not Found\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    socketserver.TCPServer.allow_reuse_address = True\n"
    "    print(\"{{title}} running on http://0.0.0.0:{{port}}\")\n"
    "    socketserver.TCPServer((\"0.0.0.0\", PORT), H).serve_forever()\n"
)

API_CODE = (
    "        if path == \"/api/info\":\n"
    "            self.reply(200, \"application/json\", json.dumps({\n"
    "                \"name\": \"{{title}}\",\n"
    "                \"version\": \"1.0.0\",\n"
    "                \"app\": \"{{app}}\",\n"
    "                \"status\": \"ok\",\n"
    "                \"uptime\": \"healthy\"\n"
    "            }))\n"
    "            return"
)


# ──── Emoji 映射 ────
EMOJI_MAP = {
    "ipcalc": "🔢", "subnet": "🔢", "ip": "🔢", "mask": "🔢",
    "config": "📋", "backup": "💾", "bak": "💾",
    "monitor": "📊", "status": "📊", "alert": "🚨",
    "topo": "🌐", "netops": "🌐", "network": "🌐",
    "user": "👥", "admin": "👥", "manage": "👥",
    "learn": "📖", "study": "📖",
    "calc": "🧮", "tool": "🛠", "tools": "🛠",
    "vlan": "🔀", "route": "🔀", "router": "🔀",
    "log": "📝", "ticket": "🎫", "issue": "🎫",
    "firewall": "🛡", "fw": "🛡",
    "server": "🖥", "service": "🖥",
}


def get_emoji(app):
    for k, v in EMOJI_MAP.items():
        if k in app.lower():
            return v
    return "📦"


# ──── 应用管理 ────
def discover_apps():
    apps = []
    for d in [NETTOOL, "/root"]:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            mf = os.path.join(d, name, "manifest.json")
            if os.path.exists(mf):
                try:
                    m = json.load(open(mf))
                    apps.append({**m, "_app": name, "_dir": os.path.join(d, name)})
                except:
                    pass
    apps.sort(key=lambda x: x.get("order", 99))
    return apps


def cmd_list():
    apps = discover_apps()
    print(f"\n{'应用名':<16} {'标题':<20} {'端口':<8} {'状态'}")
    print("-" * 60)
    running = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True).stdout
    for app in apps:
        name = app.get("_app", "?")
        title = app.get("name", "?")[:18]
        port = app.get("port", "?")
        svc = f"nettool-{name}"
        # 特殊处理独立运行的应用
        if port == 6133 and os.path.exists("/root/netops/server.py"):
            status = "✅ 原生运行" if "netops" in running else "⏸ 已停止"
        elif port == 9001:
            status = "✅ 原生运行" if "usermanage" not in running else "⏸ 已停止"
        else:
            status = "✅ 运行中" if svc in running else "⏸ 已停止"
        emoji = app.get("icon_emoji", "📦")
        print(f"{emoji} {name:<14} {title:<20} {port:<8} {status}")
    print(f"\n共 {len(apps)} 个应用\n")


def cmd_delete(appname):
    app_dir = None
    for d in [NETTOOL, "/root"]:
        ad = os.path.join(d, appname)
        mf = os.path.join(ad, "manifest.json")
        if os.path.exists(mf):
            app_dir = ad
            break
    if not app_dir:
        print(f"Error: 应用 '{appname}' 不存在")
        sys.exit(1)
    confirm = input(f"确认删除应用 '{appname}'? (输入 YES 确认): ")
    if confirm != "YES":
        print("取消删除")
        return
    import shutil
    shutil.rmtree(app_dir)
    cfg = f"/etc/supervisor/conf.d/nettool-{appname}.conf"
    if os.path.exists(cfg):
        os.remove(cfg)
    subprocess.run(["supervisorctl", "restart", "nettool-portal"], capture_output=True)
    print(f"已删除 {appname}，重启 Portal 生效")


def cmd_start(appname):
    r = subprocess.run(["supervisorctl", "start", f"nettool-{appname}"],
        capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


def cmd_stop(appname):
    r = subprocess.run(["supervisorctl", "stop", f"nettool-{appname}"],
        capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


# ──── 创建应用 ────
def create_app(app, title, desc, port, template, has_api):
    if port is None:
        used = set()
        for d in [NETTOOL, "/root"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    mf = os.path.join(d, f, "manifest.json")
                    if os.path.exists(mf):
                        try:
                            used.add(json.load(open(mf))["port"])
                        except:
                            pass
        for p in range(9001, 9100):
            if p not in used:
                port = p
                break
        if port is None:
            port = 9001

    emoji = get_emoji(app)
    date = datetime.now().strftime("%Y-%m-%d")
    app_dir = os.path.join(NETTOOL, app)

    if os.path.exists(os.path.join(app_dir, "manifest.json")):
        print(f"Error: 应用 '{app}' 已存在！")
        sys.exit(1)

    os.makedirs(os.path.join(app_dir, "static"), exist_ok=True)

    with open(os.path.join(app_dir, "manifest.json"), "w") as f:
        f.write(tpl_manifest(app, title, desc, port, emoji))

    with open(os.path.join(app_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl_index_html(app, title, desc, port, date, template))

    with open(os.path.join(app_dir, "server.py"), "w", encoding="utf-8") as f:
        f.write(tpl_server_py(app, title, port, has_api))

    cfg = (f"[program:nettool-{app}]\n"
           f"command=python3 {app_dir}/server.py\n"
           f"directory={app_dir}\n"
           f"autostart=true\n"
           f"autorestart=true\n"
           f"user=root\n"
           f"stdout_logfile=/var/log/nettool-{app}.log\n"
           f"stderr_logfile=/var/log/nettool-{app}.error.log\n")
    with open(f"/etc/supervisor/conf.d/nettool-{app}.conf", "w") as f:
        f.write(cfg)

    subprocess.run(["supervisorctl", "update"], capture_output=True)
    subprocess.run(["supervisorctl", "restart", f"nettool-{app}"], capture_output=True)
    subprocess.run(["supervisorctl", "restart", "nettool-portal"], capture_output=True)

    print(f"""
================================================================
  应用「{title}」创建成功！
================================================================
  目录: {app_dir}
  端口: {port}
  模板: {template}
  访问: http://IP:9000/{app}/
================================================================""")

    import time; time.sleep(1)
    r = subprocess.run(["supervisorctl", "status", f"nettool-{app}"],
        capture_output=True, text=True)
    print(r.stdout.strip())


# ──── 主入口 ────
def main():
    argv = sys.argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__)
        sys.exit(0)

    cmd = argv[0]

    if cmd == "list" or cmd == "ls":
        cmd_list()
    elif cmd == "delete" or cmd == "rm":
        if len(argv) < 2:
            print("用法: newapp.py delete <appname>"); sys.exit(1)
        cmd_delete(argv[1])
    elif cmd == "start":
        if len(argv) < 2:
            print("用法: newapp.py start <appname>"); sys.exit(1)
        cmd_start(argv[1])
    elif cmd == "stop":
        if len(argv) < 2:
            print("用法: newapp.py stop <appname>"); sys.exit(1)
        cmd_stop(argv[1])
    else:
        app = cmd
        if not re.match(r'^[a-z][a-z0-9]*$', app):
            print("Error: 应用名只能是小写字母和数字，且以字母开头")
            sys.exit(1)

        title = app; desc = app + " app"; port = None
        template = "feature"; has_api = True

        i = 1
        while i < len(argv):
            if argv[i] == "--title" and i+1 < len(argv): title = argv[i+1]; i += 2
            elif argv[i] == "--desc" and i+1 < len(argv): desc = argv[i+1]; i += 2
            elif argv[i] == "--port" and i+1 < len(argv): port = int(argv[i+1]); i += 2
            elif argv[i] == "--blank": template = "blank"; i += 1
            elif argv[i] == "--no-api": has_api = False; i += 1
            else: i += 1

        create_app(app, title, desc, port, template, has_api)


if __name__ == "__main__": main()
