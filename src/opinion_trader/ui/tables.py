"""
表格显示封装

提供常用的表格显示功能，包括：
- 账户余额表格
- 持仓表格
- 挂单表格
- 市场列表表格
"""
from typing import List, Dict, Any, Optional
from rich.table import Table
from rich.box import ROUNDED, SIMPLE, MINIMAL
from opinion_trader.ui.console import console, create_table, print_table


def accounts_table(
    accounts: List[Dict[str, Any]],
    title: str = "账户列表",
    show_balance: bool = True,
) -> None:
    """
    显示账户列表表格
    
    Args:
        accounts: 账户数据列表
            [{"remark": "xxx", "address": "0x...", "balance": 100.0}, ...]
        title: 标题
        show_balance: 是否显示余额
    """
    t = Table(title=title, show_header=True, header_style="bold cyan", box=ROUNDED)
    t.add_column("#", style="dim", width=4)
    t.add_column("备注", style="white")
    t.add_column("地址", style="dim")
    if show_balance:
        t.add_column("余额", justify="right", style="green")
    
    for idx, acc in enumerate(accounts, 1):
        row = [
            str(idx),
            acc.get('remark', f'账户{idx}'),
            _short_address(acc.get('address', '')),
        ]
        if show_balance:
            balance = acc.get('balance', 0)
            row.append(f"${balance:.2f}")
        t.add_row(*row)
    
    console.print(t)


def positions_table(
    positions: List[Dict[str, Any]],
    title: str = "持仓列表",
    show_pnl: bool = True,
) -> None:
    """
    显示持仓表格
    
    Args:
        positions: 持仓数据列表
            [{"market": "xxx", "side": "YES", "shares": 100, "cost": 95.0, "current": 97.0}, ...]
        title: 标题
        show_pnl: 是否显示盈亏
    """
    t = Table(title=title, show_header=True, header_style="bold magenta", box=ROUNDED)
    t.add_column("市场", style="white", max_width=30)
    t.add_column("方向", justify="center", width=6)
    t.add_column("数量", justify="right", style="cyan")
    t.add_column("成本", justify="right")
    t.add_column("现价", justify="right")
    if show_pnl:
        t.add_column("盈亏", justify="right")
    
    for pos in positions:
        side = pos.get('side', 'YES')
        side_style = "[green]YES[/green]" if side == 'YES' else "[red]NO[/red]"
        
        row = [
            _truncate(pos.get('market', '未知'), 30),
            side_style,
            str(pos.get('shares', 0)),
            f"{pos.get('cost', 0):.1f}¢",
            f"{pos.get('current', 0):.1f}¢",
        ]
        
        if show_pnl:
            pnl = pos.get('pnl', 0)
            pnl_style = f"[green]+${pnl:.2f}[/green]" if pnl >= 0 else f"[red]-${abs(pnl):.2f}[/red]"
            row.append(pnl_style)
        
        t.add_row(*row)
    
    console.print(t)


def orders_table(
    orders: List[Dict[str, Any]],
    title: str = "挂单列表",
) -> None:
    """
    显示挂单表格
    
    Args:
        orders: 挂单数据列表
            [{"id": "xxx", "market": "xxx", "side": "BUY", "price": 95.0, "amount": 100}, ...]
        title: 标题
    """
    t = Table(title=title, show_header=True, header_style="bold yellow", box=ROUNDED)
    t.add_column("订单ID", style="dim", width=12)
    t.add_column("市场", style="white", max_width=25)
    t.add_column("方向", justify="center", width=6)
    t.add_column("价格", justify="right")
    t.add_column("数量", justify="right", style="cyan")
    t.add_column("金额", justify="right", style="green")
    
    for order in orders:
        side = order.get('side', 'BUY')
        side_style = "[green]买[/green]" if side == 'BUY' else "[red]卖[/red]"
        
        t.add_row(
            _short_id(order.get('id', '')),
            _truncate(order.get('market', '未知'), 25),
            side_style,
            f"{order.get('price', 0):.1f}¢",
            str(order.get('amount', 0)),
            f"${order.get('value', 0):.2f}",
        )
    
    console.print(t)


def markets_table(
    markets: List[Dict[str, Any]],
    title: str = "市场列表",
    show_link: bool = False,
) -> None:
    """
    显示市场列表表格
    
    Args:
        markets: 市场数据列表
            [{"id": 123, "title": "xxx", "end_time": "2024-01-01", "is_categorical": False}, ...]
        title: 标题
        show_link: 是否显示链接
    """
    t = Table(title=title, show_header=True, header_style="bold blue", box=ROUNDED)
    t.add_column("ID", style="cyan", width=8)
    t.add_column("到期时间", width=14)
    t.add_column("市场名称", style="white")
    if show_link:
        t.add_column("链接", style="dim")
    
    for m in markets:
        market_id = m.get('id', '?')
        market_title = m.get('title', '未知')
        is_categorical = m.get('is_categorical', False)
        
        if is_categorical:
            market_title += " [dim][分类][/dim]"
        
        row = [
            str(market_id),
            m.get('end_time', '-'),
            _truncate(market_title, 50),
        ]
        
        if show_link:
            row.append(f"https://opinion.trade/market/{market_id}")
        
        t.add_row(*row)
    
    console.print(t)


def orderbook_table(
    bids: List[Dict[str, Any]],
    asks: List[Dict[str, Any]],
    title: str = "盘口深度",
    levels: int = 5,
) -> None:
    """
    显示盘口深度表格
    
    Args:
        bids: 买单列表 [{"price": 95.0, "amount": 100}, ...]
        asks: 卖单列表 [{"price": 96.0, "amount": 100}, ...]
        title: 标题
        levels: 显示档位数
    """
    t = Table(title=title, show_header=True, header_style="bold", box=SIMPLE)
    t.add_column("买价", justify="right", style="green")
    t.add_column("买量", justify="right", style="green")
    t.add_column("", width=3)
    t.add_column("卖价", justify="right", style="red")
    t.add_column("卖量", justify="right", style="red")
    
    # 对齐买卖单
    max_levels = max(len(bids), len(asks), levels)
    
    for i in range(min(max_levels, levels)):
        bid = bids[i] if i < len(bids) else None
        ask = asks[i] if i < len(asks) else None
        
        t.add_row(
            f"{bid['price']:.1f}¢" if bid else "-",
            str(bid['amount']) if bid else "-",
            "│",
            f"{ask['price']:.1f}¢" if ask else "-",
            str(ask['amount']) if ask else "-",
        )
    
    console.print(t)


def summary_table(
    data: Dict[str, Any],
    title: str = "汇总",
) -> None:
    """
    显示汇总表格（键值对形式）
    
    Args:
        data: 数据字典 {"总资产": "$1000", "盈亏": "+$50", ...}
        title: 标题
    """
    t = Table(title=title, show_header=False, box=MINIMAL)
    t.add_column("项目", style="dim")
    t.add_column("数值", style="bold")
    
    for key, value in data.items():
        t.add_row(key, str(value))
    
    console.print(t)


def trade_summary_table(
    trades: List[Dict[str, Any]],
    title: str = "交易汇总",
) -> None:
    """
    显示交易汇总表格
    
    Args:
        trades: 交易记录列表
            [{"account": "xxx", "side": "BUY", "shares": 100, "price": 95.0, "status": "成功"}, ...]
        title: 标题
    """
    t = Table(title=title, show_header=True, header_style="bold", box=ROUNDED)
    t.add_column("账户", style="cyan")
    t.add_column("方向", justify="center", width=6)
    t.add_column("数量", justify="right")
    t.add_column("价格", justify="right")
    t.add_column("金额", justify="right", style="green")
    t.add_column("状态", justify="center")
    
    total_amount = 0
    total_shares = 0
    
    for trade in trades:
        side = trade.get('side', 'BUY')
        side_style = "[green]买入[/green]" if side == 'BUY' else "[red]卖出[/red]"
        
        status = trade.get('status', '成功')
        status_style = "[green]✓[/green]" if status == '成功' else "[red]✗[/red]"
        
        shares = trade.get('shares', 0)
        price = trade.get('price', 0)
        amount = shares * price / 100
        
        total_shares += shares
        total_amount += amount
        
        t.add_row(
            trade.get('account', '?'),
            side_style,
            str(shares),
            f"{price:.1f}¢",
            f"${amount:.2f}",
            status_style,
        )
    
    # 添加汇总行
    t.add_row(
        "[bold]合计[/bold]",
        "",
        f"[bold]{total_shares}[/bold]",
        "",
        f"[bold green]${total_amount:.2f}[/bold green]",
        "",
    )
    
    console.print(t)


# ============ 辅助函数 ============

def _short_address(address: str, length: int = 10) -> str:
    """缩短地址显示"""
    if not address:
        return "-"
    if len(address) <= length * 2:
        return address
    return f"{address[:length]}...{address[-length:]}"


def _short_id(order_id: str, length: int = 8) -> str:
    """缩短ID显示"""
    if not order_id:
        return "-"
    if len(order_id) <= length:
        return order_id
    return f"{order_id[:length]}..."


def _truncate(text: str, max_length: int) -> str:
    """截断文本"""
    if not text:
        return "-"
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
