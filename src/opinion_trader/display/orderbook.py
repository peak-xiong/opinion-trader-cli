"""
订单簿显示模块
"""
from typing import List, Tuple, Optional, Callable, Any


class OrderbookDisplay:
    """统一的订单簿显示模块"""

    # 显示模式
    MODE_SIMPLE = "simple"       # 简单模式：档位、数量、价格
    MODE_WITH_DEPTH = "depth"    # 深度模式：档位、深度、数量、价格

    @staticmethod
    def format_price(price: float) -> str:
        """格式化价格显示"""
        if price >= 1:
            return f"{price:.2f}"
        elif price >= 0.1:
            return f"{price:.3f}"
        else:
            return f"{price:.4f}"

    @staticmethod
    def show(
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        mode: str = "simple",
        max_rows: int = 5,
        title: str = "盘口信息",
        show_summary: bool = True,
        format_price_func: Optional[Callable[[float], str]] = None
    ) -> Tuple[float, float, float, float]:
        """统一显示订单簿

        Args:
            bids: 买盘列表 [(price, size), ...] 或 [(price, size, depth), ...] 已按价格降序排列
            asks: 卖盘列表 [(price, size), ...] 或 [(price, size, depth), ...] 已按价格升序排列
            mode: 显示模式 "simple" 或 "depth"
            max_rows: 最大显示行数
            title: 标题
            show_summary: 是否显示汇总信息
            format_price_func: 自定义价格格式化函数

        Returns:
            (bid1_price, ask1_price, bid_depth, ask_depth)
        """
        fmt_price = format_price_func or OrderbookDisplay.format_price

        # 计算深度（如果未提供）
        bid_details = []
        ask_details = []
        bid_depth = 0.0
        ask_depth = 0.0

        for i, bid in enumerate(bids[:max_rows]):
            if len(bid) >= 3:
                price, size, depth = bid[0], bid[1], bid[2]
            else:
                price, size = bid[0], bid[1]
                bid_depth += price * size
                depth = bid_depth
            bid_details.append((i + 1, price, size, depth))

        for i, ask in enumerate(asks[:max_rows]):
            if len(ask) >= 3:
                price, size, depth = ask[0], ask[1], ask[2]
            else:
                price, size = ask[0], ask[1]
                ask_depth += price * size
                depth = ask_depth
            ask_details.append((i + 1, price, size, depth))

        # 获取最终深度
        if bid_details:
            bid_depth = bid_details[-1][3]
        if ask_details:
            ask_depth = ask_details[-1][3]

        # 根据模式选择宽度
        if mode == OrderbookDisplay.MODE_WITH_DEPTH:
            # 深度模式: 档位(5) + 深度(12) + 数量(10) + 价格(9) = 36 每边
            width = 36
            total_width = width * 2 + 1  # 73
        else:
            # 简单模式: 档位(6) + 数量(12) + 价格(12) = 30 每边
            width = 30
            total_width = width * 2 + 1  # 61

        # 打印标题
        print(f"\n{'═'*total_width}")
        print(f"{title:^{total_width}}")
        print(f"{'═'*total_width}")

        # 打印表头
        print(f"{'─'*total_width}")
        print(f"{'买盘 (Bid)':^{width}}│{'卖盘 (Ask)':^{width}}")

        if mode == OrderbookDisplay.MODE_WITH_DEPTH:
            # 深度模式表头（考虑中文字符显示宽度=2）
            h_bid = "档位" + " "*11 + "深度" + " "*7 + "数量" + " "*4 + "价格"
            h_ask = "价格" + " "*4 + "数量" + " "*7 + "深度" + " "*11 + "档位"
            print(f"{h_bid}│{h_ask}")
        else:
            # 简单模式表头：档位 数量 价格│价格 数量 档位
            print(f"{'档位':<6}{'数量':>12}{'价格':>12}│{'价格':<12}{'数量':>12}{'档位':>6}")

        print(f"{'─'*total_width}")

        # 打印数据行
        rows = max(len(bid_details), len(ask_details))
        if rows == 0:
            print(f"{'(无买盘)':^{width}}│{'(无卖盘)':^{width}}")
        else:
            for i in range(rows):
                # 买盘（左边）：档位 深度 数量 价格
                if i < len(bid_details):
                    b_num, b_price, b_size, b_depth = bid_details[i]
                    price_str = fmt_price(b_price) + '¢'
                    if mode == OrderbookDisplay.MODE_WITH_DEPTH:
                        depth_str = f"${b_depth:,.2f}"
                        bid_str = f"买{b_num:<2}{depth_str:>15}{b_size:>11.1f}{price_str:>8}"
                    else:
                        bid_str = f"买{b_num:<5}{b_size:>12.1f}{price_str:>12}"
                else:
                    bid_str = f"{'':<{width}}"

                # 卖盘（右边）：价格 数量 深度 档位
                if i < len(ask_details):
                    a_num, a_price, a_size, a_depth = ask_details[i]
                    price_str = fmt_price(a_price) + '¢'
                    if mode == OrderbookDisplay.MODE_WITH_DEPTH:
                        depth_str = f"${a_depth:,.2f}"
                        ask_str = f"{price_str:<8}{a_size:>11.1f}{depth_str:>15}卖{a_num:>2}"
                    else:
                        ask_str = f"{price_str:<12}{a_size:>12.1f}  卖{a_num:>2}"
                else:
                    ask_str = f"{'':<{width}}"

                print(f"{bid_str}│{ask_str}")

        print(f"{'─'*total_width}")

        # 显示汇总
        if show_summary and (bid_details or ask_details):
            bid1_price = bid_details[0][1] if bid_details else 0
            ask1_price = ask_details[0][1] if ask_details else 0

            if bid1_price > 0 and ask1_price > 0:
                spread = ask1_price - bid1_price
                mid_price = (bid1_price + ask1_price) / 2
                print(
                    f"  价差: {spread:.2f}¢ | 中间价: {fmt_price(mid_price)}¢ | 买盘深度: ${bid_depth:.2f} | 卖盘深度: ${ask_depth:.2f}")
            else:
                print(f"  买盘深度: ${bid_depth:.2f} | 卖盘深度: ${ask_depth:.2f}")

        print(f"{'═'*total_width}")

        bid1 = bid_details[0][1] if bid_details else 0
        ask1 = ask_details[0][1] if ask_details else 0
        return (bid1, ask1, bid_depth, ask_depth)

    @staticmethod
    def show_from_orderbook(
        orderbook: Any,
        mode: str = "simple",
        max_rows: int = 5,
        title: str = "盘口信息",
        show_summary: bool = True,
        format_price_func: Optional[Callable[[float], str]] = None
    ) -> Tuple[float, float, float, float]:
        """从 orderbook 对象直接显示

        Args:
            orderbook: 包含 bids 和 asks 属性的订单簿对象
            其他参数同 show()

        Returns:
            (bid1_price, ask1_price, bid_depth, ask_depth)
        """
        bids = []
        asks = []

        if orderbook.bids:
            sorted_bids = sorted(
                orderbook.bids, key=lambda x: float(x.price), reverse=True)
            bids = [(float(b.price), float(b.size)) for b in sorted_bids]

        if orderbook.asks:
            sorted_asks = sorted(orderbook.asks, key=lambda x: float(x.price))
            asks = [(float(a.price), float(a.size)) for a in sorted_asks]

        return OrderbookDisplay.show(
            bids=bids, asks=asks, mode=mode, max_rows=max_rows,
            title=title, show_summary=show_summary, format_price_func=format_price_func
        )
