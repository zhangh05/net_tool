#!/usr/bin/env python3
# IP计算器 - NetTool app  port: 9002
import os, http.server, socketserver, json, mimetypes
from urllib.parse import unquote

PORT = 9002
BASE = os.path.dirname(os.path.abspath(__file__))

class H(http.server.BaseHTTPRequestHandler):
    def log(self, *a): print(f"[{self.log_date_time_string()}]", *a)
    def reply(self, code, ct, body):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        # Portal handles static (/appname/static/...) - app server gets paths WITHOUT prefix
        if path in ("/", "", "/index.html"):
            with open(os.path.join(BASE, "index.html"), encoding="utf-8") as f:
                self.reply(200, "text/html; charset=utf-8", f.read())
            return
        if path == "/api/info":
            self.reply(200, "application/json", json.dumps({"name":"IP计算器","version":"1.0.0","app":"ipcalc","status":"ok"}))
            return
        self.reply(404, "text/plain", "Not Found")

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    print("IP计算器 running on http://0.0.0.0:" + str(PORT))
    socketserver.TCPServer(("0.0.0.0", PORT), H).serve_forever()
