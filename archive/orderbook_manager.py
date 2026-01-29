"""
订单簿管理模块
实现「主动查询 + WS 推送兜底」模式
"""
import asyncio
import time
import threading
from typing import Dict, Callable, Optional, List, Tuple
from dataclasses import dataclass, field


@dataclass
class OrderbookState:
    """订单簿本地状态"""
    bids: List[Tuple[float, float]] = field(default_factory=list)  # [(price, size), ...] 按价格降序
    asks: List[Tuple[float, float]] = field(default_factory=list)  # [(price, size), ...] 按价格升序
    last_update_time: float = 0  # 最后更新时间戳
    last_ws_time: float = 0  # 最后 WS 消息时间
    source: str = ""  # 数据来源: 'rest' 或 'ws'

    @property
    def bid1_price(self) -> float:
        """买1价"""
        return self.bids[0][0] if self.bids else 0

    @property
    def bid1_size(self) -> float:
        """买1量"""
        return self.bids[0][1] if self.bids else 0

    @property
    def ask1_price(self) -> float:
        """卖1价"""
        return self.asks[0][0] if self.asks else 0

    @property
    def ask1_size(self) -> float:
        """卖1量"""
        return self.asks[0][1] if self.asks else 0

    @property
    def mid_price(self) -> float:
        """中间价"""
        if self.bid1_price > 0 and self.ask1_price > 0:
            return (self.bid1_price + self.ask1_price) / 2
        return 0

    @property
    def spread(self) -> float:
        """价差"""
        if self.bid1_price > 0 and self.ask1_price > 0:
            return self.ask1_price - self.bid1_price
        return 0

    def get_bid_depth(self, levels: int = 5) -> float:
        """获取买盘深度（美元）"""
        return sum(price * size for price, size in self.bids[:levels])

    def get_ask_depth(self, levels: int = 5) -> float:
        """获取卖盘深度（美元）"""
        return sum(price * size for price, size in self.asks[:levels])

    def get_price_at_level(self, side: str, level: int = 0) -> float:
        """获取指定档位价格

        Args:
            side: 'bid' 或 'ask'
            level: 档位索引（0=第1档）
        """
        prices = self.bids if side == 'bid' else self.asks
        if prices and len(prices) > level:
            return prices[level][0]
        return 0


class OrderbookManager:
    """订单簿管理器

    实现「主动查询 + WS 推送兜底」模式:
    1. 初始化时通过 REST API 主动查询订单簿
    2. 之后监听 WS 推送实时更新
    3. 超时兜底：N 秒无 WS 消息自动触发 REST 查询
    """

    DEFAULT_WS_TIMEOUT = 10  # 默认 WS 超时时间（秒）

    def __init__(self, client, token_id: str,
                 ws_timeout: float = DEFAULT_WS_TIMEOUT,
                 on_update: Optional[Callable[[OrderbookState], None]] = None):
        """
        Args:
            client: Opinion SDK 客户端
            token_id: Token ID
            ws_timeout: WS 超时时间（秒），超时后触发 REST 查询
            on_update: 订单簿更新回调
        """
        self.client = client
        self.token_id = token_id
        self.ws_timeout = ws_timeout
        self.on_update = on_update

        # 本地订单簿状态
        self.state = OrderbookState()

        # 线程安全锁
        self._lock = threading.Lock()

        # 超时监控
        self._timeout_timer: Optional[threading.Timer] = None
        self._running = False

    def fetch_orderbook_rest(self) -> bool:
        """通过 REST API 查询订单簿

        Returns:
            bool: 是否成功
        """
        try:
            response = self.client.get_orderbook(token_id=self.token_id)
            if response.errno != 0:
                print(f"  [OrderbookManager] REST 查询失败: {response.errmsg}")
                return False

            orderbook = response.result

            # 排序并转换
            bids_sorted = sorted(orderbook.bids, key=lambda x: float(x.price), reverse=True) if orderbook.bids else []
            asks_sorted = sorted(orderbook.asks, key=lambda x: float(x.price)) if orderbook.asks else []

            bids = [(float(b.price), float(b.size)) for b in bids_sorted]
            asks = [(float(a.price), float(a.size)) for a in asks_sorted]

            # 更新状态
            with self._lock:
                self.state.bids = bids
                self.state.asks = asks
                self.state.last_update_time = time.time()
                self.state.source = 'rest'

            # 触发回调
            if self.on_update:
                self.on_update(self.state)

            return True

        except Exception as e:
            print(f"  [OrderbookManager] REST 查询异常: {e}")
            return False

    def handle_ws_orderbook(self, data: dict):
        """处理 WS 订单簿推送

        Args:
            data: WS 消息数据，格式示例:
                {
                    'channel': 'market.depth.diff',
                    'marketId': 123,
                    'side': 'bids' or 'asks',
                    'price': '0.50',
                    'size': 100,  # 0 表示删除该价位
                    'outcomeSide': 1 or 2
                }
        """
        try:
            side = data.get('side', '')
            price = float(data.get('price', 0))
            size = float(data.get('size', 0))

            if not side or price <= 0:
                return

            with self._lock:
                if side == 'bids':
                    self._update_orderbook_side(self.state.bids, price, size, reverse=True)
                elif side == 'asks':
                    self._update_orderbook_side(self.state.asks, price, size, reverse=False)

                self.state.last_update_time = time.time()
                self.state.last_ws_time = time.time()
                self.state.source = 'ws'

            # 重置超时计时器
            self._reset_timeout_timer()

            # 触发回调
            if self.on_update:
                self.on_update(self.state)

        except Exception as e:
            print(f"  [OrderbookManager] WS 处理异常: {e}")

    def _update_orderbook_side(self, orders: list, price: float, size: float, reverse: bool):
        """更新订单簿某一侧

        Args:
            orders: 买盘或卖盘列表
            price: 价格
            size: 数量，0 表示删除
            reverse: 是否降序（买盘 True，卖盘 False）
        """
        # 查找该价位是否存在
        idx = None
        for i, (p, _) in enumerate(orders):
            if abs(p - price) < 1e-8:  # 浮点数比较
                idx = i
                break

        if size <= 0:
            # 删除该价位
            if idx is not None:
                orders.pop(idx)
        else:
            if idx is not None:
                # 更新现有价位
                orders[idx] = (price, size)
            else:
                # 插入新价位（保持排序）
                orders.append((price, size))
                orders.sort(key=lambda x: x[0], reverse=reverse)

    def _reset_timeout_timer(self):
        """重置超时计时器"""
        if self._timeout_timer:
            self._timeout_timer.cancel()

        if self._running:
            self._timeout_timer = threading.Timer(
                self.ws_timeout,
                self._on_ws_timeout
            )
            self._timeout_timer.daemon = True
            self._timeout_timer.start()

    def _on_ws_timeout(self):
        """WS 超时回调"""
        if not self._running:
            return

        print(f"  [OrderbookManager] WS 超时（{self.ws_timeout}秒无消息），触发 REST 查询")
        self.fetch_orderbook_rest()

        # 重新启动计时器
        self._reset_timeout_timer()

    def start(self) -> bool:
        """启动订单簿管理器

        1. 先通过 REST 查询初始订单簿
        2. 启动 WS 超时监控

        Returns:
            bool: 是否成功初始化
        """
        print(f"  [OrderbookManager] 启动，token_id={self.token_id}")

        # 1. REST 查询初始数据
        if not self.fetch_orderbook_rest():
            print(f"  [OrderbookManager] 初始化失败：无法获取订单簿")
            return False

        print(f"  [OrderbookManager] 初始化成功，买1={self.state.bid1_price:.4f}，卖1={self.state.ask1_price:.4f}")

        # 2. 启动超时监控
        self._running = True
        self._reset_timeout_timer()

        return True

    def stop(self):
        """停止订单簿管理器"""
        self._running = False
        if self._timeout_timer:
            self._timeout_timer.cancel()
            self._timeout_timer = None
        print(f"  [OrderbookManager] 已停止")

    def get_state(self) -> OrderbookState:
        """获取当前订单簿状态（线程安全）"""
        with self._lock:
            # 返回副本，避免外部修改
            return OrderbookState(
                bids=list(self.state.bids),
                asks=list(self.state.asks),
                last_update_time=self.state.last_update_time,
                last_ws_time=self.state.last_ws_time,
                source=self.state.source
            )

    def refresh(self) -> bool:
        """手动刷新订单簿（强制 REST 查询）"""
        return self.fetch_orderbook_rest()


class MultiTokenOrderbookManager:
    """多交易对订单簿管理器

    管理多个 token 的订单簿，便于扩展到多市场交易
    """

    def __init__(self, client, ws_timeout: float = OrderbookManager.DEFAULT_WS_TIMEOUT):
        self.client = client
        self.ws_timeout = ws_timeout
        self._managers: Dict[str, OrderbookManager] = {}
        self._lock = threading.Lock()

    def add_token(self, token_id: str,
                  on_update: Optional[Callable[[OrderbookState], None]] = None) -> OrderbookManager:
        """添加交易对

        Args:
            token_id: Token ID
            on_update: 更新回调

        Returns:
            OrderbookManager: 该交易对的管理器
        """
        with self._lock:
            if token_id not in self._managers:
                manager = OrderbookManager(
                    client=self.client,
                    token_id=token_id,
                    ws_timeout=self.ws_timeout,
                    on_update=on_update
                )
                self._managers[token_id] = manager
            return self._managers[token_id]

    def get_manager(self, token_id: str) -> Optional[OrderbookManager]:
        """获取指定交易对的管理器"""
        with self._lock:
            return self._managers.get(token_id)

    def get_state(self, token_id: str) -> Optional[OrderbookState]:
        """获取指定交易对的订单簿状态"""
        manager = self.get_manager(token_id)
        if manager:
            return manager.get_state()
        return None

    def start_all(self) -> int:
        """启动所有管理器

        Returns:
            int: 成功启动的数量
        """
        success_count = 0
        with self._lock:
            for token_id, manager in self._managers.items():
                if manager.start():
                    success_count += 1
        return success_count

    def stop_all(self):
        """停止所有管理器"""
        with self._lock:
            for manager in self._managers.values():
                manager.stop()

    def handle_ws_message(self, data: dict):
        """处理 WS 消息，分发到对应的管理器

        Args:
            data: WS 消息数据
        """
        # 从消息中提取 token_id
        # 注意：实际实现需要根据 WS 消息格式调整
        token_id = data.get('tokenId') or data.get('token_id')
        if token_id:
            manager = self.get_manager(str(token_id))
            if manager:
                manager.handle_ws_orderbook(data)
