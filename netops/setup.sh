#!/bin/bash
# NetOps AI 拓扑助手 - 一键安装脚本
# 运行方式: bash setup.sh

set -e

NETOPS_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$NETOPS_DIR"

echo "========================================"
echo "  NetOps AI 拓扑助手 - 安装程序"
echo "========================================"

# 1. 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python3，请先安装"
    exit 1
fi

# 2. 检测本机 IP
LOCAL_IP=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
except:
    ip = '127.0.0.1'
finally:
    s.close()
print(ip)
")
echo "  检测到本机 IP: $LOCAL_IP"

# 3. 启动 NetOps 服务
echo ""
echo "  启动 NetOps 服务..."

# 杀掉旧进程
fuser -k 6133/tcp 2>/dev/null || true
sleep 1

# 启动服务
nohup python3 -u server.py > netops.log 2>&1 &
SERVER_PID=$!

sleep 2

# 检查是否启动成功
if curl -s http://127.0.0.1:6133/api/ping/read?sid=none > /dev/null 2>&1; then
    echo "  ✅ 服务启动成功"
else
    echo "  ❌ 服务启动失败，请查看 netops.log"
    exit 1
fi

# 4. 初始化 agent session
echo ""
echo "  初始化 Agent..."
curl -s -X POST http://127.0.0.1:6133/api/agent/sessions \
    -H "Content-Type: application/json" \
    -d '{"chat_session_id": "default"}' > /dev/null 2>&1 || true

# 5. 创建 uploads 目录
mkdir -p uploads
chmod 755 uploads

echo ""
echo "========================================"
echo "  ✅ 安装完成!"
echo "========================================"
echo ""
echo "  浏览器访问: http://$LOCAL_IP:6133"
echo "  AI 拓扑助手: http://$LOCAL_IP:6133/#ai"
echo ""
echo "  服务进程 PID: $SERVER_PID"
echo "  查看日志: tail -f netops.log"
echo ""
echo "  停止服务: fuser -k 6133/tcp"
echo ""
