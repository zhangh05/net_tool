#!/bin/bash
LOG=/root/netops/test-reports/comprehensive/monitor.log
while true; do
    DISK=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://192.168.32.72:6133/)
    ORPHANS=$(ps aux | grep -E "chromium|playwright" | grep -v grep | wc -l)
    echo "[$(date '+%m-%d %H:%M')] disk=${DISK}% server=${STATUS} orphans=${ORPHANS}" >> $LOG
    if [ "$STATUS" != "200" ] && [ "$STATUS" != "302" ]; then
        cd /root/netops && pkill -f "server.py" 2>/dev/null; sleep 2
        nohup python3 server.py >> netops.log 2>&1 &
        echo "[$(date)] SERVER RESTARTED" >> $LOG
    fi
    if [ "$DISK" -gt 90 ]; then
        cd /root/netops/test-reports/comprehensive
        ls -t | tail -n +11 | xargs rm -rf 2>/dev/null
        echo "[$(date)] DISK CLEANUP DONE" >> $LOG
    fi
    if [ "$ORPHANS" -gt 5 ]; then
        pkill -f "chromium|playwright" 2>/dev/null
        echo "[$(date)] ORPHANS KILLED" >> $LOG
    fi
    sleep 300
done
