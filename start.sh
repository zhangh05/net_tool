#!/bin/bash
# NetTool 启动脚本（使用 supervisor 管理）

echo "========================================"
echo "  NetTool 启动脚本"
echo "========================================"

# 启动 NetOps
echo ""
echo "🚀 启动 NetOps (supervisor)..."
supervisorctl start nettool-netops 2>&1
sleep 2
supervisorctl status nettool-netops

# 启动 Manage
echo ""
echo "🚀 启动 Manage (supervisor)..."
supervisorctl start nettool-manage 2>&1
sleep 2
supervisorctl status nettool-manage

echo ""
echo "========================================"
echo "  ✅ 全部启动完成"
echo "========================================"
echo "  Manage:  http://192.168.32.72:8999"
echo "  NetOps:  http://192.168.32.72:9000"
echo ""
