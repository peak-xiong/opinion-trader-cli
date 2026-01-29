#!/bin/bash
# 查看 Opinion Trader 日志

cd "$(dirname "$0")/.."

LOG_FILE="logs/trader.log"

if [ -f "$LOG_FILE" ]; then
    echo "查看日志: $LOG_FILE"
    echo "按 Ctrl+C 退出"
    echo "========================"
    tail -f "$LOG_FILE"
else
    echo "日志文件不存在: $LOG_FILE"
    echo "请先使用 ./scripts/run_background.sh 启动后台进程"
fi
