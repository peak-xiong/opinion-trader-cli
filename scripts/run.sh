#!/bin/bash
# Opinion Trader CLI 启动脚本

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[!] 虚拟环境不存在，正在运行安装..."
    ./scripts/install.sh
fi

# 激活虚拟环境并运行
source .venv/bin/activate

# 使用 Python 模块方式运行
python -m opinion_trader "$@"
