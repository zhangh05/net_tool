#!/usr/bin/env python3
# 配置备份 - NetTool app  port: 9005
import os, http.server, socketserver, json, mimetypes
from urllib.parse import parse_qs, unquote

PORT = 9005
BASE = os.path.dirname(os.path.abspath(__file__))


class H(http.server.BaseHTTPRequestHandler):
    def log(self, *a): print(f"[{self.log_date_time_string()}]", *a)

    def reply(self, code, ct, body):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ct + "; charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def options(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        if path in ("/", "", "/index.html"):
            with open(os.path.join(BASE, "index.html"), encoding="utf-8") as f:
                self.reply(200, "text/html", f.read())
            return

        if path == "/api/info":
            self.reply(200, "application/json", json.dumps({
                "name": "配置备份",
                "version": "1.0.0",
                "app": "configbak",
                "status": "ok",
                "uptime": "healthy"
            }))
            return

        self.reply(404, "text/plain", "Not Found")

    def do_POST(self):
        path = unquote(self.path.split("?")[0])
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        params = {}
        for kv in body.split("&"):
            k, _, v = kv.partition("=")
            params[unquote(k)] = unquote(v)

        if path == "/api/echo":
            self.reply(200, "application/json", json.dumps({"ok": True, "received": params}))
            return

        self.reply(404, "text/plain", "Not Found")


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    print("配置备份 running on http://0.0.0.0:9005")
    socketserver.TCPServer(("0.0.0.0", PORT), H).serve_forever()
