"""
订单簿服务模块 - 统一获取和解析订单簿数据
"""
from typing import Optional, Callable

from opinion_trader.display.orderbook import OrderbookDisplay


class OrderbookService:
    """订单簿服务模块 - 统一获取和解析订单簿数据"""

    @staticmethod
    def fetch(client, token_id: str, max_depth: int = 5) -> dict:
        """获取并解析订单簿

        Args:
            client: Opinion SDK客户端
            token_id: Token ID
            max_depth: 计算深度的最大档位数

        Returns:
            {
                'success': bool,
                'bids': [(price, size), ...],  # 按价格降序
                'asks': [(price, size), ...],  # 按价格升序
                'bid1_price': float,           # 买1价
                'ask1_price': float,           # 卖1价
                'bid1_size': float,            # 买1量
                'ask1_size': float,            # 卖1量
                'bid_depth': float,            # 买盘深度(美元)
                'ask_depth': float,            # 卖盘深度(美元)
                'spread': float,               # 价差
                'mid_price': float,            # 中间价
                'raw': orderbook对象,
                'error': str (如果失败)
            }
        """
        try:
            response = client.get_orderbook(token_id=token_id)
            if response.errno != 0:
                return {'success': False, 'error': response.errmsg if hasattr(response, 'errmsg') else '获取订单簿失败'}

            orderbook = response.result

            # 排序
            bids_sorted = sorted(orderbook.bids, key=lambda x: float(
                x.price), reverse=True) if orderbook.bids else []
            asks_sorted = sorted(orderbook.asks, key=lambda x: float(
                x.price)) if orderbook.asks else []

            # 转换为元组列表
            bids = [(float(b.price), float(b.size)) for b in bids_sorted]
            asks = [(float(a.price), float(a.size)) for a in asks_sorted]

            # 计算深度
            bid_depth = sum(price * size for price, size in bids[:max_depth])
            ask_depth = sum(price * size for price, size in asks[:max_depth])

            # 买1卖1
            bid1_price = bids[0][0] if bids else 0
            bid1_size = bids[0][1] if bids else 0
            ask1_price = asks[0][0] if asks else 0
            ask1_size = asks[0][1] if asks else 0

            # 价差和中间价
            spread = ask1_price - bid1_price if bid1_price > 0 and ask1_price > 0 else 0
            mid_price = (bid1_price + ask1_price) / \
                2 if bid1_price > 0 and ask1_price > 0 else 0

            return {
                'success': True,
                'bids': bids,
                'asks': asks,
                'bid1_price': bid1_price,
                'ask1_price': ask1_price,
                'bid1_size': bid1_size,
                'ask1_size': ask1_size,
                'bid_depth': bid_depth,
                'ask_depth': ask_depth,
                'spread': spread,
                'mid_price': mid_price,
                'raw': orderbook
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def fetch_and_display(
        client,
        token_id: str,
        title: str = "盘口信息",
        mode: str = "simple",
        max_rows: int = 5,
        format_price_func: Optional[Callable[[float], str]] = None
    ) -> dict:
        """获取订单簿并显示

        Returns:
            同 fetch() 返回值
        """
        result = OrderbookService.fetch(client, token_id, max_depth=max_rows)
        if result['success']:
            OrderbookDisplay.show(
                bids=result['bids'],
                asks=result['asks'],
                mode=mode,
                max_rows=max_rows,
                title=title,
                format_price_func=format_price_func
            )
        return result

    @staticmethod
    def check_liquidity(orderbook_result: dict, required_amount: float, side: str = 'buy') -> dict:
        """检查流动性是否充足

        Args:
            orderbook_result: fetch()的返回值
            required_amount: 需要的金额
            side: 'buy' 检查卖盘深度, 'sell' 检查买盘深度

        Returns:
            {
                'sufficient': bool,
                'available': float,
                'required': float,
                'shortage': float
            }
        """
        if not orderbook_result.get('success'):
            return {'sufficient': False, 'available': 0, 'required': required_amount, 'shortage': required_amount}

        available = orderbook_result['ask_depth'] if side == 'buy' else orderbook_result['bid_depth']
        shortage = max(0, required_amount - available)

        return {
            'sufficient': available >= required_amount,
            'available': available,
            'required': required_amount,
            'shortage': shortage
        }

    @staticmethod
    def get_price_at_level(orderbook_result: dict, side: str, level: int = 0, fallback: bool = True) -> float:
        """获取指定档位的价格

        Args:
            orderbook_result: fetch()的返回值
            side: 'bid' 获取买盘价格, 'ask' 获取卖盘价格
            level: 档位索引 (0=第1档, 1=第2档, ...)
            fallback: 如果指定档位不存在，是否回退到第1档

        Returns:
            价格，如果失败返回 0
        """
        if not orderbook_result.get('success'):
            return 0

        prices = orderbook_result['bids'] if side == 'bid' else orderbook_result['asks']
        if not prices:
            return 0

        if len(prices) > level:
            return prices[level][0]
        elif fallback and prices:
            return prices[0][0]
        return 0
