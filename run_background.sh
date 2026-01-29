#!/bin/bash
# Opinion Trader CLI 后台运行脚本

cd "$(dirname "$0")"

# 创建日志目录
mkdir -p logs

# 生成日志文件名（带时间戳）
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/trader_${TIMESTAMP}.log"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[!] 虚拟环境不存在，请先运行 ./install.sh"
    exit 1
fi

# 检查是否已有后台进程在运行
if [ -f "logs/trader.pid" ]; then
    OLD_PID=$(cat logs/trader.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "[!] 已有进程在运行 (PID: $OLD_PID)"
        echo "    如需重启，请先运行: ./stop.sh"
        exit 1
    fi
fi

echo "=========================================="
echo "  Opinion Trader CLI 后台启动"
echo "=========================================="
echo ""

# 后台启动（优先使用新入口）
nohup bash -c '
    source .venv/bin/activate
    if command -v opinion-trader &> /dev/null; then
        opinion-trader
    else
        python3 trade.py
    fi
' > "$LOG_FILE" 2>&1 &
PID=$!

# 保存PID
echo $PID > logs/trader.pid

echo "[✓] 程序已在后台启动"
echo ""
echo "  PID: $PID"
echo "  日志文件: $LOG_FILE"
echo ""
echo "=========================================="
echo "  常用命令"
echo "=========================================="
echo ""
echo "  查看实时日志:"
echo "    tail -f $LOG_FILE"
echo ""
echo "  查看最近100行日志:"
echo "    tail -100 $LOG_FILE"
echo ""
echo "  停止程序:"
echo "    ./stop.sh"
echo ""
echo "  检查程序状态:"
echo "    ./status.sh"
echo ""
