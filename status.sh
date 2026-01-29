#!/bin/bash
# Opinion Trader 状态检查脚本

cd "$(dirname "$0")"

echo "=========================================="
echo "  Opinion Trader 运行状态"
echo "=========================================="
echo ""

if [ ! -f "logs/trader.pid" ]; then
    echo "[状态] 未运行"
    echo ""
    exit 0
fi

PID=$(cat logs/trader.pid)

if ps -p $PID > /dev/null 2>&1; then
    echo "[状态] 运行中"
    echo "[PID]  $PID"
    echo ""

    # 显示进程信息
    echo "进程信息:"
    ps -p $PID -o pid,ppid,%cpu,%mem,etime,command | head -2
    echo ""

    # 显示最新日志文件
    LATEST_LOG=$(ls -t logs/trader_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "最新日志文件: $LATEST_LOG"
        echo "日志大小: $(du -h "$LATEST_LOG" | cut -f1)"
        echo ""
        echo "最近10行日志:"
        echo "─────────────────────────────────────────"
        tail -10 "$LATEST_LOG"
        echo "─────────────────────────────────────────"
    fi
else
    echo "[状态] 已停止 (PID文件存在但进程不存在)"
    rm -f logs/trader.pid
fi
echo ""
