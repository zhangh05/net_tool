#!/bin/bash
# NetOps 守护监控 - 每5分钟检查server状态和磁盘
REPORT_DIR="/root/netops/test-reports/comprehensive"
SERVER="http://192.168.32.72:6133"
NETOPS_DIR="/root/netops"
LOG="$REPORT_DIR/monitor.log"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG"; }

while true; do
    # 1. 检查server
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER/" 2>/dev/null)
    if [ "$STATUS" = "302" ] || [ "$STATUS" = "200" ]; then
        log "Server OK (HTTP $STATUS)"
    else
        log "Server DOWN (HTTP $STATUS) - 重启中..."
        cd "$NETOPS_DIR" && python3 server.py >> "$REPORT_DIR/server.log" 2>&1 &
        sleep 5
        STATUS2=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER/" 2>/dev/null)
        log "重启后状态: HTTP $STATUS2"
    fi
    
    # 2. 检查磁盘使用率
    DISK_PCT=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    log "磁盘使用率: ${DISK_PCT}%"
    if [ "$DISK_PCT" -gt 90 ]; then
        log "磁盘警告: ${DISK_PCT}% - 清理旧报告..."
        # 保留最新10个
        cd "$REPORT_DIR" || exit
        ls -t | grep -E '\.(md|json|log)$' | tail -n +11 | xargs rm -f 2>/dev/null
        log "清理完成"
    fi
    
    # 3. 记录检查时间
    echo "$(date): OK" >> "$REPORT_DIR/health.log"
    sleep 300
done
