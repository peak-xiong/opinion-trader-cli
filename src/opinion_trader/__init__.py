"""
Opinion Trader CLI - Opinion.trade 自动交易程序

一个功能完整的 Opinion.trade 交易工具，支持：
- 多账户管理
- 批量交易（买入、卖出、做市商等）
- 分层挂单策略
- 网格交易策略
- WebSocket 实时数据
- 跨平台打包支持
"""

__version__ = "3.0.0"
__author__ = "Opinion Trader Team"

from opinion_trader.config.models import (
    TraderConfig,
    MarketMakerConfig,
    MarketMakerState,
)

__all__ = [
    "__version__",
    "TraderConfig",
    "MarketMakerConfig",
    "MarketMakerState",
]
