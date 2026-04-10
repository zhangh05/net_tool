#!/bin/bash
# NetTool 整体停止脚本

MANAGE_PID="/tmp/manage_server.pid"
NETOPS_PID="/tmp/netops_server.pid"
MANAGE_PORT=8999
NETOPS_PORT=9000

echo "========================================"
echo "  NetTool 停止脚本"
echo "========================================"

stop_service() {
    local name=$1
    local pid_file=$2
    local port=$3

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "🛑 停止 $name（PID: $pid）..."
            kill "$pid" 2>/dev/null
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
        fi
        rm -f "$pid_file"
    fi

    # 通过端口查找残留进程
    local pids=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K\d+' | sort -u)
    if [ -n "$pids" ]; then
        for p in $pids; do
            echo "   清理残留进程 PID=$p ..."
            kill -9 "$p" 2>/dev/null
        done
    fi
}

echo ""
stop_service "Manage" "$MANAGE_PID" $MANAGE_PORT
echo ""
stop_service "NetOps" "$NETOPS_PID" $NETOPS_PORT

echo ""
echo "========================================"
echo "  ✅ 停止完成"
echo "========================================"
