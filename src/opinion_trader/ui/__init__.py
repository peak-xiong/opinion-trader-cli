"""
UI 交互模块

提供统一的用户交互接口，包括：
- console: 基础输出（成功/错误/警告/表格等）
- prompts: 交互式输入（账户选择/市场选择/确认等）
- menus: 菜单系统
- tables: 表格显示
"""

from opinion_trader.ui.console import (
    # 核心对象
    console,
    # 消息输出
    success, error, warning, info, dim,
    # 标题布局
    header, section, divider, rule, banner, clear,
    # 键值
    kv, bullet,
    # 基础交互
    select, select_multiple, confirm, pause,
    ask, ask_int, ask_float, ask_password,
    # 表格
    table, create_table, print_table,
    # 进度
    spinner, progress_bar,
    # 特殊
    code, json_print,
    # 打印
    print, log,
)

from opinion_trader.ui.prompts import (
    # 账户相关
    select_accounts,
    select_single_account,
    # 市场相关
    select_market,
    input_market_id,
    # 通用
    confirm_action,
    input_amount,
    input_price,
    input_shares,
)

from opinion_trader.ui.menus import (
    Menu,
    MenuItem,
    MainMenu,
    TradingMenu,
    MergeSplitMenu,
    CancelOrdersMenu,
    QueryPositionMenu,
    ClaimMenu,
    create_menu,
)

from opinion_trader.ui.tables import (
    accounts_table,
    positions_table,
    orders_table,
    markets_table,
    orderbook_table,
    summary_table,
    trade_summary_table,
)

__all__ = [
    # console
    "console",
    "success", "error", "warning", "info", "dim",
    "header", "section", "divider", "rule", "banner", "clear",
    "kv", "bullet",
    "select", "select_multiple", "confirm", "pause",
    "ask", "ask_int", "ask_float", "ask_password",
    "table", "create_table", "print_table",
    "spinner", "progress_bar",
    "code", "json_print",
    "print", "log",
    # prompts
    "select_accounts",
    "select_single_account",
    "select_market",
    "input_market_id",
    "confirm_action",
    "input_amount",
    "input_price",
    "input_shares",
    # menus
    "Menu",
    "MenuItem",
    "MainMenu",
    "TradingMenu",
    "MergeSplitMenu",
    "CancelOrdersMenu",
    "QueryPositionMenu",
    "ClaimMenu",
    "create_menu",
    # tables
    "accounts_table",
    "positions_table",
    "orders_table",
    "markets_table",
    "orderbook_table",
    "summary_table",
    "trade_summary_table",
]
