#!/bin/bash
# 停止后台运行的 Opinion Trader

cd "$(dirname "$0")/.."

if [ -f ".trader.pid" ]; then
    PID=$(cat .trader.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        rm .trader.pid
        echo "✓ 已停止进程 (PID: $PID)"
    else
        rm .trader.pid
        echo "进程已不存在"
    fi
else
    echo "未找到 PID 文件，可能程序未在运行"
    
    # 尝试查找进程
    PIDS=$(pgrep -f "python.*opinion_trader")
    if [ -n "$PIDS" ]; then
        echo "找到相关进程: $PIDS"
        echo "使用 kill $PIDS 手动停止"
    fi
fi
