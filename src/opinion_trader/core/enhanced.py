"""
交易增强模块
包含：合并/拆分、下单方式增强、交易汇总统计
"""
import time
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# ============ 交易汇总统计 ============

@dataclass
class TradeRecord:
    """单笔交易记录"""
    timestamp: float  # 时间戳
    side: str  # 'buy' 或 'sell'
    price: float  # 成交价格
    shares: int  # 成交数量
    amount: float  # 成交金额（美元）
    account_remark: str = ""  # 账户备注
    order_id: str = ""  # 订单ID


@dataclass
class TradeSummary:
    """交易汇总统计"""
    trades: List[TradeRecord] = field(default_factory=list)

    # 统计字段
    total_amount: float = 0  # 总成交金额
    total_trades: int = 0  # 总成交笔数
    avg_price: float = 0  # 平均成交价
    max_price: float = 0  # 最高成交价
    min_price: float = float('inf')  # 最低成交价

    # 按方向分类统计
    buy_amount: float = 0
    buy_trades: int = 0
    buy_avg_price: float = 0
    sell_amount: float = 0
    sell_trades: int = 0
    sell_avg_price: float = 0

    def add_trade(self, trade: TradeRecord):
        """添加交易记录"""
        self.trades.append(trade)
        self._update_stats(trade)

    def _update_stats(self, trade: TradeRecord):
        """更新统计数据"""
        self.total_amount += trade.amount
        self.total_trades += 1

        # 价格统计
        if trade.price > self.max_price:
            self.max_price = trade.price
        if trade.price < self.min_price:
            self.min_price = trade.price

        # 计算加权平均价
        if self.total_trades > 0:
            total_shares = sum(t.shares for t in self.trades)
            if total_shares > 0:
                self.avg_price = sum(t.price * t.shares for t in self.trades) / total_shares

        # 按方向统计
        if trade.side == 'buy':
            self.buy_amount += trade.amount
            self.buy_trades += 1
            buy_trades = [t for t in self.trades if t.side == 'buy']
            buy_shares = sum(t.shares for t in buy_trades)
            if buy_shares > 0:
                self.buy_avg_price = sum(t.price * t.shares for t in buy_trades) / buy_shares
        else:
            self.sell_amount += trade.amount
            self.sell_trades += 1
            sell_trades = [t for t in self.trades if t.side == 'sell']
            sell_shares = sum(t.shares for t in sell_trades)
            if sell_shares > 0:
                self.sell_avg_price = sum(t.price * t.shares for t in sell_trades) / sell_shares

    def print_summary(self, title: str = "交易汇总"):
        """打印汇总信息"""
        print(f"\n{'='*60}")
        print(f"{title:^60}")
        print(f"{'='*60}")

        if self.total_trades == 0:
            print("  无交易记录")
            return

        print(f"  总成交金额: ${self.total_amount:.2f}")
        print(f"  总成交笔数: {self.total_trades}")
        print(f"  平均成交价: {self.avg_price * 100:.2f}¢")
        print(f"  最高成交价: {self.max_price * 100:.2f}¢")
        if self.min_price < float('inf'):
            print(f"  最低成交价: {self.min_price * 100:.2f}¢")

        if self.buy_trades > 0 or self.sell_trades > 0:
            print(f"\n  买入统计:")
            print(f"    笔数: {self.buy_trades}, 金额: ${self.buy_amount:.2f}, 均价: {self.buy_avg_price * 100:.2f}¢")
            print(f"  卖出统计:")
            print(f"    笔数: {self.sell_trades}, 金额: ${self.sell_amount:.2f}, 均价: {self.sell_avg_price * 100:.2f}¢")

        print(f"{'='*60}")

    def reset(self):
        """重置统计"""
        self.trades = []
        self.total_amount = 0
        self.total_trades = 0
        self.avg_price = 0
        self.max_price = 0
        self.min_price = float('inf')
        self.buy_amount = 0
        self.buy_trades = 0
        self.buy_avg_price = 0
        self.sell_amount = 0
        self.sell_trades = 0
        self.sell_avg_price = 0


# ============ 下单数量计算器 ============

class OrderCalculator:
    """订单数量计算器

    支持按金额、按仓位计算下单数量
    """

    @staticmethod
    def calculate_shares_by_amount(amount: float, price: float) -> int:
        """按金额计算下单数量

        Args:
            amount: 金额（USDT）
            price: 价格（0-1之间的小数）

        Returns:
            int: 下单数量（份额）
        """
        if price <= 0:
            return 0
        shares = int(amount / price)
        return max(0, shares)

    @staticmethod
    def calculate_amount_by_shares(shares: int, price: float) -> float:
        """按数量计算金额

        Args:
            shares: 数量（份额）
            price: 价格（0-1之间的小数）

        Returns:
            float: 金额（USDT）
        """
        return shares * price

    @staticmethod
    def calculate_position_shares(total_balance: float, price: float,
                                   position_ratio: float) -> int:
        """按仓位比例计算下单数量

        Args:
            total_balance: 总余额（USDT）
            price: 价格（0-1之间的小数）
            position_ratio: 仓位比例（0-1，如0.25表示1/4仓）

        Returns:
            int: 下单数量（份额）
        """
        if price <= 0 or position_ratio <= 0:
            return 0
        amount = total_balance * position_ratio
        return OrderCalculator.calculate_shares_by_amount(amount, price)

    @staticmethod
    def get_position_options() -> List[Tuple[str, float]]:
        """获取仓位选项列表

        Returns:
            [(显示名称, 比例), ...]
        """
        return [
            ("1/4 仓位", 0.25),
            ("1/3 仓位", 0.333),
            ("1/2 仓位", 0.5),
            ("全仓", 1.0)
        ]


# ============ 合并/拆分操作 ============

class MergeSplitService:
    """合并/拆分服务

    处理 Opinion.trade 的 merge/split 操作
    """

    @staticmethod
    def merge(client, market_id: int, shares: int, max_retries: int = 3) -> dict:
        """合并操作（YES + NO → USDT）

        Args:
            client: SDK 客户端
            market_id: 市场ID
            shares: 合并数量
            max_retries: 最大重试次数（网络错误时）

        Returns:
            {
                'success': bool,
                'tx_hash': str,
                'error': str,
                'warning': str
            }
        """
        import time
        
        shares_int = int(shares)
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 调用 SDK 的 merge 接口
                result = client.merge(market_id=market_id, shares=shares_int)
                
                # 处理 Tuple 返回值（新版 SDK）
                if isinstance(result, tuple):
                    if result and result[0]:
                        return {'success': True, 'tx_hash': result[0]}
                    else:
                        return {'success': False, 'error': f'合并失败: {result}'}

                # 处理带 errno 的结果（旧版 SDK）
                if hasattr(result, 'errno') and result.errno == 0:
                    tx_hash = ''
                    if result.result:
                        tx_hash = getattr(result.result, 'tx_hash', '') or ''
                    return {'success': True, 'tx_hash': tx_hash}
                else:
                    error_msg = getattr(result, 'errmsg', '合并失败') or '合并失败'
                    return {'success': False, 'error': error_msg}

            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否包含交易哈希
                if 'Transaction hash:' in error_str:
                    tx_hash = error_str.split('Transaction hash:')[-1].strip().split()[0]
                    return {'success': True, 'tx_hash': tx_hash, 'warning': error_str}
                
                # 网络错误时重试
                is_network_error = any(x in error_str.lower() for x in [
                    'ssl', 'connection', 'timeout', 'max retries', 'eof'
                ])
                
                if is_network_error and attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                
                return {'success': False, 'error': error_str}
        
        return {'success': False, 'error': last_error or '合并失败'}

    @staticmethod
    def split(client, market_id: int, amount: float, max_retries: int = 3) -> dict:
        """拆分操作（USDT → YES + NO）

        Args:
            client: SDK 客户端
            market_id: 市场ID
            amount: 拆分金额（USDT）
            max_retries: 最大重试次数（网络错误时）

        Returns:
            {
                'success': bool,
                'tx_hash': str,
                'shares': int,  # 拆分得到的份额
                'error': str,
                'warning': str  # 可能的警告信息
            }
        """
        import time
        
        # amount 必须是整数
        amount_int = int(amount)
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 调用 SDK 的 split 接口
                # SDK 可能返回 Tuple[tx_hash, safe_tx_hash, return_value] 或带 errno 的结果
                result = client.split(market_id=market_id, amount=amount_int)
                
                # 处理 Tuple 返回值（新版 SDK）
                if isinstance(result, tuple):
                    if result and result[0]:  # tx_hash 存在表示成功
                        return {
                            'success': True, 
                            'tx_hash': result[0], 
                            'shares': amount_int
                        }
                    else:
                        return {'success': False, 'error': f'拆分失败: {result}'}
                
                # 处理带 errno 的结果（旧版 SDK）
                if hasattr(result, 'errno') and result.errno == 0:
                    tx_hash = ''
                    if result.result:
                        tx_hash = getattr(result.result, 'tx_hash', '') or ''
                    return {
                        'success': True, 
                        'tx_hash': tx_hash, 
                        'shares': amount_int
                    }
                else:
                    error_msg = getattr(result, 'errmsg', '拆分失败') or '拆分失败'
                    return {'success': False, 'error': error_msg}

            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否包含交易哈希（可能是成功但抛出异常的情况）
                if 'Transaction hash:' in error_str:
                    tx_hash = error_str.split('Transaction hash:')[-1].strip().split()[0]
                    return {
                        'success': True, 
                        'tx_hash': tx_hash, 
                        'shares': amount_int,
                        'warning': error_str
                    }
                
                # 网络错误时重试
                is_network_error = any(x in error_str.lower() for x in [
                    'ssl', 'connection', 'timeout', 'max retries', 'eof'
                ])
                
                if is_network_error and attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))  # 递增等待时间
                    continue
                
                return {'success': False, 'error': error_str}
        
        return {'success': False, 'error': last_error or '拆分失败'}


# ============ 增强版下单服务 ============

class EnhancedOrderService:
    """增强版下单服务

    支持：
    - 按金额下单
    - 按仓位下单
    - 卖出时跳过余额检查
    - 交易汇总统计
    """

    def __init__(self, client, config, format_price_func=None):
        """
        Args:
            client: SDK 客户端
            config: TraderConfig 账户配置
            format_price_func: 价格格式化函数
        """
        self.client = client
        self.config = config
        self.format_price = format_price_func or (lambda p: f"{p*100:.2f}")

        # 交易汇总
        self.summary = TradeSummary()

    def submit_buy_order(self, market_id: int, token_id: str, price: float,
                         amount: float = None, shares: int = None,
                         skip_balance_check: bool = False) -> dict:
        """提交买入订单

        Args:
            market_id: 市场ID
            token_id: Token ID
            price: 价格
            amount: 金额（与shares二选一）
            shares: 数量（与amount二选一）
            skip_balance_check: 是否跳过余额检查

        Returns:
            {
                'success': bool,
                'shares': int,
                'amount': float,
                'order_id': str,
                'error': str
            }
        """
        from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
        from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
        from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER

        try:
            # 计算下单参数
            if amount is not None:
                order_amount = round(amount, 2)
                order_shares = OrderCalculator.calculate_shares_by_amount(amount, price)
            elif shares is not None:
                order_shares = shares
                order_amount = OrderCalculator.calculate_amount_by_shares(shares, price)
            else:
                return {'success': False, 'error': '必须指定 amount 或 shares'}

            # 构建订单
            order_data = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=f"{price:.6f}",
                makerAmountInQuoteToken=order_amount
            )

            # 提交订单
            response = self.client.place_order(order_data, check_approval=True)

            if response.errno == 0:
                order_id = response.result.order_id if hasattr(response.result, 'order_id') else ''

                # 记录交易
                trade = TradeRecord(
                    timestamp=time.time(),
                    side='buy',
                    price=price,
                    shares=order_shares,
                    amount=order_amount,
                    account_remark=self.config.remark,
                    order_id=order_id
                )
                self.summary.add_trade(trade)

                return {
                    'success': True,
                    'shares': order_shares,
                    'amount': order_amount,
                    'order_id': order_id
                }
            else:
                return {
                    'success': False,
                    'error': response.errmsg if hasattr(response, 'errmsg') else f'errno={response.errno}'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def submit_sell_order(self, market_id: int, token_id: str, price: float,
                          shares: int, skip_balance_check: bool = True) -> dict:
        """提交卖出订单

        注意：卖出时默认跳过余额检查，直接提交

        Args:
            market_id: 市场ID
            token_id: Token ID
            price: 价格
            shares: 卖出数量
            skip_balance_check: 是否跳过余额检查（默认True）

        Returns:
            {
                'success': bool,
                'shares': int,
                'amount': float,
                'order_id': str,
                'error': str
            }
        """
        from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
        from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
        from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER

        try:
            # 计算金额
            order_amount = OrderCalculator.calculate_amount_by_shares(shares, price)

            # 构建订单（直接提交，不检查余额）
            order_data = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=f"{price:.6f}",
                makerAmountInBaseToken=shares
            )

            # 提交订单
            response = self.client.place_order(order_data, check_approval=True)

            if response.errno == 0:
                order_id = response.result.order_id if hasattr(response.result, 'order_id') else ''

                # 记录交易
                trade = TradeRecord(
                    timestamp=time.time(),
                    side='sell',
                    price=price,
                    shares=shares,
                    amount=order_amount,
                    account_remark=self.config.remark,
                    order_id=order_id
                )
                self.summary.add_trade(trade)

                return {
                    'success': True,
                    'shares': shares,
                    'amount': order_amount,
                    'order_id': order_id
                }
            else:
                return {
                    'success': False,
                    'error': response.errmsg if hasattr(response, 'errmsg') else f'errno={response.errno}'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def submit_buy_by_position(self, market_id: int, token_id: str, price: float,
                                total_balance: float, position_ratio: float) -> dict:
        """按仓位比例买入

        Args:
            market_id: 市场ID
            token_id: Token ID
            price: 价格
            total_balance: 总余额
            position_ratio: 仓位比例（0-1）

        Returns:
            同 submit_buy_order
        """
        shares = OrderCalculator.calculate_position_shares(total_balance, price, position_ratio)
        if shares <= 0:
            return {'success': False, 'error': '计算份额为0'}

        amount = OrderCalculator.calculate_amount_by_shares(shares, price)
        return self.submit_buy_order(market_id, token_id, price, amount=amount)

    def get_summary(self) -> TradeSummary:
        """获取交易汇总"""
        return self.summary

    def reset_summary(self):
        """重置交易汇总"""
        self.summary.reset()


# ============ 用户交互助手 ============

class OrderInputHelper:
    """订单输入助手

    处理用户交互输入
    """

    @staticmethod
    def prompt_order_method() -> str:
        """提示用户选择下单方式

        Returns:
            'amount' | 'position' | 'shares' | None（取消）
        """
        print("\n请选择下单方式:")
        print("  1. 按金额 - 输入USDT金额，自动计算数量")
        print("  2. 按仓位 - 选择仓位比例（1/4、1/3、1/2、全仓）")
        print("  3. 按数量 - 直接输入份额数量")
        print("  0. 返回")

        choice = input("请选择 (0-3): ").strip()

        if choice == '0' or not choice:
            return None
        elif choice == '1':
            return 'amount'
        elif choice == '2':
            return 'position'
        elif choice == '3':
            return 'shares'
        else:
            print("✗ 无效选择")
            return None

    @staticmethod
    def prompt_amount() -> Optional[float]:
        """提示用户输入金额

        Returns:
            float | None（取消）
        """
        while True:
            amount_input = input("\n请输入金额 ($，留空返回): ").strip()
            if not amount_input:
                return None
            try:
                amount = float(amount_input)
                if amount <= 0:
                    print("✗ 金额必须大于0")
                    continue
                return amount
            except ValueError:
                print("✗ 请输入有效的数字")

    @staticmethod
    def prompt_position_ratio() -> Optional[float]:
        """提示用户选择仓位比例

        Returns:
            float | None（取消）
        """
        options = OrderCalculator.get_position_options()
        print("\n请选择仓位:")
        for i, (name, _) in enumerate(options, 1):
            print(f"  {i}. {name}")
        print("  0. 返回")

        choice = input(f"请选择 (0-{len(options)}): ").strip()
        if choice == '0' or not choice:
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][1]
            else:
                print("✗ 无效选择")
                return None
        except ValueError:
            print("✗ 请输入有效的数字")
            return None

    @staticmethod
    def prompt_shares() -> Optional[int]:
        """提示用户输入数量

        Returns:
            int | None（取消）
        """
        while True:
            shares_input = input("\n请输入数量（份额，留空返回）: ").strip()
            if not shares_input:
                return None
            try:
                shares = int(shares_input)
                if shares <= 0:
                    print("✗ 数量必须大于0")
                    continue
                return shares
            except ValueError:
                print("✗ 请输入有效的整数")

    @staticmethod
    def prompt_sell_after_split(bid1_price: float, ask1_price: float,
                                  format_price_func=None) -> Tuple[str, Optional[float]]:
        """拆分完成后提示卖出选项

        Args:
            bid1_price: 买1价
            ask1_price: 卖1价
            format_price_func: 价格格式化函数

        Returns:
            (action, price)
            action: 'default' | 'custom' | 'bid1' | 'ask1' | 'skip'
            price: 卖出价格（skip时为None）
        """
        fmt = format_price_func or (lambda p: f"{p*100:.2f}")

        print("\n拆分完成！请选择卖出方式:")
        print(f"  1. 卖出（默认，买1价 {fmt(bid1_price)}¢）")
        print(f"  2. 卖出（自定义价格）")
        print(f"  3. 卖出（买1价 {fmt(bid1_price)}¢）")
        print(f"  4. 卖出（卖1价 {fmt(ask1_price)}¢）")
        print(f"  5. 不卖出")

        choice = input("请选择 (1-5，默认1): ").strip()

        if not choice or choice == '1':
            return ('default', bid1_price)
        elif choice == '2':
            # 自定义价格
            while True:
                price_input = input("请输入卖出价格（分，如50）: ").strip()
                try:
                    price_cent = float(price_input)
                    if price_cent <= 0 or price_cent >= 100:
                        print("✗ 价格必须在 0-100 之间")
                        continue
                    return ('custom', price_cent / 100)
                except ValueError:
                    print("✗ 请输入有效的数字")
        elif choice == '3':
            return ('bid1', bid1_price)
        elif choice == '4':
            return ('ask1', ask1_price)
        elif choice == '5':
            return ('skip', None)
        else:
            print("✗ 无效选择，默认不卖出")
            return ('skip', None)
