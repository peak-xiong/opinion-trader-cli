#!/bin/bash
# Opinion Trader CLI 一键安装脚本

echo "=========================================="
echo "  Opinion Trader CLI v3.0.0 安装程序"
echo "=========================================="

cd "$(dirname "$0")"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python3 (>=3.10)"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[✓] Python3 已安装: Python $PYTHON_VERSION"

# 检查 Python 版本
REQUIRED_MAJOR=3
REQUIRED_MINOR=10
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt "$REQUIRED_MAJOR" ] || ([ "$MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$MINOR" -lt "$REQUIRED_MINOR" ]); then
    echo "[错误] 需要 Python >= 3.10，当前版本: $PYTHON_VERSION"
    exit 1
fi

# 创建虚拟环境
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo "[✓] 虚拟环境创建完成"
else
    echo "[✓] 虚拟环境已存在"
fi

# 激活虚拟环境并安装依赖
echo "[*] 安装依赖包..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

# 先安装基础依赖
pip install -r requirements.txt -q

# 以开发模式安装项目（支持新包结构）
echo "[*] 安装项目..."
pip install -e . -q

echo "[✓] 依赖安装完成"
echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "运行方式："
echo "  方式1: ./run.sh"
echo "  方式2: source .venv/bin/activate && opinion-trader"
echo "  方式3: source .venv/bin/activate && python trade.py"
echo ""
echo "后台运行："
echo "  ./run_background.sh"
echo ""
echo "打包可执行文件："
echo "  pip install pyinstaller"
echo "  python build.py"
echo ""
