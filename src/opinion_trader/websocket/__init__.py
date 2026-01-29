"""
WebSocket 模块

包含 WebSocket 客户端和监控工具
"""

from opinion_trader.websocket.client import OpinionWebSocket, WEBSOCKET_AVAILABLE
from opinion_trader.websocket.monitor import WebSocketMonitor

__all__ = [
    "OpinionWebSocket",
    "WebSocketMonitor",
    "WEBSOCKET_AVAILABLE",
]
