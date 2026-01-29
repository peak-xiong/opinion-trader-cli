"""
Opinion SDK WebSocket 客户端模块
包含 WebSocket 实时数据服务和监控工具
"""
import asyncio
import json
from datetime import datetime
from typing import Callable

try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False


class OpinionWebSocket:
    """Opinion.trade WebSocket 实时数据服务"""

    WS_BASE_URL = "wss://ws.opinion.trade"

    def __init__(self, api_key: str, on_orderbook: Callable = None,
                 on_trade: Callable = None, on_price: Callable = None):
        self.api_key = api_key
        self.ws = None
        self.on_orderbook = on_orderbook
        self.on_trade = on_trade
        self.on_price = on_price
        self.subscriptions = set()
        self.is_connected = False
        self._stop_event = asyncio.Event()
        self._heartbeat_task = None

    async def connect(self) -> bool:
        """建立 WebSocket 连接"""
        if not WEBSOCKET_AVAILABLE:
            print("✗ websockets 库未安装，请运行: pip install websockets")
            return False

        try:
            # API key 通过 URL query param 传递
            ws_url = f"{self.WS_BASE_URL}?apikey={self.api_key}"
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10
            )
            self.is_connected = True
            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            print("✓ WebSocket 已连接")
            return True
        except Exception as e:
            print(f"✗ WebSocket 连接失败: {e}")
            return False

    async def _heartbeat_loop(self):
        """发送心跳保持连接"""
        import time
        try:
            while self.is_connected and self.ws:
                await asyncio.sleep(25)  # 每25秒发送心跳
                if self.ws and self.is_connected:
                    await self.ws.send(json.dumps({"action": "HEARTBEAT"}))
                    timestamp = time.strftime("%H:%M:%S")
                    print(f"  [{timestamp}] 保持连接中...")
        except Exception:
            pass

    async def disconnect(self):
        """断开连接"""
        self._stop_event.set()
        self.is_connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
        print("✓ WebSocket 已断开")

    async def subscribe_orderbook(self, market_id: int):
        """订阅订单簿变动"""
        if not self.ws:
            print(f"  ✗ 订阅订单簿失败: WebSocket 未连接")
            return False
        msg = {
            "action": "SUBSCRIBE",
            "channel": "market.depth.diff",
            "marketId": market_id
        }
        try:
            await self.ws.send(json.dumps(msg))
            self.subscriptions.add(f"market.depth.diff_{market_id}")
            print(f"  ✓ 已订阅订单簿 (marketId={market_id})")
            return True
        except Exception as e:
            print(f"  ✗ 订阅订单簿失败: {e}")
            return False

    async def subscribe_trade(self, market_id: int):
        """订阅成交信息"""
        if not self.ws:
            print(f"  ✗ 订阅成交失败: WebSocket 未连接")
            return False
        msg = {
            "action": "SUBSCRIBE",
            "channel": "market.last.trade",
            "marketId": market_id
        }
        try:
            await self.ws.send(json.dumps(msg))
            self.subscriptions.add(f"market.last.trade_{market_id}")
            print(f"  ✓ 已订阅成交 (marketId={market_id})")
            return True
        except Exception as e:
            print(f"  ✗ 订阅成交失败: {e}")
            return False

    async def subscribe_price(self, market_id: int):
        """订阅价格变动"""
        if not self.ws:
            return
        msg = {
            "action": "SUBSCRIBE",
            "channel": "market.last.price",
            "marketId": market_id
        }
        await self.ws.send(json.dumps(msg))
        self.subscriptions.add(f"market.last.price_{market_id}")
        print(f"  ✓ 已订阅价格 (marketId={market_id})")

    async def unsubscribe(self, channel: str, market_id: int):
        """取消订阅"""
        if not self.ws:
            return
        msg = {
            "action": "UNSUBSCRIBE",
            "channel": channel,
            "marketId": market_id
        }
        await self.ws.send(json.dumps(msg))
        self.subscriptions.discard(f"{channel}_{market_id}")

    async def receive_loop(self):
        """接收消息循环"""
        if not self.ws:
            return

        try:
            while not self._stop_event.is_set():
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                    await self._handle_message(msg)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if "ConnectionClosed" in str(type(e).__name__):
                        print("WebSocket 连接已关闭")
                        break
                    raise
        except Exception as e:
            print(f"WebSocket 接收错误: {e}")

    async def _handle_message(self, msg: str):
        """处理接收到的消息"""
        try:
            data = json.loads(msg)
            channel = data.get("channel", "")

            if channel == "market.depth.diff" and self.on_orderbook:
                self.on_orderbook(data)
            elif channel == "market.last.trade" and self.on_trade:
                self.on_trade(data)
            elif channel == "market.last.price" and self.on_price:
                self.on_price(data)

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"处理消息错误: {e}")


class WebSocketMonitor:
    """WebSocket 实时监控工具"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws_service = None
        self.market_titles = {}

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

    async def start_monitoring(self, market_ids: list, market_titles: dict = None,
                               subscribe_orderbook: bool = True,
                               subscribe_trade: bool = True,
                               subscribe_price: bool = True):
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
