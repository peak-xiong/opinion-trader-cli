#!/bin/bash
# Opinion Trader CLI 启动脚本

cd "$(dirname "$0")"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[!] 虚拟环境不存在，正在运行安装..."
    ./install.sh
fi

# 激活虚拟环境并运行
source .venv/bin/activate

# 优先使用新入口，如果失败则回退到旧入口
if command -v opinion-trader &> /dev/null; then
    opinion-trader "$@"
else
    python3 trade.py "$@"
fi
