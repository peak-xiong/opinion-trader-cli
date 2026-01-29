#!/bin/bash
# Opinion Trader 日志查看脚本

cd "$(dirname "$0")"

# 检查logs目录
if [ ! -d "logs" ]; then
    echo "[!] 日志目录不存在"
    exit 1
fi

# 获取最新日志文件
LATEST_LOG=$(ls -t logs/trader_*.log 2>/dev/null | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "[!] 未找到日志文件"
    exit 1
fi

echo "=========================================="
echo "  Opinion Trader 日志查看"
echo "=========================================="
echo ""
echo "当前日志文件: $LATEST_LOG"
echo ""
echo "选项:"
echo "  1. 实时查看日志 (tail -f)"
echo "  2. 查看最近100行"
echo "  3. 查看最近500行"
echo "  4. 搜索关键词"
echo "  5. 列出所有日志文件"
echo "  0. 退出"
echo ""

read -p "请选择: " choice

case $choice in
    1)
        echo ""
        echo "按 Ctrl+C 退出实时查看"
        echo "─────────────────────────────────────────"
        tail -f "$LATEST_LOG"
        ;;
    2)
        echo ""
        tail -100 "$LATEST_LOG"
        ;;
    3)
        echo ""
        tail -500 "$LATEST_LOG"
        ;;
    4)
        read -p "请输入搜索关键词: " keyword
        echo ""
        grep -i "$keyword" "$LATEST_LOG" | tail -50
        ;;
    5)
        echo ""
        echo "所有日志文件:"
        ls -lh logs/trader_*.log 2>/dev/null
        ;;
    *)
        echo "已退出"
        ;;
esac
