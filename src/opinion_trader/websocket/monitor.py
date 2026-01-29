"""
WebSocket 实时监控工具
"""
from datetime import datetime
from typing import Dict, List, Optional

from opinion_trader.websocket.client import OpinionWebSocket


class WebSocketMonitor:
    """WebSocket 实时监控工具"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws_service: Optional[OpinionWebSocket] = None
        self.market_titles: Dict[int, str] = {}

    def _format_orderbook_update(self, data: dict) -> str:
        """格式化订单簿更新"""
        market_id = data.get('marketId', '')
        title = self.market_titles.get(market_id, f'#{market_id}')
        side = data.get('side', '')
        price = data.get('price', '')
        size = data.get('size', 0)
        outcome = 'Yes' if data.get('outcomeSide') == 1 else 'No'

        side_str = '买' if side == 'bids' else '卖'
        action = '新增/更新' if size > 0 else '删除'

        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"[{timestamp}] 盘口 {title[:15]} | {outcome} {side_str}盘 | {price}¢ x {size} ({action})"

    def _format_trade_update(self, data: dict) -> str:
        """格式化成交信息"""
        market_id = data.get('marketId', '')
        title = self.market_titles.get(market_id, f'#{market_id}')
        side = data.get('side', '')
        price = data.get('price', '')
        shares = data.get('shares', 0)
        outcome = 'Yes' if data.get('outcomeSide') == 1 else 'No'

        side_str = '买入' if side == 'buy' else '卖出'

        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"[{timestamp}] 成交 {title[:15]} | {outcome} {side_str} | {price}¢ x {shares}份"

    def _format_price_update(self, data: dict) -> str:
        """格式化价格变动"""
        market_id = data.get('marketId', '')
        title = self.market_titles.get(market_id, f'#{market_id}')
        yes_price = data.get('yesPrice', 0)
        no_price = data.get('noPrice', 0)

        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"[{timestamp}] 价格 {title[:15]} | Yes: {yes_price}¢ | No: {no_price}¢"

    async def start_monitoring(
        self,
        market_ids: List[int],
        market_titles: Optional[Dict[int, str]] = None,
        subscribe_orderbook: bool = True,
        subscribe_trade: bool = True,
        subscribe_price: bool = True
    ):
        """开始监控"""
        self.market_titles = market_titles or {}

        def on_orderbook(data):
            print(self._format_orderbook_update(data))

        def on_trade(data):
            print(self._format_trade_update(data))

        def on_price(data):
            print(self._format_price_update(data))

        self.ws_service = OpinionWebSocket(
            api_key=self.api_key,
            on_orderbook=on_orderbook if subscribe_orderbook else None,
            on_trade=on_trade if subscribe_trade else None,
            on_price=on_price if subscribe_price else None
        )

        if not await self.ws_service.connect():
            return

        # 订阅所有市场
        for market_id in market_ids:
            if subscribe_orderbook:
                await self.ws_service.subscribe_orderbook(market_id)
            if subscribe_trade:
                await self.ws_service.subscribe_trade(market_id)
            if subscribe_price:
                await self.ws_service.subscribe_price(market_id)

        print(f"\n已订阅 {len(market_ids)} 个市场，按 Ctrl+C 停止监控\n")
        print("-" * 60)

        # 开始接收消息
        await self.ws_service.receive_loop()

    async def stop_monitoring(self):
        """停止监控"""
        if self.ws_service:
            await self.ws_service.disconnect()
