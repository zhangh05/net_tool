#!/bin/bash
# NetOps 停止脚本

PORT=9000
PID_FILE="/tmp/netops_server.pid"

# 先尝试从 PID 文件杀
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 停止 NetOps（PID: $PID）..."
        kill "$PID"
        sleep 1
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null
            echo "   已强制杀死"
        else
            echo "   已停止"
        fi
    else
        echo "⚠️  PID 文件中的进程不存在"
    fi
    rm -f "$PID_FILE"
else
    echo "⚠️  PID 文件不存在，尝试通过端口查找..."
fi

# 通过端口查找并杀死
PIDS=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | grep -oP 'pid=\K\d+' | sort -u)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
        echo "🛑 停止进程 PID=$pid ..."
        kill "$pid" 2>/dev/null
        sleep 1
        kill -9 "$pid" 2>/dev/null
    done
    echo "✅ 已停止"
else
    echo "✅ 端口 ${PORT} 未被占用（服务已停止）"
fi

# 也杀 python3 server.py 进程
for pid in $(ps aux 2>/dev/null | grep "[s]erver.py" | grep nettool | awk '{print $2}'); do
    echo "🛑 额外杀死: $pid"
    kill "$pid" 2>/dev/null
done

echo "✅ 停止完成"
