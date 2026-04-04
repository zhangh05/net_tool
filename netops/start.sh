#!/bin/bash
# NetOps 启动脚本

SERVICE="netops"
PORT=9000
WORKDIR="/root/nettool/netops"
LOG="/tmp/netops_srv.log"
PID_FILE="/tmp/netops_server.pid"

# 检查是否已在运行
if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
    echo "❌ NetOps 已在运行（端口 ${PORT} 已被占用）"
    ss -tlnp | grep "${PORT}"
    exit 1
fi

# 检查工作目录
if [ ! -d "$WORKDIR" ]; then
    echo "❌ 工作目录不存在: $WORKDIR"
    exit 1
fi

# 启动
echo "🚀 启动 NetOps..."
cd "$WORKDIR"
nohup python3 -u server.py > "$LOG" 2>&1 &
echo $! > "$PID_FILE"

# 等待启动
sleep 2

# 检查是否成功
if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
    echo "✅ NetOps 已启动（PID: $(cat $PID_FILE)）"
    echo "   访问地址: http://192.168.32.72:${PORT}"
    echo "   日志: $LOG"
else
    echo "❌ 启动失败，请查看日志: $LOG"
    tail -20 "$LOG"
    exit 1
fi
