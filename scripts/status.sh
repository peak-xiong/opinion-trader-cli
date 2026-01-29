#!/bin/bash
# 查看 Opinion Trader 运行状态

cd "$(dirname "$0")/.."

echo "Opinion Trader CLI 状态"
echo "========================"

if [ -f ".trader.pid" ]; then
    PID=$(cat .trader.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✓ 运行中 (PID: $PID)"
        echo ""
        echo "进程信息:"
        ps -p $PID -o pid,ppid,%cpu,%mem,etime,command
    else
        echo "✗ 进程已停止 (PID 文件存在但进程不存在)"
    fi
else
    # 检查是否有相关进程在运行
    PIDS=$(pgrep -f "python.*opinion_trader")
    if [ -n "$PIDS" ]; then
        echo "✓ 发现运行中的进程:"
        ps -p $PIDS -o pid,ppid,%cpu,%mem,etime,command
    else
        echo "✗ 未运行"
    fi
fi
