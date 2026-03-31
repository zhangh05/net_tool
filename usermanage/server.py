#!/usr/bin/env python3
"""
Usermanage - 用户管理应用
端口: 9001
功能: 用户管理界面 + API代理到Portal
"""
import os
import http.server
import socketserver
import http.client
import json

PORT = 9001
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTAL_HOST = '127.0.0.1:9000'


class Handler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")
    
    def get_user_info(self):
        """从Portal获取当前登录用户信息"""
        conn = http.client.HTTPConnection(PORTAL_HOST, timeout=10)
        headers = {'Cookie': self.headers.get('Cookie', '')}
        try:
            conn.request('GET', '/api/users/', headers=headers)
            resp = conn.getresponse()
            return resp.status == 200
        except:
            return False
        finally:
            conn.close()
    
    def send_html(self, body):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def send_json(self, status, body):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    
    def proxy_to_portal(self, path, method='GET'):
        """代理API请求到Portal"""
        conn = http.client.HTTPConnection(PORTAL_HOST, timeout=10)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'connection') if k}
        try:
            conn.request(method, path, headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ('transfer-encoding', 'connection'):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            self.send_json(502, f'Proxy error: {e}')
        finally:
            conn.close()
    
    def do_GET(self):
        path = self.path.split('?')[0]
        
        # 静态资源
        if path.startswith('/static/'):
            filepath = path[8:]
            full = os.path.join(BASE_DIR, 'static', filepath)
            if os.path.exists(full) and '..' not in filepath:
                with open(full, 'rb') as f:
                    body = f.read()
                import mimetypes
                mt, _ = mimetypes.guess_type(filepath)
                self.send_response(200)
                self.send_header('Content-Type', mt or 'application/octet-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()
            return
        
        # API -> 代理到Portal
        if path.startswith('/api/'):
            self.proxy_to_portal(path)
            return
        
        # 首页
        with open(os.path.join(BASE_DIR, 'index.html'), encoding='utf-8') as f:
            body = f.read()
        self.send_html(body.encode('utf-8'))
    
    def do_POST(self):
        if self.path.startswith('/api/'):
            self.proxy_to_portal(self.path, 'POST')
        else:
            self.send_response(405)
            self.end_headers()
    
    def do_PUT(self):
        if self.path.startswith('/api/'):
            self.proxy_to_portal(self.path, 'PUT')
        else:
            self.send_response(405)
            self.end_headers()
    
    def do_DELETE(self):
        if self.path.startswith('/api/'):
            self.proxy_to_portal(self.path, 'DELETE')
        else:
            self.send_response(405)
            self.end_headers()


if __name__ == '__main__':
    print(f"Usermanage 启动: http://0.0.0.0:{PORT}")
    with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nUsermanage 已停止")
