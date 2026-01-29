"""
终端输出美化模块

使用 rich 库提供美化的终端输出，同时保持向后兼容
"""
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# 全局 Console 实例
console = Console() if RICH_AVAILABLE else None


def print_success(message: str):
    """打印成功消息"""
    if RICH_AVAILABLE:
        console.print(f"[green]✓[/green] {message}")
    else:
        print(f"✓ {message}")


def print_error(message: str):
    """打印错误消息"""
    if RICH_AVAILABLE:
        console.print(f"[red]✗[/red] {message}")
    else:
        print(f"✗ {message}")


def print_warning(message: str):
    """打印警告消息"""
    if RICH_AVAILABLE:
        console.print(f"[yellow]![/yellow] {message}")
    else:
        print(f"! {message}")


def print_info(message: str):
    """打印信息消息"""
    if RICH_AVAILABLE:
        console.print(f"[blue]ℹ[/blue] {message}")
    else:
        print(f"ℹ {message}")


def print_header(title: str, subtitle: str = None):
    """打印标题头"""
    if RICH_AVAILABLE:
        if subtitle:
            console.print(Panel(f"[bold]{title}[/bold]\n{subtitle}", expand=False))
        else:
            console.print(Panel(f"[bold]{title}[/bold]", expand=False))
    else:
        print("=" * 60)
        print(f"  {title}")
        if subtitle:
            print(f"  {subtitle}")
        print("=" * 60)


def print_section(title: str):
    """打印分节标题"""
    if RICH_AVAILABLE:
        console.print(f"\n[bold cyan]━━━ {title} ━━━[/bold cyan]")
    else:
        print(f"\n{'─' * 20} {title} {'─' * 20}")


def create_table(title: str = None, columns: list = None) -> 'Table':
    """创建表格
    
    Args:
        title: 表格标题
        columns: 列定义列表，每项可以是字符串或 (name, style) 元组
    
    Returns:
        Table 对象（rich）或 None（无 rich）
    """
    if not RICH_AVAILABLE:
        return None
    
    table = Table(title=title, show_header=True, header_style="bold")
    if columns:
        for col in columns:
            if isinstance(col, tuple):
                table.add_column(col[0], style=col[1] if len(col) > 1 else None)
            else:
                table.add_column(col)
    return table


def print_table(table):
    """打印表格"""
    if RICH_AVAILABLE and table:
        console.print(table)


def print_key_value(key: str, value, highlight: bool = False):
    """打印键值对"""
    if RICH_AVAILABLE:
        if highlight:
            console.print(f"  [dim]{key}:[/dim] [bold]{value}[/bold]")
        else:
            console.print(f"  [dim]{key}:[/dim] {value}")
    else:
        print(f"  {key}: {value}")


def print_menu(title: str, options: list):
    """打印菜单选项
    
    Args:
        title: 菜单标题
        options: 选项列表，每项为 (key, description) 元组
    """
    if RICH_AVAILABLE:
        console.print(f"\n[bold]{title}[/bold]")
        for key, desc in options:
            console.print(f"  [cyan]{key}[/cyan]. {desc}")
    else:
        print(f"\n{title}")
        for key, desc in options:
            print(f"  {key}. {desc}")


def create_progress():
    """创建进度显示器"""
    if RICH_AVAILABLE:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        )
    return None


# 简化的 print 替代（可直接替换 print）
def cprint(*args, style: str = None, **kwargs):
    """美化的 print 函数
    
    Args:
        *args: 打印内容
        style: rich 样式（如 "bold", "red", "green"）
    """
    if RICH_AVAILABLE and style:
        text = " ".join(str(a) for a in args)
        console.print(f"[{style}]{text}[/{style}]", **kwargs)
    elif RICH_AVAILABLE:
        console.print(*args, **kwargs)
    else:
        print(*args, **kwargs)
