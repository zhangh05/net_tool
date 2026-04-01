#!/usr/bin/env python3
"""锚点 - 网络资产记账工具 后端服务"""

import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "anchors.json")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")


def load_anchors():
    """加载数据"""
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_anchors(anchors):
    """保存数据"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(anchors, f, ensure_ascii=False, indent=2)


def safe_subprocess_run(cmd, timeout=10, capture=True):
    """安全执行子进程命令"""
    try:
        kwargs = {"timeout": timeout, "shell": True}
        if capture:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.STDOUT
        result = subprocess.run(cmd, **kwargs)
        output = result.stdout.decode("utf-8", errors="replace") if capture else ""
        return {"success": result.returncode == 0, "output": output.strip(), "exit_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "操作超时", "exit_code": -1}
    except Exception as e:
        return {"success": False, "output": f"执行错误: {str(e)}", "exit_code": -1}


class AnchorsHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def log_message(self, format, *args):
        """抑制默认日志输出"""
        pass

    def send_json(self, data, status=200):
        """发送 JSON 响应"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_html(self, content):
        """发送 HTML 响应"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _strip_anchor_prefix(self, path):
        if path.startswith('/anchor'):
            return path[len('/anchor'):] or '/'
        return path

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        path = self._strip_anchor_prefix(path)
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            if os.path.exists(INDEX_FILE):
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    self.send_html(f.read())
            else:
                self.send_json({"error": "index.html not found"}, 404)
        elif path == "/api/anchors":
            anchors = load_anchors()
            self.send_json(anchors)
        elif path == "/api/ping":
            # GET /api/ping?ip=<IP>
            ip = (params.get("ip") or [None])[0]
            if not ip:
                self.send_json({"error": "Missing ip parameter"}, 400)
                return
            if not re.match(r"^[\d\.\-a-zA-Z]+$", ip):
                self.send_json({"error": "Invalid IP address"}, 400)
                return
            result = safe_subprocess_run(f"ping -c 4 {ip}", timeout=15)
            self.send_json(result)
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """处理 POST 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        path = self._strip_anchor_prefix(path)

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        # ---- 网络操作 API ----
        if path == "/api/telnet":
            ip = data.get("ip", "")
            port = data.get("port", 23)
            if not ip:
                self.send_json({"error": "Missing ip"}, 400)
                return
            if not re.match(r"^[\d\.\-a-zA-Z]+$", ip):
                self.send_json({"error": "Invalid IP address"}, 400)
                return
            # telnet 输出到 stdout/stderr，BatchMode 方式不可用，直接执行
            result = safe_subprocess_run(
                f"timeout 8 sh -c 'printf \"\\r\\n\" | telnet {ip} {port} 2>&1'",
                timeout=12
            )
            self.send_json(result)
            return

        if path == "/api/ssh":
            ip = data.get("ip", "")
            port = data.get("port", 22)
            user = data.get("user", "root")
            password = data.get("password", "")
            cmd = data.get("cmd", "hostname && uname -a")
            if not ip:
                self.send_json({"error": "Missing ip"}, 400)
                return
            if not re.match(r"^[\d\.\-a-zA-Z]+$", ip):
                self.send_json({"error": "Invalid IP address"}, 400)
                return

            # 优先尝试 paramiko（如果可用），否则用 sshpass + ssh
            try:
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    client.connect(
                        hostname=ip,
                        port=int(port),
                        username=user,
                        password=password,
                        timeout=10,
                        allow_agent=False,
                        look_for_keys=False,
                    )
                    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
                    out = stdout.read().decode("utf-8", errors="replace")
                    err = stderr.read().decode("utf-8", errors="replace")
                    combined = out + err if err else out
                    client.close()
                    self.send_json({"success": True, "output": combined.strip(), "method": "paramiko"})
                    return
                except Exception as e:
                    self.send_json({"success": False, "output": str(e), "method": "paramiko"})
                    return
            except ImportError:
                pass

            # fallback chain: sshpass > pexpect > batch ssh
            if password:
                # 1. sshpass
                r = safe_subprocess_run(
                    f"sshpass -p {password} ssh -o StrictHostKeyChecking=no "
                    f"-o BatchMode=yes -o ConnectTimeout=10 "
                    f"-p {port} {user}@{ip} {cmd}",
                    timeout=15
                )
                if r["exit_code"] != 127:  # not "command not found"
                    r["method"] = "sshpass"
                    self.send_json(r)
                    return

                # 2. pexpect (pure-python, no external dep)
                try:
                    import pexpect
                    child = pexpect.spawn(
                        f"/usr/bin/ssh -o StrictHostKeyChecking=no "
                        f"-o ConnectTimeout=10 -p {port} {user}@{ip} {cmd}",
                        timeout=10,
                        encoding="utf-8",
                        codec_errors="replace"
                    )
                    idx = child.expect(["password:", "Permission denied", "Connection refused",
                                        pexpect.TIMEOUT, pexpect.EOF], timeout=10)
                    if idx == 0:
                        child.sendline(password)
                        # After password, expect EOF or permission denied
                        idx2 = child.expect(
                            ["Permission denied", pexpect.EOF, pexpect.TIMEOUT], timeout=10
                        )
                        output = child.before.strip()
                        child.close(force=True)
                        if idx2 == 0:
                            self.send_json({
                                "success": False,
                                "output": "认证失败，请检查用户名或密码",
                                "method": "pexpect"
                            })
                        else:
                            self.send_json({"success": True, "output": output, "method": "pexpect"})
                        return
                    elif idx == 1:
                        child.close(force=True)
                        self.send_json({"success": False, "output": "认证失败，请检查用户名或密码", "method": "pexpect"})
                        return
                    elif idx == 2:
                        child.close(force=True)
                        self.send_json({"success": False, "output": "连接被拒绝", "method": "pexpect"})
                        return
                    else:
                        output = child.before.strip() if hasattr(child, 'before') else ""
                        child.close(force=True)
                        self.send_json({"success": False, "output": output or "连接超时", "method": "pexpect"})
                        return
                except Exception as e:
                    try:
                        child.close(force=True)
                    except Exception:
                        pass
                    self.send_json({"success": False, "output": f"pexpect 错误: {str(e)}", "method": "pexpect"})
                    return

            # 无密码: batch mode
            result = safe_subprocess_run(
                f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes "
                f"-o ConnectTimeout=10 -p {port} {user}@{ip} {cmd}",
                timeout=15
            )
            result["method"] = "ssh"
            self.send_json(result)
            return

        # ---- 数据管理 API ----
        anchors = load_anchors()

        if path == "/api/anchors":
            action = data.get("action", "")

            if action == "add":
                new_anchor = {
                    "id": str(uuid.uuid4()),
                    "ip": data.get("ip", ""),
                    "hostname": data.get("hostname", ""),
                    "ports": data.get("ports", ""),
                    "type": data.get("type", "other"),
                    "tag": data.get("tag", ""),
                    "note": data.get("note", ""),
                    "created": datetime.now().strftime("%Y-%m-%d")
                }
                anchors.append(new_anchor)
                save_anchors(anchors)
                self.send_json(new_anchor)

            elif action == "update":
                anchor_id = data.get("id")
                for i, anchor in enumerate(anchors):
                    if anchor["id"] == anchor_id:
                        anchors[i].update({
                            "ip": data.get("ip", anchor.get("ip", "")),
                            "hostname": data.get("hostname", anchor.get("hostname", "")),
                            "ports": data.get("ports", anchor.get("ports", "")),
                            "type": data.get("type", anchor.get("type", "other")),
                            "tag": data.get("tag", anchor.get("tag", "")),
                            "note": data.get("note", anchor.get("note", ""))
                        })
                        save_anchors(anchors)
                        self.send_json(anchors[i])
                        return
                self.send_json({"error": "Anchor not found"}, 404)

            elif action == "delete":
                anchor_id = data.get("id")
                new_anchors = [a for a in anchors if a["id"] != anchor_id]
                if len(new_anchors) < len(anchors):
                    save_anchors(new_anchors)
                    self.send_json({"success": True})
                else:
                    self.send_json({"error": "Anchor not found"}, 404)

            else:
                self.send_json({"error": "Unknown action"}, 400)
        else:
            self.send_json({"error": "Not found"}, 404)


def main():
    """启动服务器"""
    port = 9006
    server = HTTPServer(("0.0.0.0", port), AnchorsHandler)
    print(f"🚀 锚点 服务已启动 http://0.0.0.0:{port}")
    print(f"📁 数据文件: {DATA_FILE}")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
