"""
交互式输入封装

提供常用的用户输入交互，包括：
- 账户选择（单选/多选）
- 市场选择
- 金额/价格/份额输入
- 确认对话框
"""
from typing import List, Optional, Tuple, Any, Callable
from opinion_trader.ui.console import (
    console, select, select_multiple, confirm, 
    ask, ask_int, ask_float, 
    success, error, warning, info, section, divider, kv
)


# ============ 账户选择 ============

def select_accounts(
    configs: list,
    title: str = "选择账户",
    allow_all: bool = True,
    min_count: int = 1,
) -> List[int]:
    """
    选择账户（支持多选）
    
    Args:
        configs: 账户配置列表，每个配置需要有 remark 属性
        title: 标题
        allow_all: 是否允许选择全部
        min_count: 最少选择数量
    
    Returns:
        选中的账户索引列表 (0-based)
    """
    if not configs:
        error("没有可用的账户")
        return []
    
    section(title)
    
    # 构建选项
    choices = []
    if allow_all:
        choices.append({"name": "📋 全部账户", "value": "all", "checked": True})
    
    for idx, config in enumerate(configs):
        remark = getattr(config, 'remark', f'账户{idx+1}')
        choices.append({
            "name": f"👤 {remark}",
            "value": idx,
            "checked": not allow_all  # 如果不允许全选，默认选中所有
        })
    
    if allow_all:
        # 单选模式：选择"全部"或具体账户
        result = select("请选择:", [
            ("📋 全部账户", "all"),
            *[(f"👤 {getattr(c, 'remark', f'账户{i+1}')}", i) for i, c in enumerate(configs)]
        ], back_option=True, back_text="返回")
        
        if result is None:
            return []
        elif result == "all":
            return list(range(len(configs)))
        else:
            return [result]
    else:
        # 多选模式
        selected = select_multiple("请选择账户:", choices, min_count=min_count)
        if not selected:
            return []
        return [s for s in selected if isinstance(s, int)]


def select_single_account(configs: list, title: str = "选择账户") -> Optional[int]:
    """
    选择单个账户
    
    Args:
        configs: 账户配置列表
        title: 标题
    
    Returns:
        选中的账户索引 (0-based)，取消返回 None
    """
    if not configs:
        error("没有可用的账户")
        return None
    
    section(title)
    
    choices = [(f"👤 {getattr(c, 'remark', f'账户{i+1}')}", i) for i, c in enumerate(configs)]
    
    return select("请选择账户:", choices, back_option=True)


# ============ 市场选择 ============

def input_market_id(prompt: str = "请输入市场ID") -> Optional[int]:
    """
    输入市场ID
    
    Returns:
        市场ID，取消或无效返回 None
    """
    market_id_str = ask(prompt)
    if not market_id_str:
        return None
    
    try:
        market_id = int(market_id_str)
        if market_id <= 0:
            error("市场ID必须大于0")
            return None
        return market_id
    except ValueError:
        error("请输入有效的数字")
        return None


def select_market(
    markets: list,
    title: str = "选择市场",
    show_details: bool = True,
) -> Optional[Any]:
    """
    从市场列表中选择
    
    Args:
        markets: 市场列表，每个市场需要有 market_id 和 market_title 属性
        title: 标题
        show_details: 是否显示详细信息
    
    Returns:
        选中的市场对象，取消返回 None
    """
    if not markets:
        info("没有可用的市场")
        return None
    
    section(title)
    
    choices = []
    for m in markets:
        market_id = getattr(m, 'market_id', '?')
        market_title = getattr(m, 'market_title', '未知市场')
        # 截断过长的标题
        if len(market_title) > 40:
            market_title = market_title[:37] + "..."
        choices.append((f"[{market_id}] {market_title}", m))
    
    return select("请选择:", choices, back_option=True)


def select_child_market(
    parent_title: str,
    child_markets: list,
) -> Optional[Any]:
    """
    选择子市场（分类市场）
    
    Args:
        parent_title: 父市场标题
        child_markets: 子市场列表
    
    Returns:
        选中的子市场对象，取消返回 None
    """
    if not child_markets:
        return None
    
    info(f"分类市场: {parent_title}")
    console.print(f"  找到 {len(child_markets)} 个子市场")
    
    choices = []
    for child in child_markets:
        child_id = getattr(child, 'market_id', '?')
        child_title = getattr(child, 'market_title', '未知')
        if len(child_title) > 35:
            child_title = child_title[:32] + "..."
        choices.append((f"[{child_id}] {child_title}", child))
    
    return select("请选择子市场:", choices, back_option=True)


# ============ 金额/价格/份额输入 ============

def input_amount(
    prompt: str = "请输入金额",
    min_val: float = 0,
    max_val: float = None,
    default: float = None,
    unit: str = "$",
) -> Optional[float]:
    """
    输入金额
    
    Args:
        prompt: 提示文字
        min_val: 最小值
        max_val: 最大值
        default: 默认值
        unit: 单位
    
    Returns:
        金额，取消返回 None
    """
    hint = f" ({unit})"
    if max_val:
        hint = f" (最大: {unit}{max_val:.2f})"
    
    result = ask_float(f"{prompt}{hint}", default=default, min_val=min_val, max_val=max_val)
    
    if result is None or result == 0:
        return None
    return result


def input_price(
    prompt: str = "请输入价格",
    min_val: float = 0,
    max_val: float = 100,
    default: float = None,
    unit: str = "¢",
) -> Optional[float]:
    """
    输入价格（分）
    
    Args:
        prompt: 提示文字
        min_val: 最小值
        max_val: 最大值
        default: 默认值
        unit: 单位
    
    Returns:
        价格，取消返回 None
    """
    result = ask_float(f"{prompt} ({unit})", default=default, min_val=min_val, max_val=max_val)
    
    if result is None or result == 0:
        return None
    return result


def input_shares(
    prompt: str = "请输入份额",
    min_val: int = 1,
    max_val: int = None,
    default: int = None,
) -> Optional[int]:
    """
    输入份额
    
    Args:
        prompt: 提示文字
        min_val: 最小值
        max_val: 最大值
        default: 默认值
    
    Returns:
        份额，取消返回 None
    """
    hint = ""
    if max_val:
        hint = f" (最大: {max_val})"
    
    result = ask_int(f"{prompt}{hint}", default=default, min_val=min_val, max_val=max_val)
    
    if result is None or result == 0:
        return None
    return result


# ============ 确认对话框 ============

def confirm_action(
    action: str,
    details: dict = None,
    danger: bool = False,
) -> bool:
    """
    确认操作
    
    Args:
        action: 操作描述
        details: 详细信息字典
        danger: 是否为危险操作
    
    Returns:
        True 确认，False 取消
    """
    if danger:
        warning(f"即将执行: {action}")
    else:
        info(f"即将执行: {action}")
    
    if details:
        for key, value in details.items():
            kv(key, value)
    
    console.print()
    return confirm("确认执行?", default=not danger)


def confirm_dangerous(
    action: str,
    confirm_word: str = "yes",
) -> bool:
    """
    危险操作确认（需要输入特定词）
    
    Args:
        action: 操作描述
        confirm_word: 需要输入的确认词
    
    Returns:
        True 确认，False 取消
    """
    warning(f"危险操作: {action}")
    console.print(f"  [red]请输入 '{confirm_word}' 确认[/red]")
    
    user_input = ask("确认")
    return user_input.lower() == confirm_word.lower()


# ============ 通用选择 ============

def select_option(
    title: str,
    options: List[Tuple[str, Any]],
    back_text: str = "返回",
) -> Optional[Any]:
    """
    通用选项选择
    
    Args:
        title: 标题
        options: 选项列表 [(显示文字, 值), ...]
        back_text: 返回按钮文字
    
    Returns:
        选中的值，取消返回 None
    """
    section(title)
    return select("请选择:", options, back_option=True, back_text=back_text)


def select_with_preview(
    title: str,
    options: list,
    preview_fn: Callable[[Any], str],
) -> Optional[Any]:
    """
    带预览的选择
    
    Args:
        title: 标题
        options: 选项列表
        preview_fn: 预览函数，接收选项返回预览字符串
    
    Returns:
        选中的值
    """
    section(title)
    
    choices = []
    for opt in options:
        preview = preview_fn(opt)
        choices.append((preview, opt))
    
    return select("请选择:", choices, back_option=True)
