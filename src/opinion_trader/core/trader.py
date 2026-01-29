"""
核心交易模块

包含 OpinionSDKTrader 类和相关交易功能

注意：这是一个桥接模块，核心逻辑仍在根目录的 trade.py 中
将来的版本会逐步将代码迁移到此处
"""
import sys
import os

# 添加项目根目录到路径，以便导入原始 trade.py
_project_root = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 从原始 trade.py 导入核心类
# 注意：这是临时方案，将来会将代码完全迁移到此模块
try:
    from trade import OpinionSDKTrader, load_configs, main as trade_main
except ImportError:
    # 如果从包内运行，使用相对导入可能失败
    # 提供占位符，实际运行时需要确保 trade.py 可访问
    OpinionSDKTrader = None
    load_configs = None
    trade_main = None

__all__ = [
    'OpinionSDKTrader',
    'load_configs',
    'trade_main',
]
