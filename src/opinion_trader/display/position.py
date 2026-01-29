"""
持仓和余额显示模块
"""
from typing import List, Optional, Tuple, Any


class PositionDisplay:
    """持仓显示模块"""

    @staticmethod
    def parse_sdk_position(position: Any) -> Optional[dict]:
        """从SDK的position对象解析出统一格式的数据

        Args:
            position: SDK返回的持仓对象

        Returns:
            解析后的字典，包含:
            - market_id: int
            - root_market_id: int
            - market_title: str
            - side: str
            - shares: int
            - current_value: float
            - cost: float
            - pnl: float
            - current_price: float
        """
        try:
            market_id = position.market_id if hasattr(
                position, 'market_id') else 0
            shares = int(float(position.shares_owned if hasattr(
                position, 'shares_owned') else 0))
            side = position.outcome_side_enum if hasattr(
                position, 'outcome_side_enum') else 'N/A'

            root_market_id = position.root_market_id if hasattr(
                position, 'root_market_id') and position.root_market_id else market_id
            market_title = position.market_title if hasattr(
                position, 'market_title') else None

            # 判断是否为子市场
            if root_market_id != market_id and market_title:
                display_title = market_title
            else:
                display_title = 'null'

            current_value = float(position.current_value_in_quote_token if hasattr(
                position, 'current_value_in_quote_token') and position.current_value_in_quote_token else 0)
            pnl = float(position.unrealized_pnl if hasattr(
                position, 'unrealized_pnl') and position.unrealized_pnl else 0)
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
    def show_positions_table(
        positions: List[dict],
        title: str = "持仓信息",
        show_summary: bool = True,
        indent: int = 2
    ) -> Tuple[float, float, float]:
        """显示持仓表格

        Args:
            positions: 持仓数据列表
            title: 标题
            show_summary: 是否显示汇总
            indent: 缩进

        Returns:
            (total_value, total_cost, total_pnl)
        """
        if not positions:
            print(f"{'  ' * (indent // 2)}无持仓")
            return 0, 0, 0

        prefix = " " * indent

        # 打印标题
        if title:
            print(f"\n{prefix}{title}")

        # 打印表格
        print(
            f"\n{prefix}┌────────┬──────────────────┬──────┬────────┬────────┬──────────┬──────────┬──────────┐")
        print(f"{prefix}│{'ParentID':^8}│{'ChildMarket':^18}│{'Side':^6}│{'Shares':^8}│{'Price':^8}│{'Value':^10}│{'Cost':^10}│{'P/L':^10}│")
        print(f"{prefix}├────────┼──────────────────┼──────┼────────┼────────┼──────────┼──────────┼──────────┤")

        total_value = 0
        total_cost = 0

        for pos in positions:
            root_market_id = pos.get(
                'root_market_id', pos.get('market_id', 'N/A'))
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
    def show_simple_positions_table(positions: List[dict], indent: int = 2):
        """显示简化的持仓表格（不含父市场ID）

        Args:
            positions: 持仓数据列表
            indent: 缩进
        """
        if not positions:
            print(f"{'  ' * (indent // 2)}无持仓")
            return

        prefix = " " * indent

        print(
            f"\n{prefix}┌──────┬────────┬────────┬──────────┬──────────┬──────────┐")
        print(
            f"{prefix}│{'Side':^6}│{'Shares':^8}│{'Price':^8}│{'Value':^10}│{'Cost':^10}│{'P/L':^10}│")
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

            print(
                f"{prefix}│{side:^6}│{shares:^8}│{price_str:^8}│{value_str:^10}│{cost_str:^10}│{pnl_str:^10}│")

        print(f"{prefix}└──────┴────────┴────────┴──────────┴──────────┴──────────┘")


class BalanceDisplay:
    """账户余额显示模块"""

    @staticmethod
    def show_balances(
        balances: List[dict],
        title: str = "账户余额",
        show_total: bool = True,
        num_width: int = 2,
        remark_width: int = 10
    ) -> float:
        """显示账户余额列表

        Args:
            balances: 余额数据列表，每项包含:
                - idx: 序号
                - remark: 备注
                - balance: 可用余额
                - total: 总余额（可选）
                - locked: 挂单占用（可选）
                - status: 状态 (ok, ok_locked, no_data, error)
                - error: 错误信息（可选）
            title: 标题
            show_total: 是否显示总计
            num_width: 序号宽度
            remark_width: 备注宽度

        Returns:
            总可用余额
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
                print(
                    f"  {idx:>{num_width}}  {remark:<{remark_width}}  余额: ${balance:>12.2f} (总${total:.2f}, 挂单占用${locked:.2f})")
                total_balance += balance
            elif status == 'ok':
                print(
                    f"  {idx:>{num_width}}  {remark:<{remark_width}}  余额: ${balance:>12.2f}")
                total_balance += balance
            elif status == 'no_data':
                print(
                    f"  {idx:>{num_width}}  {remark:<{remark_width}}  [!] 无余额数据")
            elif status == 'error':
                error = item.get('error', '未知错误')
                print(
                    f"  {idx:>{num_width}}  {remark:<{remark_width}}  ✗ {error}")

        if show_total:
            print(f"\n✓ 总可用余额: ${total_balance:.2f}")

        return total_balance

    @staticmethod
    def show_insufficient_warning(insufficient: List[dict]):
        """显示余额不足警告

        Args:
            insufficient: 列表，每项包含 remark, balance, required
        """
        if not insufficient:
            return

        print(f"\n[!] 余额不足警告:")
        for item in insufficient:
            remark = item.get('remark', '')
            balance = item.get('balance', 0)
            required = item.get('required', 0)
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")
