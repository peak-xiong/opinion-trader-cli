"""
菜单系统封装

提供可复用的菜单类，支持：
- 定义菜单项
- 自动处理选择逻辑
- 支持子菜单
"""
from typing import List, Tuple, Callable, Optional, Dict, Any
from dataclasses import dataclass, field
from opinion_trader.ui.console import (
    console, select, section, success, error, warning, info, header
)


@dataclass
class MenuItem:
    """菜单项"""
    label: str          # 显示文字
    value: str          # 返回值/标识符
    icon: str = ""      # 图标
    handler: Callable = None  # 处理函数
    submenu: 'Menu' = None    # 子菜单
    enabled: bool = True      # 是否启用
    
    def display(self) -> str:
        """获取显示文字"""
        if self.icon:
            return f"{self.icon} {self.label}"
        return self.label


@dataclass  
class Menu:
    """菜单基类"""
    title: str
    items: List[MenuItem] = field(default_factory=list)
    back_text: str = "返回"
    show_header: bool = True
    
    def add_item(
        self,
        label: str,
        value: str,
        icon: str = "",
        handler: Callable = None,
        submenu: 'Menu' = None,
    ):
        """添加菜单项"""
        self.items.append(MenuItem(
            label=label,
            value=value,
            icon=icon,
            handler=handler,
            submenu=submenu,
        ))
    
    def add_separator(self):
        """添加分隔线"""
        self.items.append(MenuItem(label="---", value="---"))
    
    def show(self) -> Optional[str]:
        """显示菜单并返回选择"""
        if self.show_header:
            section(self.title)
        
        choices = []
        for item in self.items:
            if item.value == "---":
                choices.append("---")
            elif item.enabled:
                choices.append((item.display(), item.value))
        
        return select("请选择:", choices, back_option=True, back_text=self.back_text)
    
    def run(self, context: Dict[str, Any] = None) -> Optional[str]:
        """
        运行菜单循环
        
        Args:
            context: 上下文数据，传递给处理函数
        
        Returns:
            最后选择的值
        """
        context = context or {}
        
        while True:
            choice = self.show()
            
            if choice is None:
                return None
            
            # 查找对应的菜单项
            item = next((i for i in self.items if i.value == choice), None)
            
            if item:
                if item.submenu:
                    # 进入子菜单
                    result = item.submenu.run(context)
                    if result == "__back__":
                        continue
                elif item.handler:
                    # 执行处理函数
                    try:
                        result = item.handler(context)
                        if result == "__exit__":
                            return choice
                    except Exception as e:
                        error(f"操作失败: {e}")
                else:
                    # 没有处理函数，直接返回值
                    return choice
        
        return None


class MainMenu(Menu):
    """主菜单"""
    
    def __init__(self, trader=None):
        super().__init__(
            title="主菜单",
            back_text="退出程序"
        )
        self.trader = trader
        self._init_items()
    
    def _init_items(self):
        """初始化菜单项"""
        self.add_item("开始交易", "trade", "📈")
        self.add_item("合并/拆分", "merge", "🔀")
        self.add_item("查询挂单", "orders", "📋")
        self.add_item("撤销挂单", "cancel", "❌")
        self.add_item("查询TOKEN持仓", "position", "💰")
        self.add_item("查询账户资产", "assets", "💳")
        self.add_item("Claim (领取收益)", "claim", "🎁")
    
    def run(self, context: Dict[str, Any] = None) -> Optional[str]:
        """运行主菜单"""
        context = context or {}
        context['trader'] = self.trader
        
        while True:
            choice = self.show()
            
            if choice is None:
                success("程序退出")
                return None
            
            if self.trader:
                self._handle_choice(choice)
    
    def _handle_choice(self, choice: str):
        """处理选择"""
        if not self.trader:
            return
        
        handlers = {
            'trade': self.trader.trading_menu,
            'merge': self.trader.merge_split_menu,
            'orders': self.trader.query_open_orders,
            'cancel': self.trader.cancel_orders_menu,
            'position': self.trader.query_positions,
            'assets': self.trader.query_account_assets,
            'claim': self.trader.claim_menu,
        }
        
        handler = handlers.get(choice)
        if handler:
            try:
                handler()
            except Exception as e:
                error(f"操作失败: {e}")


class TradingMenu(Menu):
    """交易模式菜单"""
    
    def __init__(self):
        super().__init__(
            title="交易模式",
            back_text="返回主菜单"
        )
        self._init_items()
    
    def _init_items(self):
        """初始化菜单项"""
        # 基础模式
        self.add_item("仅买入", "buy_only", "🟢")
        self.add_item("仅卖出", "sell_only", "🔴")
        self.add_item("先买后卖", "buy_then_sell", "🔄")
        self.add_item("先卖后买", "sell_then_buy", "↩️")
        self.add_item("自定义策略", "custom", "⚙️")
        
        self.add_separator()
        
        # 高级模式
        self.add_item("快速模式（买卖交替）", "quick_mode", "⚡")
        self.add_item("低损耗模式（先买后挂单）", "low_loss_mode", "📉")
        self.add_item("挂单模式（自定义价格）", "limit_order_mode", "📊")
        self.add_item("做市商模式（双边挂单）", "market_maker_mode", "🏦")
        self.add_item("增强买卖（金额/仓位）", "enhanced_mode", "💹")


class MergeSplitMenu(Menu):
    """合并/拆分菜单"""
    
    def __init__(self):
        super().__init__(
            title="合并/拆分",
            back_text="返回主菜单"
        )
        self._init_items()
    
    def _init_items(self):
        """初始化菜单项"""
        self.add_item("拆分 (USDT → YES + NO)", "split", "🔀")
        self.add_item("合并 (YES + NO → USDT)", "merge", "🔄")


class CancelOrdersMenu(Menu):
    """撤单菜单"""
    
    def __init__(self):
        super().__init__(
            title="撤销挂单",
            back_text="返回主菜单"
        )
        self._init_items()
    
    def _init_items(self):
        """初始化菜单项"""
        self.add_item("撤销所有挂单", "all", "🗑️")
        self.add_item("撤销指定市场的挂单", "market", "📍")
        self.add_item("撤销指定订单ID", "order", "🔢")


class QueryPositionMenu(Menu):
    """查询持仓菜单"""
    
    def __init__(self):
        super().__init__(
            title="查询TOKEN持仓",
            back_text="返回主菜单"
        )
        self._init_items()
    
    def _init_items(self):
        """初始化菜单项"""
        self.add_item("查询所有持仓", "all", "📊")
        self.add_item("查询指定市场持仓", "market", "📍")


class ClaimMenu(Menu):
    """Claim菜单"""
    
    def __init__(self):
        super().__init__(
            title="Claim - 领取收益",
            back_text="返回主菜单"
        )
        self._init_items()
    
    def _init_items(self):
        """初始化菜单项"""
        self.add_item("自动扫描并Claim所有可领取的市场", "auto", "🔍")
        self.add_item("指定市场ID进行Claim", "manual", "📍")


# ============ 菜单工厂 ============

def create_menu(
    title: str,
    options: List[Tuple[str, str, str]],
    back_text: str = "返回",
) -> Menu:
    """
    快速创建菜单
    
    Args:
        title: 标题
        options: 选项列表 [(图标, 文字, 值), ...]
        back_text: 返回按钮文字
    
    Returns:
        Menu 对象
    """
    menu = Menu(title=title, back_text=back_text)
    for item in options:
        if item == "---":
            menu.add_separator()
        elif len(item) == 3:
            menu.add_item(item[1], item[2], item[0])
        elif len(item) == 2:
            menu.add_item(item[0], item[1])
    return menu
