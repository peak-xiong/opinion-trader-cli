#!/bin/bash
# Opinion Trader 停止脚本

cd "$(dirname "$0")"

if [ ! -f "logs/trader.pid" ]; then
    echo "[!] 未找到PID文件，程序可能未在运行"
    exit 1
fi

PID=$(cat logs/trader.pid)

if ps -p $PID > /dev/null 2>&1; then
    echo "[*] 正在停止进程 (PID: $PID)..."
    kill $PID
    sleep 2

    # 检查是否还在运行
    if ps -p $PID > /dev/null 2>&1; then
        echo "[*] 进程未响应，强制终止..."
        kill -9 $PID
    fi

    rm -f logs/trader.pid
    echo "[✓] 程序已停止"
else
    echo "[!] 进程 $PID 已不存在"
    rm -f logs/trader.pid
fi
