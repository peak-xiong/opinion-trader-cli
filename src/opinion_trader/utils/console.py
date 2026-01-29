"""
终端输出美化模块 - 基于 rich
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm, IntPrompt, FloatPrompt
from rich.text import Text
from rich.style import Style
from rich import print as rprint

# 全局 Console 实例
console = Console()


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
    """打印标题"""
    content = f"[bold white]{title}[/bold white]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(content, border_style="blue", expand=False))


def section(title: str):
    """打印分节标题"""
    console.print(f"\n[bold cyan]{'━' * 3} {title} {'━' * 40}[/bold cyan]")


def divider(char: str = "─", style: str = "dim"):
    """打印分隔线"""
    console.print(f"[{style}]{char * 60}[/{style}]")


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


# ============ 菜单 ============

def menu(title: str, options: list):
    """打印菜单
    
    Args:
        title: 菜单标题
        options: [(key, description), ...]
    """
    console.print(f"\n[bold]{title}[/bold]")
    for key, desc in options:
        console.print(f"  [cyan]{key}[/cyan]. {desc}")


def menu_table(title: str, options: list, columns: int = 2):
    """打印表格形式的菜单"""
    table = Table(title=title, show_header=False, box=None, padding=(0, 2))
    for _ in range(columns):
        table.add_column()
    
    rows = []
    for i, (key, desc) in enumerate(options):
        rows.append(f"[cyan]{key}[/cyan]. {desc}")
        if len(rows) == columns:
            table.add_row(*rows)
            rows = []
    if rows:
        rows.extend([""] * (columns - len(rows)))
        table.add_row(*rows)
    
    console.print(table)


# ============ 表格 ============

def table(title: str = None, columns: list = None, rows: list = None):
    """创建并打印表格
    
    Args:
        title: 标题
        columns: 列名列表
        rows: 行数据列表
    """
    t = Table(title=title, show_header=bool(columns), header_style="bold")
    if columns:
        for col in columns:
            t.add_column(str(col))
    if rows:
        for row in rows:
            t.add_row(*[str(cell) for cell in row])
    console.print(t)
    return t


def create_table(title: str = None, columns: list = None) -> Table:
    """创建表格对象"""
    t = Table(title=title, show_header=bool(columns), header_style="bold")
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


# ============ 输入 ============

def ask(prompt: str, default: str = None) -> str:
    """文本输入"""
    return Prompt.ask(prompt, default=default, console=console)


def ask_int(prompt: str, default: int = None) -> int:
    """整数输入"""
    return IntPrompt.ask(prompt, default=default, console=console)


def ask_float(prompt: str, default: float = None) -> float:
    """浮点数输入"""
    return FloatPrompt.ask(prompt, default=default, console=console)


def confirm(prompt: str, default: bool = False) -> bool:
    """确认输入"""
    return Confirm.ask(prompt, default=default, console=console)


def choose(prompt: str, choices: list, default: str = None) -> str:
    """选择输入"""
    return Prompt.ask(prompt, choices=choices, default=default, console=console)


# ============ 进度 ============

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

def banner(text: str, style: str = "bold white on blue"):
    """打印横幅"""
    console.print(Panel(text, style=style, expand=True))


def code(text: str, language: str = "python"):
    """打印代码块"""
    from rich.syntax import Syntax
    syntax = Syntax(text, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def json_print(data):
    """美化打印 JSON"""
    from rich.json import JSON
    console.print(JSON.from_data(data))


def rule(title: str = "", style: str = "dim"):
    """打印带标题的分隔线"""
    console.rule(title, style=style)


# ============ 快捷函数 ============

# 直接使用 console.print 的别名
print = console.print
log = console.log
