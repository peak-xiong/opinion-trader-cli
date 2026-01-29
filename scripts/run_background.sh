#!/bin/bash
# Opinion Trader CLI 后台运行脚本

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[!] 虚拟环境不存在，请先运行 ./scripts/install.sh"
    exit 1
fi

# 激活虚拟环境
source .venv/bin/activate

# 后台运行
nohup python -m opinion_trader > logs/trader.log 2>&1 &
echo $! > .trader.pid

echo "✓ 程序已在后台启动"
echo "  PID: $(cat .trader.pid)"
echo "  日志: logs/trader.log"
echo ""
echo "停止命令: ./scripts/stop.sh"
