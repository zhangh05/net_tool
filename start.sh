#!/bin/bash
# NetTool 整体启动脚本

WORKDIR="/root/nettool"
MANAGE_PORT=8999
NETOPS_PORT=9000
MANAGE_LOG="/tmp/manage_srv.log"
NETOPS_LOG="/tmp/netops_srv.log"
MANAGE_PID="/tmp/manage_server.pid"
NETOPS_PID="/tmp/netops_server.pid"

echo "========================================"
echo "  NetTool 启动脚本"
echo "========================================"

# 检查端口是否已被占用
check_port() {
    if ss -tlnp 2>/dev/null | grep -q ":$1 "; then
        echo "❌ 端口 $1 已被占用，$2 可能已在运行"
        ss -tlnp | grep ":$1 "
        return 1
    fi
    return 0
}

# 检查所有必需端口
check_port $MANAGE_PORT "Manage" || exit 1
check_port $NETOPS_PORT "NetOps" || exit 1

# 启动 NetOps
echo ""
echo "🚀 启动 NetOps..."
cd "$WORKDIR/netops"
PORT=9000 NETTOOL_OPEN_MODE=true nohup python3 -u server.py > "$NETOPS_LOG" 2>&1 &
echo $! > "$NETOPS_PID"
sleep 2
if ss -tlnp 2>/dev/null | grep -q ":${NETOPS_PORT} "; then
    echo "   NetOps ✅ PID: $(cat $NETOPS_PID)"
else
    echo "   NetOps ❌ 启动失败"
    tail -10 "$NETOPS_LOG"
    exit 1
fi

# 启动 Manage
echo ""
echo "🚀 启动 Manage..."
cd "$WORKDIR/manage"
nohup python3 -u server.py > "$MANAGE_LOG" 2>&1 &
echo $! > "$MANAGE_PID"
sleep 2
if ss -tlnp 2>/dev/null | grep -q ":${MANAGE_PORT} "; then
    echo "   Manage ✅ PID: $(cat $MANAGE_PID)"
else
    echo "   Manage ❌ 启动失败"
    tail -10 "$MANAGE_LOG"
    # 停止 NetOps
    kill $(cat "$NETOPS_PID") 2>/dev/null
    exit 1
fi

echo ""
echo "========================================"
echo "  ✅ 全部启动完成"
echo "========================================"
echo "  Manage:  http://192.168.32.72:$MANAGE_PORT"
echo "  NetOps: http://192.168.32.72:$NETOPS_PORT"
echo "  日志: /tmp/{manage,netops}_srv.log"
echo ""
