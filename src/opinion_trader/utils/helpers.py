"""
辅助函数模块
"""
import re


def translate_error(errmsg: str) -> str:
    """翻译常见错误信息"""
    if not errmsg:
        return "未知错误"

    # 最低金额错误
    min_value_match = re.search(
        r'Order value ([\d.]+) USDT is below the minimum required value of ([\d.]+) USDT', errmsg)
    if min_value_match:
        actual = min_value_match.group(1)
        required = min_value_match.group(2)
        return f"金额${actual}低于最低要求${required}"

    # 余额不足
    if 'insufficient' in errmsg.lower() or 'balance' in errmsg.lower():
        return "余额不足"

    # 地区限制
    if 'region' in errmsg.lower() or 'country' in errmsg.lower() or 'restricted' in errmsg.lower():
        return "地区限制"

    # 订单不存在
    if 'order not found' in errmsg.lower():
        return "订单不存在"

    # 市场已关闭
    if 'market' in errmsg.lower() and ('closed' in errmsg.lower() or 'resolved' in errmsg.lower()):
        return "市场已关闭"

    # 价格超出范围
    if 'price' in errmsg.lower() and ('invalid' in errmsg.lower() or 'range' in errmsg.lower()):
        return "价格无效"

    # 数量错误
    if 'quantity' in errmsg.lower() or 'shares' in errmsg.lower():
        if 'minimum' in errmsg.lower():
            return "数量低于最小要求"
        elif 'maximum' in errmsg.lower():
            return "数量超过最大限制"

    # 网络错误
    if 'timeout' in errmsg.lower() or 'connection' in errmsg.lower():
        return "网络超时"

    # 如果没有匹配，返回原始消息（但截断过长的消息）
    if len(errmsg) > 50:
        return errmsg[:47] + "..."
    return errmsg


def format_price(price: float) -> str:
    """格式化价格显示（*100并去掉小数点后多余的0）"""
    # 先四舍五入到0.1分精度，避免浮点数精度问题
    price_cent = round(price * 100, 1)
    if price_cent == int(price_cent):
        return f"{int(price_cent)}"
    else:
        return f"{price_cent:.1f}"


def format_amount(amount: float, currency: str = "$") -> str:
    """格式化金额显示"""
    if amount >= 1000000:
        return f"{currency}{amount/1000000:.2f}M"
    elif amount >= 1000:
        return f"{currency}{amount/1000:.2f}K"
    else:
        return f"{currency}{amount:.2f}"


def truncate_string(s: str, max_length: int = 20, suffix: str = "...") -> str:
    """截断字符串"""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def mask_address(address: str, prefix_len: int = 6, suffix_len: int = 4) -> str:
    """隐藏地址中间部分"""
    if len(address) <= prefix_len + suffix_len:
        return address
    return f"{address[:prefix_len]}...{address[-suffix_len:]}"


def mask_private_key(key: str) -> str:
    """隐藏私钥（只显示前6位和后4位）"""
    return mask_address(key, prefix_len=6, suffix_len=4)
