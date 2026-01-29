#!/bin/bash
# Opinion Trader CLI 安装脚本

# 切换到项目根目录
cd "$(dirname "$0")/.."

echo "============================================"
echo "Opinion Trader CLI 安装程序"
echo "============================================"

# 检查 Python 版本
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD=$cmd
            echo "✓ 找到 Python $version ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "✗ 未找到 Python 3.10+，请先安装"
    exit 1
fi

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo ""
    echo "正在创建虚拟环境..."
    $PYTHON_CMD -m venv .venv
    echo "✓ 虚拟环境已创建"
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
echo ""
echo "正在安装依赖..."
pip install --upgrade pip -q
pip install -e . -q

echo ""
echo "============================================"
echo "✓ 安装完成！"
echo ""
echo "运行方式："
echo "  ./scripts/run.sh"
echo "  或"
echo "  source .venv/bin/activate && python -m opinion_trader"
echo "============================================"
