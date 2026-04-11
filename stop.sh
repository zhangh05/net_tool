#!/bin/bash
# NetTool 停止脚本（使用 supervisor 管理）

echo "========================================"
echo "  NetTool 停止脚本"
echo "========================================"

echo ""
echo "🛑 停止 Manage..."
supervisorctl stop nettool-manage 2>&1

echo ""
echo "🛑 停止 NetOps..."
supervisorctl stop nettool-netops 2>&1

echo ""
supervisorctl status

echo ""
echo "========================================"
echo "  ✅ 停止完成"
echo "========================================"
