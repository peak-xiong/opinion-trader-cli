"""
工具模块
"""
from opinion_trader.utils.daemon import DaemonProcess
from opinion_trader.utils.confirmation import UserConfirmation, handle_insufficient_balance
from opinion_trader.utils.helpers import translate_error, format_price
from opinion_trader.utils.console import (
    # 核心对象
    console,
    # 消息输出
    success, error, warning, info, dim,
    # 标题布局
    header, section, divider, rule, banner, clear,
    # 键值
    kv, bullet,
    # 交互式菜单 (questionary)
    select, select_multiple, confirm, pause,
    # 输入
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

__all__ = [
    # 旧模块
    "DaemonProcess",
    "UserConfirmation",
    "handle_insufficient_balance",
    "translate_error",
    "format_price",
    # console 核心
    "console",
    # 消息
    "success", "error", "warning", "info", "dim",
    # 布局
    "header", "section", "divider", "rule", "banner", "clear",
    # 键值
    "kv", "bullet",
    # 交互
    "select", "select_multiple", "confirm", "pause",
    # 输入
    "ask", "ask_int", "ask_float", "ask_password",
    # 表格
    "table", "create_table", "print_table",
    # 进度
    "spinner", "progress_bar",
    # 特殊
    "code", "json_print",
    # 打印
    "print", "log",
]
