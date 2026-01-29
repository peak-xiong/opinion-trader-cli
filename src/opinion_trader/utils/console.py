"""
终端输出美化模块 - 基于 rich + questionary
提供统一的 UI 交互接口
"""
import questionary
from questionary import Style, Choice, Separator
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text
from rich import print as rprint

# 全局 Console 实例
console = Console()

# questionary 自定义样式
Q_STYLE = Style([
    ('qmark', 'fg:#673ab7 bold'),
    ('question', 'bold'),
    ('answer', 'fg:#61afef bold'),
    ('pointer', 'fg:#673ab7 bold'),
    ('highlighted', 'fg:#673ab7 bold'),
    ('selected', 'fg:#61afef'),
    ('separator', 'fg:#6c6c6c'),
    ('instruction', 'fg:#6c6c6c'),
    ('text', ''),
    ('disabled', 'fg:#6c6c6c italic'),
])


# ============ 消息输出 ============

def success(message: str):
    """成功消息"""
    console.print(f"[green]✓[/green] {message}")


def error(message: str):
    """错误消息"""
    console.print(f"[red]✗[/red] {message}")


def warning(message: str):
    """警告消息"""
    console.print(f"[yellow]![/yellow] {message}")


def info(message: str):
    """信息消息"""
    console.print(f"[blue]ℹ[/blue] {message}")


def dim(message: str):
    """灰色消息"""
    console.print(f"[dim]{message}[/dim]")


# ============ 标题和分节 ============

def header(title: str, subtitle: str = None):
    """打印标题面板"""
    content = f"[bold cyan]{title}[/bold cyan]"
    if subtitle:
        console.print(Panel.fit(content, subtitle=subtitle, border_style="blue"))
    else:
        console.print(Panel.fit(content, border_style="blue"))


def section(title: str):
    """打印分节标题"""
    console.print(f"\n[bold cyan]━━━ {title} ━━━[/bold cyan]")


def divider(char: str = "─", style: str = "dim", width: int = 60):
    """打印分隔线"""
    console.print(f"[{style}]{char * width}[/{style}]")


def rule(title: str = "", style: str = "dim"):
    """打印带标题的分隔线"""
    console.rule(title, style=style)


# ============ 键值对和列表 ============

def kv(key: str, value, highlight: bool = False):
    """打印键值对"""
    if highlight:
        console.print(f"  [dim]{key}:[/dim] [bold yellow]{value}[/bold yellow]")
    else:
        console.print(f"  [dim]{key}:[/dim] {value}")


def bullet(message: str, indent: int = 2):
    """打印列表项"""
    console.print(f"{' ' * indent}[dim]•[/dim] {message}")


# ============ 菜单选择 (questionary) ============

def select(prompt: str, choices: list, back_option: bool = True, back_text: str = "返回") -> str:
    """
    交互式单选菜单
    
    Args:
        prompt: 提示文字
        choices: 选项列表，支持以下格式：
            - 简单字符串列表: ["选项1", "选项2"]
            - 元组列表: [("显示文字", "返回值"), ...]
            - dict列表: [{"name": "显示", "value": "值"}, ...]
        back_option: 是否添加返回选项
        back_text: 返回选项的文字
    
    Returns:
        选中的值，取消返回 None
    """
    q_choices = []
    
    for item in choices:
        if isinstance(item, str):
            q_choices.append(Choice(item, value=item))
        elif isinstance(item, tuple):
            q_choices.append(Choice(item[0], value=item[1]))
        elif isinstance(item, dict):
            q_choices.append(Choice(item.get("name", ""), value=item.get("value", "")))
        elif item == "---" or item is None:
            q_choices.append(Separator("─" * 35))
    
    if back_option:
        q_choices.append(Separator("─" * 35))
        q_choices.append(Choice(f"↩️  {back_text}", value=None))
    
    return questionary.select(
        prompt,
        choices=q_choices,
        style=Q_STYLE,
        use_shortcuts=False,
        use_arrow_keys=True,
    ).ask()


def select_multiple(prompt: str, choices: list, min_count: int = 0) -> list:
    """
    交互式多选菜单
    
    Args:
        prompt: 提示文字
        choices: 选项列表
        min_count: 最少选择数量
    
    Returns:
        选中的值列表
    """
    q_choices = []
    for item in choices:
        if isinstance(item, str):
            q_choices.append(Choice(item, value=item))
        elif isinstance(item, tuple):
            q_choices.append(Choice(item[0], value=item[1]))
        elif isinstance(item, dict):
            q_choices.append(Choice(
                item.get("name", ""),
                value=item.get("value", ""),
                checked=item.get("checked", False)
            ))
    
    result = questionary.checkbox(
        prompt,
        choices=q_choices,
        style=Q_STYLE,
        validate=lambda x: len(x) >= min_count or f"请至少选择 {min_count} 项",
    ).ask()
    
    return result if result else []


def confirm(prompt: str, default: bool = False) -> bool:
    """确认对话框"""
    result = questionary.confirm(
        prompt,
        default=default,
        style=Q_STYLE,
    ).ask()
    return result if result is not None else False


def ask(prompt: str, default: str = "") -> str:
    """文本输入"""
    result = questionary.text(
        prompt,
        default=default,
        style=Q_STYLE,
    ).ask()
    return result if result is not None else ""


def ask_int(prompt: str, default: int = None, min_val: int = None, max_val: int = None) -> int:
    """整数输入"""
    def validate(val):
        if not val and default is not None:
            return True
        try:
            n = int(val)
            if min_val is not None and n < min_val:
                return f"不能小于 {min_val}"
            if max_val is not None and n > max_val:
                return f"不能大于 {max_val}"
            return True
        except ValueError:
            return "请输入有效的整数"
    
    result = questionary.text(
        prompt,
        default=str(default) if default is not None else "",
        validate=validate,
        style=Q_STYLE,
    ).ask()
    
    if result is None:
        return default if default is not None else 0
    return int(result) if result else (default if default is not None else 0)


def ask_float(prompt: str, default: float = None, min_val: float = None, max_val: float = None) -> float:
    """浮点数输入"""
    def validate(val):
        if not val and default is not None:
            return True
        try:
            n = float(val)
            if min_val is not None and n < min_val:
                return f"不能小于 {min_val}"
            if max_val is not None and n > max_val:
                return f"不能大于 {max_val}"
            return True
        except ValueError:
            return "请输入有效的数字"
    
    result = questionary.text(
        prompt,
        default=str(default) if default is not None else "",
        validate=validate,
        style=Q_STYLE,
    ).ask()
    
    if result is None:
        return default if default is not None else 0.0
    return float(result) if result else (default if default is not None else 0.0)


def ask_password(prompt: str) -> str:
    """密码输入（隐藏输入）"""
    result = questionary.password(
        prompt,
        style=Q_STYLE,
    ).ask()
    return result if result else ""


def pause(message: str = "按任意键继续..."):
    """暂停等待用户按键"""
    questionary.press_any_key_to_continue(message).ask()


# ============ 表格 ============

def table(title: str = None, columns: list = None, rows: list = None, 
          show_header: bool = True, box_style = None):
    """
    创建并打印表格
    
    Args:
        title: 标题
        columns: 列定义，支持：
            - 简单字符串列表: ["列1", "列2"]
            - 元组列表: [("列名", "样式", "对齐"), ...]
        rows: 行数据列表
        show_header: 是否显示表头
        box_style: 边框样式
    """
    from rich.box import ROUNDED, SIMPLE, MINIMAL
    
    t = Table(
        title=title, 
        show_header=show_header, 
        header_style="bold magenta",
        box=box_style or ROUNDED,
    )
    
    if columns:
        for col in columns:
            if isinstance(col, tuple):
                t.add_column(
                    col[0], 
                    style=col[1] if len(col) > 1 else None,
                    justify=col[2] if len(col) > 2 else "left"
                )
            else:
                t.add_column(str(col))
    
    if rows:
        for row in rows:
            t.add_row(*[str(cell) for cell in row])
    
    console.print(t)


def create_table(title: str = None, columns: list = None) -> Table:
    """创建表格对象（用于动态添加行）"""
    from rich.box import ROUNDED
    
    t = Table(title=title, show_header=bool(columns), header_style="bold magenta", box=ROUNDED)
    if columns:
        for col in columns:
            if isinstance(col, tuple):
                t.add_column(col[0], style=col[1] if len(col) > 1 else None,
                            justify=col[2] if len(col) > 2 else "left")
            else:
                t.add_column(str(col))
    return t


def print_table(t: Table):
    """打印表格"""
    console.print(t)


# ============ 进度显示 ============

def spinner(message: str):
    """创建加载动画上下文"""
    return console.status(f"[bold blue]{message}[/bold blue]", spinner="dots")


def progress_bar():
    """创建进度条"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


# ============ 特殊输出 ============

def banner(text: str, subtitle: str = None, style: str = "blue"):
    """打印横幅"""
    console.print(Panel.fit(
        f"[bold cyan]{text}[/bold cyan]",
        subtitle=subtitle,
        border_style=style
    ))


def code(text: str, language: str = "python"):
    """打印代码块"""
    from rich.syntax import Syntax
    syntax = Syntax(text, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def json_print(data):
    """美化打印 JSON"""
    from rich.json import JSON
    console.print(JSON.from_data(data))


def clear():
    """清屏"""
    console.clear()


# ============ 快捷导出 ============

# 直接使用 console.print 的别名
print = console.print
log = console.log
