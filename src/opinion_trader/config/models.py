"""
Opinion SDK 数据模型定义
包含所有配置类和状态类
"""
from dataclasses import dataclass, field
from typing import List, Optional


class TraderConfig:
    """交易配置"""
    remark: str  # 备注
    api_key: str
    eoa_address: str  # EOA地址 - Opinion.trade上的注册地址，用于查询余额
    private_key: str
    proxy_address: str = None  # 代理地址 - 用于交易，可自动从API获取

    def __init__(self, remark: str, api_key: str, eoa_address: str, private_key: str,
                 proxy_address: str = None, socks5: str = None):
        self.remark = remark
        self.api_key = api_key
        self.eoa_address = eoa_address
        self.private_key = private_key
        self.proxy_address = proxy_address
        # socks5 参数保留但不使用，保持向后兼容

    def get_proxies(self, proxy_type='socks5'):
        """获取当前账户的代理配置（已弃用，始终返回None）"""
        return None


@dataclass
class MarketMakerConfig:
    """做市商策略配置"""
    # 基础参数
    market_id: int = 0
    token_id: str = ""
    market_title: str = ""  # 市场标题，用于显示

    # 价格参数
    min_spread: float = 0.1  # 最小价差阈值（分），价差小于此值暂停跟随
    price_step: float = 0.1  # 价格调整步长（分）

    # ============ 价格边界保护（防止被带节奏）============
    # 绝对价格边界 - 硬性限制，绝不突破
    max_buy_price: float = 0  # 买入价格上限（分），0表示不限制
    min_sell_price: float = 0  # 卖出价格下限（分），0表示不限制

    # 相对偏离保护 - 基于启动时的参考价
    max_price_deviation: float = 0  # 最大价格偏离度（分），相对于启动时的中间价，0表示不限制
    # 例如：启动时中间价50分，偏离度设为5，则买价不超过55，卖价不低于45

    # ============ 盘口深度验证（防止薄盘操控）============
    min_orderbook_depth: float = 0  # 最小盘口深度（美元），买卖盘各自需达到此深度才交易
    # 建议根据市场交易量设置，如日交易量的1%-5%

    # 深度不足时的行为
    pause_on_low_depth: bool = True  # True=深度不足时暂停挂单，False=继续但减小金额

    # 单笔交易参数
    order_amount_min: float = 5.0  # 单笔最小金额（美元）
    order_amount_max: float = 20.0  # 单笔最大金额（美元）

    # ============ 仓位限制（必须设置至少一项）============
    max_position_shares: int = 0  # 最大持仓份额，0表示不限制
    max_position_amount: float = 0  # 最大持仓金额（美元），0表示不限制
    max_position_percent: float = 0  # 最大持仓占净资产百分比，0表示不限制

    # 止损参数（三选一触发）
    stop_loss_percent: float = 0  # 亏损百分比止损，如5表示亏损5%止损，0表示不启用
    stop_loss_amount: float = 0  # 亏损金额止损（美元），0表示不启用
    stop_loss_price: float = 0  # 价格止损（分），跌破此价格止损，0表示不启用

    # 运行控制
    check_interval: float = 2.0  # 盘口检查间隔（秒）

    # 深度检测参数（止损时用）
    min_depth_levels: int = 5  # 止损时要求的最小买盘深度档数
    min_depth_amount: float = 100  # 止损时要求的最小买盘金额

    # ============ 盘口异常撤单保护 ============
    # 检测到大量撤单时跟着撤，防止被砸盘
    depth_drop_threshold: float = 50  # 深度骤降阈值（百分比），如50表示深度下降50%时触发
    depth_drop_window: int = 3  # 检测窗口（检查次数），在此窗口内深度骤降则触发
    auto_cancel_on_depth_drop: bool = True  # 检测到深度骤降时是否自动撤单

    # 紧急撤单时持仓处理方式
    # 'hold' = 只撤单不卖出，保留全部持仓
    # 'sell_all' = 撤单后市价卖出全部持仓
    # 'sell_partial' = 撤单后卖出部分持仓，保留一定比例
    emergency_position_action: str = 'hold'
    emergency_sell_percent: float = 0  # 卖出比例（百分比），仅当 action='sell_partial' 时有效

    # ============ 分层挂单配置（卖出时使用）============
    # 启用分层卖出挂单，买入成交后按多档价格分层挂出
    layered_sell_enabled: bool = False  # 是否启用分层卖出

    # 价格层级列表，如 [1, 5, 10] 表示在卖1、卖5、卖10挂单
    sell_price_levels: list = None  # 默认 [1]，即只在卖1挂单

    # 分布模式
    # 'uniform' = 垂直分布（每层相等）
    # 'pyramid' = 金字塔（靠近盘口较小，远离盘口较大）
    # 'inverse_pyramid' = 倒金字塔（靠近盘口较大，远离盘口较小）
    # 'custom' = 自定义比例
    sell_distribution_mode: str = 'uniform'

    # 自定义比例（仅当 sell_distribution_mode='custom' 时使用）
    sell_custom_ratios: list = None

    # ============ 分层挂单配置（买入时使用）============
    # 启用分层买入挂单
    layered_buy_enabled: bool = False  # 是否启用分层买入

    # 价格层级列表，如 [1, 5, 10] 表示在买1、买5、买10挂单
    buy_price_levels: list = None  # 默认 [1]，即只在买1挂单

    # 分布模式
    buy_distribution_mode: str = 'uniform'

    # 自定义比例
    buy_custom_ratios: list = None

    # ============ 成本加成卖出配置 ============
    # 启用后：卖出价 = 平均买入成本 + 利润价差（而非跟随市场卖1价）
    cost_based_sell_enabled: bool = False  # 是否启用成本加成定价
    sell_profit_spread: float = 1.0  # 卖出利润价差（分），卖出价 = 平均成本 + 此值
    min_cost_profit_spread: float = 0.5  # 最小利润价差（分），低于此值不挂卖

    # ============ 网格策略配置 ============
    # 网格模式：追踪每笔买入成本，按成本+利润价差挂卖
    grid_enabled: bool = False  # 是否启用网格模式
    grid_profit_spread: float = 1.0  # 目标利润价差（分），卖出价 = 买入价 + 此值
    grid_min_profit_spread: float = 0.5  # 最小利润价差（分），低于此值不挂卖
    grid_levels: int = 5  # 网格层数（同时挂多少档买单）
    grid_level_spread: float = 1.0  # 每层价格间隔（分）
    grid_amount_per_level: float = 10.0  # 每层挂单金额（美元）
    grid_auto_rebalance: bool = True  # 是否自动再平衡（卖出后重新挂买）

    # ============ WebSocket 模式 ============
    use_websocket: bool = False  # 是否使用 WebSocket 实时数据（替代轮询）


@dataclass
class MarketMakerState:
    """做市商运行状态（每个账户独立）"""
    is_running: bool = False

    # 参考价（启动时记录，用于偏离度保护）
    reference_mid_price: float = 0  # 启动时的中间价
    reference_bid1: float = 0  # 启动时的买1
    reference_ask1: float = 0  # 启动时的卖1

    # 双边挂单
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    buy_order_price: float = 0
    sell_order_price: float = 0

    # 交易统计
    total_buy_shares: int = 0  # 累计买入份额
    total_buy_cost: float = 0  # 累计买入成本
    total_sell_shares: int = 0  # 累计卖出份额
    total_sell_revenue: float = 0  # 累计卖出收入
    realized_pnl: float = 0  # 已实现盈亏

    # ============ 增强版盈亏统计 ============
    # 交易次数统计
    buy_trade_count: int = 0  # 买入成交笔数
    sell_trade_count: int = 0  # 卖出成交笔数

    # 时间统计
    start_time: float = 0  # 做市开始时间戳
    end_time: float = 0  # 做市结束时间戳

    # 盈亏跟踪
    peak_pnl: float = 0  # 历史最高盈亏（用于计算回撤）
    max_drawdown: float = 0  # 最大回撤金额
    max_drawdown_percent: float = 0  # 最大回撤百分比

    # 价差收益统计
    spread_profit: float = 0  # 做市价差收益（买卖配对产生的收益）
    matched_shares: int = 0  # 已配对的份额（min(买入, 卖出)）

    # 手续费统计
    total_fees: float = 0  # 累计手续费支出

    # 单笔交易记录（用于详细分析）
    trade_history: Optional[list] = None  # 交易历史 [{'time', 'side', 'shares', 'price', 'amount'}, ...]

    # 价格统计
    min_buy_price: float = float('inf')  # 最低买入价
    max_buy_price: float = 0  # 最高买入价
    min_sell_price: float = float('inf')  # 最低卖出价
    max_sell_price: float = 0  # 最高卖出价

    # 状态标记
    stop_loss_triggered: bool = False
    position_limit_reached: bool = False
    depth_insufficient: bool = False  # 深度不足标记
    price_boundary_hit: bool = False  # 价格边界触发标记
    depth_drop_triggered: bool = False  # 深度骤降触发标记

    # 深度历史记录（用于检测骤降）
    bid_depth_history: Optional[list] = None  # 买盘深度历史
    ask_depth_history: Optional[list] = None  # 卖盘深度历史

    # ============ 网格策略状态 ============
    # 网格持仓追踪：记录每笔买入的价格和份额，用于计算对应卖出价
    # 格式: [{'buy_price': float, 'shares': int, 'buy_time': float, 'sell_order_id': str, 'sell_price': float}, ...]
    grid_positions: Optional[list] = None
    # 网格买单追踪：当前挂出的买单
    # 格式: [{'order_id': str, 'price': float, 'amount': float, 'level': int}, ...]
    grid_buy_orders: Optional[list] = None
    # 网格卖单追踪：当前挂出的卖单
    # 格式: [{'order_id': str, 'price': float, 'shares': int, 'buy_price': float}, ...]
    grid_sell_orders: Optional[list] = None

    def __post_init__(self):
        """初始化列表字段"""
        if self.trade_history is None:
            self.trade_history = []
        if self.bid_depth_history is None:
            self.bid_depth_history = []
        if self.ask_depth_history is None:
            self.ask_depth_history = []
        if self.grid_positions is None:
            self.grid_positions = []
        if self.grid_buy_orders is None:
            self.grid_buy_orders = []
        if self.grid_sell_orders is None:
            self.grid_sell_orders = []
