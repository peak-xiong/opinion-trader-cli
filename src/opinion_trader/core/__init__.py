"""
核心交易逻辑模块

包含交易器、做市商、批量交易等核心功能
"""

from opinion_trader.core.trader import OpinionSDKTrader
from opinion_trader.core.enhanced import (
    TradeSummary,
    TradeRecord,
    OrderCalculator,
    MergeSplitService,
    EnhancedOrderService,
    OrderInputHelper,
)

__all__ = [
    "OpinionSDKTrader",
    "TradeSummary",
    "TradeRecord",
    "OrderCalculator",
    "MergeSplitService",
    "EnhancedOrderService",
    "OrderInputHelper",
]
