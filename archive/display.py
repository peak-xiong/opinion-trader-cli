"""
Opinion SDK 显示模块
包含所有UI显示相关的类
"""
import sys
import time
import threading


class ProgressBar:
    """进度条/动画显示工具"""

    @staticmethod
    def show_spinner(message: str, stop_event: threading.Event):
        """显示旋转动画（在后台线程运行）
        Args:
            message: 显示的消息
            stop_event: 停止事件
        """
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        idx = 0
        while not stop_event.is_set():
            sys.stdout.write(f'\r{spinner_chars[idx]} {message}')
            sys.stdout.flush()
            idx = (idx + 1) % len(spinner_chars)
            time.sleep(0.1)
        # 清除spinner行
        sys.stdout.write('\r' + ' ' * (len(message) + 4) + '\r')
        sys.stdout.flush()

    @staticmethod
    def show_progress(current: int, total: int, prefix: str = '', suffix: str = '', bar_length: int = 30):
        """显示进度条
        Args:
            current: 当前进度
            total: 总数
            prefix: 前缀文本
            suffix: 后缀文本
            bar_length: 进度条长度
        """
        if total == 0:
            percent = 100
        else:
            percent = current / total * 100
        filled = int(bar_length * current / total) if total > 0 else bar_length
        bar = '█' * filled + '░' * (bar_length - filled)
        sys.stdout.write(f'\r{prefix} [{bar}] {percent:.0f}% ({current}/{total}) {suffix}')
        sys.stdout.flush()
        if current >= total:
            print()  # 完成时换行

    @staticmethod
    def clear_line():
        """清除当前行"""
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()


class TableDisplay:
    """通用表格显示模块"""

    @staticmethod
    def print_table(headers: list, rows: list, col_widths: list = None,
                    alignments: list = None, title: str = None, indent: int = 2):
        """
        打印通用表格

        Args:
            headers: 表头列表 ["列1", "列2", ...]
            rows: 数据行列表 [["值1", "值2", ...], ...]
            col_widths: 列宽列表，None则自动计算
            alignments: 对齐方式列表 ["<", "^", ">"]，默认居中
            title: 表格标题
            indent: 缩进空格数
        """
        if not headers:
            return

        prefix = " " * indent
        num_cols = len(headers)

        # 自动计算列宽（如果未指定）
        if col_widths is None:
            col_widths = []
            for i, h in enumerate(headers):
                max_w = len(str(h)) + 2  # 表头宽度 + 边距
                for row in rows:
                    if i < len(row):
                        max_w = max(max_w, len(str(row[i])) + 2)
                col_widths.append(min(max_w, 20))  # 最大20字符

        # 默认对齐：居中
        if alignments is None:
            alignments = ["^"] * num_cols

        # 构建分隔线
        def make_line(left, mid, right, fill="─"):
            parts = [fill * w for w in col_widths]
            return prefix + left + mid.join(parts) + right

        top_line = make_line("┌", "┬", "┐")
        mid_line = make_line("├", "┼", "┤")
        bot_line = make_line("└", "┴", "┘")

        # 构建行
        def make_row(values):
            cells = []
            for i, v in enumerate(values):
                w = col_widths[i] if i < len(col_widths) else 10
                a = alignments[i] if i < len(alignments) else "^"
                cells.append(f"{str(v):{a}{w}}")
            return prefix + "│" + "│".join(cells) + "│"

        # 打印标题
        if title:
            print(f"\n{prefix}{title}")

        # 打印表格
        print(top_line)
        print(make_row(headers))
        print(mid_line)
        for row in rows:
            print(make_row(row))
        print(bot_line)

    @staticmethod
    def print_simple_header(title: str, width: int = 60, char: str = "─"):
        """打印简单的标题分隔线"""
        print(f"\n{char*width}")
        print(title)
        print(f"{char*width}")

    @staticmethod
    def print_section(title: str, width: int = 60):
        """打印区块标题"""
        print(f"\n{'='*width}")
        print(title)
        print(f"{'='*width}")


class PositionDisplay:
    """持仓显示模块"""

    @staticmethod
    def parse_sdk_position(position) -> dict:
        """
        从SDK的position对象解析出统一格式的数据

        Args:
            position: SDK返回的持仓对象

        Returns:
            {
                'market_id': int,
                'root_market_id': int,
                'market_title': str,
                'side': str,
                'shares': int,
                'current_value': float,
                'cost': float,
                'pnl': float,
                'current_price': float
            }
        """
        try:
            market_id = position.market_id if hasattr(position, 'market_id') else 0
            shares = int(float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
            side = position.outcome_side_enum if hasattr(position, 'outcome_side_enum') else 'N/A'

            root_market_id = position.root_market_id if hasattr(position, 'root_market_id') and position.root_market_id else market_id
            market_title = position.market_title if hasattr(position, 'market_title') else None

            # 判断是否为子市场
            if root_market_id != market_id and market_title:
                display_title = market_title
            else:
                display_title = 'null'

            current_value = float(position.current_value_in_quote_token if hasattr(position, 'current_value_in_quote_token') and position.current_value_in_quote_token else 0)
            pnl = float(position.unrealized_pnl if hasattr(position, 'unrealized_pnl') and position.unrealized_pnl else 0)
            cost = current_value - pnl
            current_price = current_value / shares if shares > 0 else 0

            return {
                'market_id': market_id,
                'root_market_id': root_market_id,
                'market_title': display_title,
                'side': side,
                'shares': shares,
                'current_value': current_value,
                'cost': cost,
                'pnl': pnl,
                'current_price': current_price
            }
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def show_positions_table(positions: list, title: str = "持仓信息",
                            show_summary: bool = True, indent: int = 2):
        """
        显示持仓表格

        Args:
            positions: 持仓数据列表，每项包含:
                {
                    'market_id': int,
                    'root_market_id': int,
                    'market_title': str,
                    'side': str,
                    'shares': int,
                    'current_value': float,
                    'cost': float,
                    'pnl': float,
                    'current_price': float
                }
            title: 标题
            show_summary: 是否显示汇总
            indent: 缩进
        """
        if not positions:
            print(f"{'  ' * (indent // 2)}无持仓")
            return 0, 0, 0

        prefix = " " * indent

        # 打印标题
        if title:
            print(f"\n{prefix}{title}")

        # 打印表格
        print(f"\n{prefix}┌────────┬──────────────────┬──────┬────────┬────────┬──────────┬──────────┬──────────┐")
        print(f"{prefix}│{'ParentID':^8}│{'ChildMarket':^18}│{'Side':^6}│{'Shares':^8}│{'Price':^8}│{'Value':^10}│{'Cost':^10}│{'P/L':^10}│")
        print(f"{prefix}├────────┼──────────────────┼──────┼────────┼────────┼──────────┼──────────┼──────────┤")

        total_value = 0
        total_cost = 0

        for pos in positions:
            root_market_id = pos.get('root_market_id', pos.get('market_id', 'N/A'))
            market_title = pos.get('market_title', 'null')
            child_name = market_title[:16] if market_title and market_title != 'null' else 'null'
            side = pos.get('side', 'N/A')
            shares = pos.get('shares', 0)
            current_value = pos.get('current_value', 0)
            cost = pos.get('cost', 0)
            pnl = pos.get('pnl', 0)
            current_price = pos.get('current_price', 0)

            total_value += current_value
            total_cost += cost

            price_str = f"{current_price*100:.1f}¢"
            value_str = f"${current_value:.2f}"
            cost_str = f"${cost:.2f}"
            pnl_str = f"{'+' if pnl >= 0 else ''}{pnl:.2f}"

            print(f"{prefix}│{root_market_id:^8}│{child_name:^18}│{side:^6}│{shares:^8}│{price_str:^8}│{value_str:^10}│{cost_str:^10}│{pnl_str:^10}│")

        print(f"{prefix}└────────┴──────────────────┴──────┴────────┴────────┴──────────┴──────────┴──────────┘")

        # 汇总
        if show_summary and (total_value > 0 or total_cost > 0):
            total_pnl = total_value - total_cost
            pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            print(f"{prefix}汇总: 市值 ${total_value:.2f} | 成本 ${total_cost:.2f} | 盈亏 {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} ({'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%)")

        return total_value, total_cost, total_value - total_cost

    @staticmethod
    def show_simple_positions_table(positions: list, indent: int = 2):
        """
        显示简化的持仓表格（不含父市场ID）

        Args:
            positions: 持仓数据列表
        """
        if not positions:
            print(f"{'  ' * (indent // 2)}无持仓")
            return

        prefix = " " * indent

        print(f"\n{prefix}┌──────┬────────┬────────┬──────────┬──────────┬──────────┐")
        print(f"{prefix}│{'Side':^6}│{'Shares':^8}│{'Price':^8}│{'Value':^10}│{'Cost':^10}│{'P/L':^10}│")
        print(f"{prefix}├──────┼────────┼────────┼──────────┼──────────┼──────────┤")

        for pos in positions:
            side = pos.get('side', 'N/A')
            shares = pos.get('shares', 0)
            current_value = pos.get('current_value', 0)
            cost = pos.get('cost', 0)
            pnl = pos.get('pnl', 0)
            current_price = pos.get('current_price', 0)

            price_str = f"{current_price*100:.1f}¢"
            value_str = f"${current_value:.2f}"
            cost_str = f"${cost:.2f}"
            pnl_str = f"{'+' if pnl >= 0 else ''}{pnl:.2f}"

            print(f"{prefix}│{side:^6}│{shares:^8}│{price_str:^8}│{value_str:^10}│{cost_str:^10}│{pnl_str:^10}│")

        print(f"{prefix}└──────┴────────┴────────┴──────────┴──────────┴──────────┘")


class BalanceDisplay:
    """账户余额显示模块"""

    @staticmethod
    def show_balances(balances: list, title: str = "账户余额",
                     show_total: bool = True, num_width: int = 2, remark_width: int = 10):
        """
        显示账户余额列表

        Args:
            balances: 余额数据列表
                [
                    {
                        'idx': int,           # 序号
                        'remark': str,        # 备注
                        'balance': float,     # 可用余额
                        'total': float,       # 总余额（可选）
                        'locked': float,      # 挂单占用（可选）
                        'status': str,        # 状态: ok, ok_locked, no_data, error
                        'error': str          # 错误信息（可选）
                    },
                    ...
                ]
            title: 标题
            show_total: 是否显示总计
            num_width: 序号宽度
            remark_width: 备注宽度
        """
        if title:
            print(f"\n{title}")

        total_balance = 0

        for item in balances:
            idx = item.get('idx', 0)
            remark = item.get('remark', '')
            balance = item.get('balance', 0)
            status = item.get('status', 'ok')

            if status == 'ok_locked':
                total = item.get('total', balance)
                locked = item.get('locked', 0)
                print(f"  {idx:>{num_width}}  {remark:<{remark_width}}  余额: ${balance:>12.2f} (总${total:.2f}, 挂单占用${locked:.2f})")
                total_balance += balance
            elif status == 'ok':
                print(f"  {idx:>{num_width}}  {remark:<{remark_width}}  余额: ${balance:>12.2f}")
                total_balance += balance
            elif status == 'no_data':
                print(f"  {idx:>{num_width}}  {remark:<{remark_width}}  [!] 无余额数据")
            elif status == 'error':
                error = item.get('error', '未知错误')
                print(f"  {idx:>{num_width}}  {remark:<{remark_width}}  ✗ {error}")

        if show_total:
            print(f"\n✓ 总可用余额: ${total_balance:.2f}")

        return total_balance

    @staticmethod
    def show_insufficient_warning(insufficient: list):
        """
        显示余额不足警告

        Args:
            insufficient: [{'remark': str, 'balance': float, 'required': float}, ...]
        """
        if not insufficient:
            return

        print(f"\n[!] 余额不足警告:")
        for item in insufficient:
            remark = item.get('remark', '')
            balance = item.get('balance', 0)
            required = item.get('required', 0)
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")


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
    def show_orders_table(orders: list, title: str = None, indent: int = 2,
                         format_price_func=None):
        """
        显示挂单表格

        Args:
            orders: 挂单数据列表
                [
                    {
                        'order_id': str,
                        'root_market_id': int,
                        'market_title': str,
                        'side': str,  # 'BUY' or 'SELL'
                        'price': float,
                        'order_shares': int,
                        'filled_shares': int
                    },
                    ...
                ]
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

        print(f"\n{prefix}┌──────────┬────────┬────────────┬──────┬────────┬────────┬────────┐")
        print(f"{prefix}│{'OrderID':^10}│{'ParentID':^8}│{'ChildName':^12}│{'Side':^6}│{'Price':^8}│{'Qty':^8}│{'Filled':^8}│")
        print(f"{prefix}├──────────┼────────┼────────────┼──────┼────────┼────────┼────────┤")

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

        print(f"{prefix}└──────────┴────────┴────────────┴──────┴────────┴────────┴────────┘")

    @staticmethod
    def parse_sdk_order(order) -> dict:
        """
        从SDK的order对象解析出统一格式的数据

        Args:
            order: SDK返回的挂单对象

        Returns:
            解析后的字典
        """
        try:
            order_id = order.order_id if hasattr(order, 'order_id') else 'N/A'
            order_market_id = order.market_id if hasattr(order, 'market_id') else 'N/A'
            side = 'BUY' if (hasattr(order, 'side') and order.side == 1) else 'SELL'
            price = float(order.price if hasattr(order, 'price') else 0)
            order_shares = int(float(order.order_shares if hasattr(order, 'order_shares') else 0))
            filled_shares = int(float(order.filled_shares if hasattr(order, 'filled_shares') else 0))

            root_market_id = order.root_market_id if hasattr(order, 'root_market_id') and order.root_market_id else None
            market_title = order.market_title if hasattr(order, 'market_title') else None

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
    def show(bids: list, asks: list, mode: str = "simple",
             max_rows: int = 5, title: str = "盘口信息",
             show_summary: bool = True, format_price_func=None) -> tuple:
        """
        统一显示订单簿

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
            # 数据格式: 档位(4) + 深度(15) + 数量(11) + 价格(8) = 38显示宽度
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
                print(f"  价差: {spread:.2f}¢ | 中间价: {fmt_price(mid_price)}¢ | 买盘深度: ${bid_depth:.2f} | 卖盘深度: ${ask_depth:.2f}")
            else:
                print(f"  买盘深度: ${bid_depth:.2f} | 卖盘深度: ${ask_depth:.2f}")

        print(f"{'═'*total_width}")

        bid1 = bid_details[0][1] if bid_details else 0
        ask1 = ask_details[0][1] if ask_details else 0
        return (bid1, ask1, bid_depth, ask_depth)

    @staticmethod
    def show_from_orderbook(orderbook, mode: str = "simple", max_rows: int = 5,
                            title: str = "盘口信息", show_summary: bool = True,
                            format_price_func=None) -> tuple:
        """
        从 orderbook 对象直接显示

        Args:
            orderbook: 包含 bids 和 asks 属性的订单簿对象
            其他参数同 show()

        Returns:
            (bid1_price, ask1_price, bid_depth, ask_depth)
        """
        bids = []
        asks = []

        if orderbook.bids:
            sorted_bids = sorted(orderbook.bids, key=lambda x: float(x.price), reverse=True)
            bids = [(float(b.price), float(b.size)) for b in sorted_bids]

        if orderbook.asks:
            sorted_asks = sorted(orderbook.asks, key=lambda x: float(x.price))
            asks = [(float(a.price), float(a.size)) for a in sorted_asks]

        return OrderbookDisplay.show(
            bids=bids, asks=asks, mode=mode, max_rows=max_rows,
            title=title, show_summary=show_summary, format_price_func=format_price_func
        )
