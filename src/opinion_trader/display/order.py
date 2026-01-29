"""
挂单显示模块
"""
from typing import List, Optional, Callable, Any


class OrderDisplay:
    """挂单显示模块"""

    @staticmethod
    def format_price(price: float) -> str:
        """格式化价格显示"""
        price_cent = price * 100
        if price_cent == int(price_cent):
            return f"{int(price_cent)}"
        return f"{price_cent:.10g}"

    @staticmethod
    def show_orders_table(
        orders: List[dict],
        title: Optional[str] = None,
        indent: int = 2,
        format_price_func: Optional[Callable[[float], str]] = None
    ):
        """显示挂单表格

        Args:
            orders: 挂单数据列表，每项包含:
                - order_id: 订单ID
                - root_market_id: 父市场ID
                - market_title: 市场标题
                - side: 方向 ('BUY' or 'SELL')
                - price: 价格
                - order_shares: 订单数量
                - filled_shares: 已成交数量
            title: 标题
            indent: 缩进
            format_price_func: 自定义价格格式化函数
        """
        if not orders:
            print(f"{' ' * indent}无挂单")
            return

        fmt_price = format_price_func or OrderDisplay.format_price
        prefix = " " * indent

        if title:
            print(f"\n{prefix}{title}")

        print(
            f"\n{prefix}┌──────────┬────────┬────────────┬──────┬────────┬────────┬────────┐")
        print(f"{prefix}│{'OrderID':^10}│{'ParentID':^8}│{'ChildName':^12}│{'Side':^6}│{'Price':^8}│{'Qty':^8}│{'Filled':^8}│")
        print(
            f"{prefix}├──────────┼────────┼────────────┼──────┼────────┼────────┼────────┤")

        for order in orders:
            order_id = order.get('order_id', 'N/A')
            order_id_short = str(order_id).split('-')[0] if order_id else 'N/A'
            root_market_id = order.get('root_market_id', 'N/A')
            market_title = order.get('market_title', 'null')
            child_name = market_title[:10] if market_title and market_title != 'null' else 'null'
            side = order.get('side', 'N/A')
            price = order.get('price', 0)
            order_shares = order.get('order_shares', 0)
            filled_shares = order.get('filled_shares', 0)

            price_display = fmt_price(price) + '¢'

            print(f"{prefix}│{order_id_short:^10}│{root_market_id:^8}│{child_name:^12}│{side:^6}│{price_display:^8}│{order_shares:^8}│{filled_shares:^8}│")

        print(
            f"{prefix}└──────────┴────────┴────────────┴──────┴────────┴────────┴────────┘")

    @staticmethod
    def parse_sdk_order(order: Any) -> Optional[dict]:
        """从SDK的order对象解析出统一格式的数据

        Args:
            order: SDK返回的挂单对象

        Returns:
            解析后的字典，包含:
            - order_id: str
            - root_market_id: int
            - market_title: str
            - side: str
            - price: float
            - order_shares: int
            - filled_shares: int
        """
        try:
            order_id = order.order_id if hasattr(order, 'order_id') else 'N/A'
            order_market_id = order.market_id if hasattr(
                order, 'market_id') else 'N/A'
            side = 'BUY' if (hasattr(order, 'side')
                             and order.side == 1) else 'SELL'
            price = float(order.price if hasattr(order, 'price') else 0)
            order_shares = int(
                float(order.order_shares if hasattr(order, 'order_shares') else 0))
            filled_shares = int(
                float(order.filled_shares if hasattr(order, 'filled_shares') else 0))

            root_market_id = order.root_market_id if hasattr(
                order, 'root_market_id') and order.root_market_id else None
            market_title = order.market_title if hasattr(
                order, 'market_title') else None

            if root_market_id and root_market_id != order_market_id:
                p_id = root_market_id
                c_name = market_title if market_title else 'null'
            else:
                p_id = order_market_id
                c_name = 'null'

            return {
                'order_id': order_id,
                'root_market_id': p_id,
                'market_title': c_name,
                'side': side,
                'price': price,
                'order_shares': order_shares,
                'filled_shares': filled_shares
            }
        except (ValueError, TypeError, AttributeError):
            return None
