"""
Opinion SDK 服务模块
包含订单簿、订单构建、用户确认、市场信息、账户迭代、持仓等服务
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from opinion_trader.display.display import OrderbookDisplay, PositionDisplay, ProgressBar


class OrderbookService:
    """订单簿服务模块 - 统一获取和解析订单簿数据"""

    @staticmethod
    def fetch(client, token_id: str, max_depth: int = 5) -> dict:
        """获取并解析订单簿

        Args:
            client: Opinion SDK客户端
            token_id: Token ID
            max_depth: 计算深度的最大档位数

        Returns:
            {
                'success': bool,
                'bids': [(price, size), ...],  # 按价格降序
                'asks': [(price, size), ...],  # 按价格升序
                'bid1_price': float,           # 买1价
                'ask1_price': float,           # 卖1价
                'bid1_size': float,            # 买1量
                'ask1_size': float,            # 卖1量
                'bid_depth': float,            # 买盘深度(美元)
                'ask_depth': float,            # 卖盘深度(美元)
                'spread': float,               # 价差
                'mid_price': float,            # 中间价
                'raw': orderbook对象,
                'error': str (如果失败)
            }
        """
        try:
            response = client.get_orderbook(token_id=token_id)
            if response.errno != 0:
                return {'success': False, 'error': response.errmsg if hasattr(response, 'errmsg') else '获取订单簿失败'}

            orderbook = response.result

            # 排序
            bids_sorted = sorted(orderbook.bids, key=lambda x: float(
                x.price), reverse=True) if orderbook.bids else []
            asks_sorted = sorted(orderbook.asks, key=lambda x: float(
                x.price)) if orderbook.asks else []

            # 转换为元组列表
            bids = [(float(b.price), float(b.size)) for b in bids_sorted]
            asks = [(float(a.price), float(a.size)) for a in asks_sorted]

            # 计算深度
            bid_depth = sum(price * size for price, size in bids[:max_depth])
            ask_depth = sum(price * size for price, size in asks[:max_depth])

            # 买1卖1
            bid1_price = bids[0][0] if bids else 0
            bid1_size = bids[0][1] if bids else 0
            ask1_price = asks[0][0] if asks else 0
            ask1_size = asks[0][1] if asks else 0

            # 价差和中间价
            spread = ask1_price - bid1_price if bid1_price > 0 and ask1_price > 0 else 0
            mid_price = (bid1_price + ask1_price) / \
                2 if bid1_price > 0 and ask1_price > 0 else 0

            return {
                'success': True,
                'bids': bids,
                'asks': asks,
                'bid1_price': bid1_price,
                'ask1_price': ask1_price,
                'bid1_size': bid1_size,
                'ask1_size': ask1_size,
                'bid_depth': bid_depth,
                'ask_depth': ask_depth,
                'spread': spread,
                'mid_price': mid_price,
                'raw': orderbook
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def fetch_and_display(client, token_id: str, title: str = "盘口信息",
                          mode: str = "simple", max_rows: int = 5,
                          format_price_func=None) -> dict:
        """获取订单簿并显示

        Returns:
            同 fetch() 返回值
        """
        result = OrderbookService.fetch(client, token_id, max_depth=max_rows)
        if result['success']:
            OrderbookDisplay.show(
                bids=result['bids'],
                asks=result['asks'],
                mode=mode,
                max_rows=max_rows,
                title=title,
                format_price_func=format_price_func
            )
        return result

    @staticmethod
    def check_liquidity(orderbook_result: dict, required_amount: float,
                        side: str = 'buy') -> dict:
        """检查流动性是否充足

        Args:
            orderbook_result: fetch()的返回值
            required_amount: 需要的金额
            side: 'buy' 检查卖盘深度, 'sell' 检查买盘深度

        Returns:
            {
                'sufficient': bool,
                'available': float,
                'required': float,
                'shortage': float
            }
        """
        if not orderbook_result.get('success'):
            return {'sufficient': False, 'available': 0, 'required': required_amount, 'shortage': required_amount}

        available = orderbook_result['ask_depth'] if side == 'buy' else orderbook_result['bid_depth']
        shortage = max(0, required_amount - available)

        return {
            'sufficient': available >= required_amount,
            'available': available,
            'required': required_amount,
            'shortage': shortage
        }

    @staticmethod
    def get_price_at_level(orderbook_result: dict, side: str, level: int = 0, fallback: bool = True) -> float:
        """获取指定档位的价格

        Args:
            orderbook_result: fetch()的返回值
            side: 'bid' 获取买盘价格, 'ask' 获取卖盘价格
            level: 档位索引 (0=第1档, 1=第2档, ...)
            fallback: 如果指定档位不存在，是否回退到第1档

        Returns:
            价格，如果失败返回 0
        """
        if not orderbook_result.get('success'):
            return 0

        prices = orderbook_result['bids'] if side == 'bid' else orderbook_result['asks']
        if not prices:
            return 0

        if len(prices) > level:
            return prices[level][0]
        elif fallback and prices:
            return prices[0][0]
        return 0


class OrderBuilder:
    """订单构建器 - 统一创建和执行订单"""

    @staticmethod
    def create_limit_buy(token_id: str, price: float, shares: int,
                         reduce_only: bool = False):
        """创建限价买单"""
        from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
        from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
        from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER

        return PlaceOrderDataInput(
            token_id=token_id,
            price=price,
            side=OrderSide.BUY,
            order_type=LIMIT_ORDER,
            shares=shares,
            reduce_only=reduce_only
        )

    @staticmethod
    def create_limit_sell(token_id: str, price: float, shares: int,
                          reduce_only: bool = False):
        """创建限价卖单"""
        from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
        from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
        from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER

        return PlaceOrderDataInput(
            token_id=token_id,
            price=price,
            side=OrderSide.SELL,
            order_type=LIMIT_ORDER,
            shares=shares,
            reduce_only=reduce_only
        )

    @staticmethod
    def create_market_buy(token_id: str, shares: int):
        """创建市价买单"""
        from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
        from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
        from opinion_clob_sdk.chain.py_order_utils.model.order_type import MARKET_ORDER

        return PlaceOrderDataInput(
            token_id=token_id,
            side=OrderSide.BUY,
            order_type=MARKET_ORDER,
            shares=shares
        )

    @staticmethod
    def create_market_sell(token_id: str, shares: int):
        """创建市价卖单"""
        from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
        from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
        from opinion_clob_sdk.chain.py_order_utils.model.order_type import MARKET_ORDER

        return PlaceOrderDataInput(
            token_id=token_id,
            side=OrderSide.SELL,
            order_type=MARKET_ORDER,
            shares=shares
        )

    @staticmethod
    def create_order(token_id: str, price: float, shares: int, side: str,
                     order_type: str = 'limit', reduce_only: bool = False):
        """通用订单创建方法

        Args:
            token_id: Token ID
            price: 价格 (市价单忽略)
            shares: 数量
            side: 'buy' 或 'sell'
            order_type: 'limit' 或 'market'
            reduce_only: 是否仅减仓
        """
        side = side.lower()
        order_type = order_type.lower()

        if order_type == 'market':
            if side == 'buy':
                return OrderBuilder.create_market_buy(token_id, shares)
            else:
                return OrderBuilder.create_market_sell(token_id, shares)
        else:
            if side == 'buy':
                return OrderBuilder.create_limit_buy(token_id, price, shares, reduce_only)
            else:
                return OrderBuilder.create_limit_sell(token_id, price, shares, reduce_only)

    @staticmethod
    def execute(client, order, translate_error_func=None, remark: str = '') -> dict:
        """执行订单

        Args:
            client: Opinion SDK客户端
            order: PlaceOrderDataInput对象
            translate_error_func: 错误翻译函数
            remark: 账户备注(用于日志)

        Returns:
            {
                'success': bool,
                'result': 原始返回结果,
                'error': str (如果失败)
            }
        """
        try:
            result = client.place_order(order, check_approval=True)
            if result.errno == 0:
                return {'success': True, 'result': result}
            else:
                error_msg = result.errmsg if hasattr(
                    result, 'errmsg') else '未知错误'
                if translate_error_func:
                    error_msg = translate_error_func(error_msg)
                return {'success': False, 'error': error_msg, 'result': result}
        except Exception as e:
            error_msg = str(e)
            if translate_error_func:
                error_msg = translate_error_func(error_msg)
            return {'success': False, 'error': error_msg}

    @staticmethod
    def execute_with_retry(client, order, max_retries: int = 2,
                           translate_error_func=None, remark: str = '') -> dict:
        """带重试的订单执行

        Args:
            max_retries: 最大重试次数
            其他参数同 execute()
        """
        last_error = None
        for attempt in range(max_retries + 1):
            result = OrderBuilder.execute(
                client, order, translate_error_func, remark)
            if result['success']:
                return result
            last_error = result.get('error', '未知错误')
            if attempt < max_retries:
                time.sleep(0.5)
        return {'success': False, 'error': last_error}


class UserConfirmation:
    """用户确认交互模块 - 统一处理用户输入确认"""

    @staticmethod
    def yes_no(prompt: str, default: bool = False) -> bool:
        """简单是/否确认

        Args:
            prompt: 提示语
            default: 默认值 (直接回车时使用)

        Returns:
            bool: 用户确认结果
        """
        suffix = "(Y/n)" if default else "(y/N)"
        response = input(f"{prompt} {suffix}: ").strip().lower()
        if not response:
            return default
        return response in ('y', 'yes', '是')

    @staticmethod
    def confirm_keyword(prompt: str, keyword: str = 'yes') -> bool:
        """关键词确认 (需要输入特定词如 'yes' 或 'done')

        Args:
            prompt: 提示语
            keyword: 需要输入的关键词

        Returns:
            bool: 是否输入了正确关键词
        """
        response = input(f"{prompt}: ").strip().lower()
        return response == keyword.lower()

    @staticmethod
    def continue_or_abort(warning_msg: str, show_warning: bool = True) -> bool:
        """警告后询问是否继续

        Args:
            warning_msg: 警告消息
            show_warning: 是否显示警告前缀

        Returns:
            bool: 是否继续
        """
        if show_warning:
            print(f"\n[!] {warning_msg}")
        return UserConfirmation.yes_no("是否继续?")

    @staticmethod
    def select_option(title: str, options: list, allow_cancel: bool = True) -> int:
        """多选项选择

        Args:
            title: 标题
            options: 选项列表 [(label, description), ...] 或 [label, ...]
            allow_cancel: 是否允许取消(留空返回)

        Returns:
            int: 选择的索引 (1-based), 0表示取消
        """
        print(f"\n{title}")
        for i, opt in enumerate(options, 1):
            if isinstance(opt, tuple):
                label, desc = opt
                print(f"  [{i}] {label} - {desc}")
            else:
                print(f"  [{i}] {opt}")

        cancel_hint = " (留空返回)" if allow_cancel else ""
        while True:
            choice = input(f"\n请选择{cancel_hint}: ").strip()
            if not choice:
                if allow_cancel:
                    return 0
                print("  请输入有效选项")
                continue
            try:
                idx = int(choice)
                if 1 <= idx <= len(options):
                    return idx
            except ValueError:
                pass
            print("  无效输入，请重新选择")

    @staticmethod
    def confirm_with_summary(title: str, items: list, keyword: str = 'done') -> bool:
        """显示摘要后确认

        Args:
            title: 标题
            items: 摘要项 [(label, value), ...]
            keyword: 确认关键词

        Returns:
            bool: 是否确认
        """
        print(f"\n{title}")
        print("-" * 40)
        for label, value in items:
            print(f"  {label}: {value}")
        print("-" * 40)
        return UserConfirmation.confirm_keyword(f"确认无误请输入 '{keyword}'", keyword)

    @staticmethod
    def handle_insufficient_balance_choice(insufficient_list: list) -> tuple:
        """处理余额不足的选择

        Args:
            insufficient_list: [(remark, balance, required), ...] 或 [(idx, remark, balance, required), ...]

        Returns:
            (action, skip_remarks)
            action: 'continue'/'skip'/'cancel'
            skip_remarks: 需跳过的账户备注集合
        """
        if not insufficient_list:
            return ('continue', None)

        print(f"\n[!] 余额不足警告:")
        for item in insufficient_list:
            if len(item) == 3:
                remark, balance, required = item
            else:
                _, remark, balance, required = item
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")

        options = [
            ("继续", "忽略警告继续执行"),
            ("跳过", "跳过余额不足的账户"),
            ("停止", "取消操作")
        ]
        choice = UserConfirmation.select_option(
            "请选择操作", options, allow_cancel=False)

        if choice == 1:
            return ('continue', None)
        elif choice == 2:
            skip_remarks = set()
            for item in insufficient_list:
                remark = item[0] if len(item) == 3 else item[1]
                skip_remarks.add(remark)
            return ('skip', skip_remarks)
        else:
            return ('cancel', None)


class MarketInfoService:
    """市场信息服务 - 统一获取市场详情"""

    @staticmethod
    def get_market_info(client, market_id: int) -> dict:
        """获取市场信息 (自动判断分类/二元市场)

        Args:
            client: Opinion SDK客户端
            market_id: 市场ID

        Returns:
            {
                'success': bool,
                'is_categorical': bool,      # 是否分类市场
                'title': str,                # 市场标题
                'child_markets': list,       # 子市场列表 (分类市场)
                'yes_token_id': str,         # Yes Token ID (二元市场)
                'no_token_id': str,          # No Token ID (二元市场)
                'tokens': list,              # Token列表
                'raw': 原始数据,
                'error': str (如果失败)
            }
        """
        # 记录API错误信息，用于最终提示
        cat_error = None
        bin_error = None

        # 先尝试作为分类市场获取
        try:
            cat_resp = client.get_categorical_market(market_id=market_id)
            if cat_resp.errno == 0 and cat_resp.result and cat_resp.result.data:
                data = cat_resp.result.data
                child_markets = []
                if hasattr(data, 'child_markets') and data.child_markets:
                    child_markets = data.child_markets

                return {
                    'success': True,
                    'is_categorical': True,
                    'title': data.market_title if hasattr(data, 'market_title') else '',
                    'child_markets': child_markets,
                    'yes_token_id': None,
                    'no_token_id': None,
                    'tokens': [],
                    'raw': data
                }
            else:
                cat_error = cat_resp.errmsg if hasattr(
                    cat_resp, 'errmsg') and cat_resp.errmsg else f'errno={cat_resp.errno}'
        except Exception as e:
            cat_error = str(e)

        # 尝试作为二元市场获取
        try:
            bin_resp = client.get_market(market_id=market_id)
            if bin_resp.errno == 0 and bin_resp.result and bin_resp.result.data:
                data = bin_resp.result.data
                yes_token_id = None
                no_token_id = None
                tokens = []

                # 尝试多种方式获取token
                if hasattr(data, 'yes_token') and data.yes_token:
                    yes_token_id = str(data.yes_token.token_id)
                    no_token_id = str(
                        data.no_token.token_id) if data.no_token else None
                elif hasattr(data, 'yes_token_id') and data.yes_token_id:
                    yes_token_id = str(data.yes_token_id)
                    no_token_id = str(data.no_token_id) if hasattr(
                        data, 'no_token_id') else None
                elif hasattr(data, 'tokens') and data.tokens:
                    tokens = data.tokens
                    for token in tokens:
                        ticker = token.ticker.upper() if hasattr(token, 'ticker') else ''
                        if 'YES' in ticker:
                            yes_token_id = str(token.token_id)
                        elif 'NO' in ticker:
                            no_token_id = str(token.token_id)

                return {
                    'success': True,
                    'is_categorical': False,
                    'title': data.market_title if hasattr(data, 'market_title') else '',
                    'child_markets': None,
                    'yes_token_id': yes_token_id,
                    'no_token_id': no_token_id,
                    'tokens': tokens,
                    'raw': data
                }
            else:
                bin_error = bin_resp.errmsg if hasattr(
                    bin_resp, 'errmsg') and bin_resp.errmsg else f'errno={bin_resp.errno}'
        except Exception as e:
            bin_error = str(e)

        # 两种方式都失败，返回详细错误
        # 优先使用二元市场的错误信息（更常见）
        error_msg = bin_error or cat_error or '未知错误'
        return {'success': False, 'error': f'市场不存在或已下架，请检查市场ID ({error_msg})'}

    @staticmethod
    def get_child_market_info(client, child_market_id: int) -> dict:
        """获取子市场信息

        Returns:
            {
                'success': bool,
                'title': str,
                'yes_token_id': str,
                'no_token_id': str,
                'error': str (如果失败)
            }
        """
        try:
            resp = client.get_market(market_id=child_market_id)
            if resp.errno != 0 or not resp.result or not resp.result.data:
                return {'success': False, 'error': '获取子市场失败'}

            data = resp.result.data
            yes_token_id = None
            no_token_id = None

            if hasattr(data, 'yes_token') and data.yes_token:
                yes_token_id = str(data.yes_token.token_id)
                no_token_id = str(
                    data.no_token.token_id) if data.no_token else None
            elif hasattr(data, 'yes_token_id'):
                yes_token_id = str(data.yes_token_id)
                no_token_id = str(data.no_token_id) if hasattr(
                    data, 'no_token_id') else None
            elif hasattr(data, 'tokens') and data.tokens:
                for token in data.tokens:
                    ticker = token.ticker.upper() if hasattr(token, 'ticker') else ''
                    if 'YES' in ticker:
                        yes_token_id = str(token.token_id)
                    elif 'NO' in ticker:
                        no_token_id = str(token.token_id)

            return {
                'success': True,
                'title': data.market_title if hasattr(data, 'market_title') else '',
                'yes_token_id': yes_token_id,
                'no_token_id': no_token_id
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def get_all_child_markets_info(client, parent_market_id: int,
                                   include_prices: bool = False) -> dict:
        """获取分类市场下所有子市场信息

        Args:
            client: SDK客户端
            parent_market_id: 父市场ID
            include_prices: 是否获取当前价格

        Returns:
            {
                'success': bool,
                'title': str,           # 父市场标题
                'children': {           # 子市场信息字典
                    child_market_id: {
                        'title': str,
                        'yes_token_id': str,
                        'no_token_id': str,
                        'yes_price': float,  # 如果include_prices=True
                        'no_price': float
                    },
                    ...
                },
                'error': str
            }
        """
        parent_info = MarketInfoService.get_market_info(
            client, parent_market_id)
        if not parent_info['success']:
            return parent_info

        if not parent_info['is_categorical']:
            return {'success': False, 'error': '不是分类市场'}

        children = {}
        for child in parent_info.get('child_markets', []):
            child_id = child.market_id
            child_info = MarketInfoService.get_child_market_info(
                client, child_id)
            if not child_info['success']:
                continue

            child_data = {
                'title': child_info['title'] or (child.market_title if hasattr(child, 'market_title') else ''),
                'yes_token_id': child_info['yes_token_id'],
                'no_token_id': child_info['no_token_id']
            }

            # 获取价格
            if include_prices and child_info['yes_token_id']:
                child_data['yes_price'] = 0
                child_data['no_price'] = 0

                try:
                    ob_yes = OrderbookService.fetch(
                        client, child_info['yes_token_id'])
                    if ob_yes['success']:
                        child_data['yes_price'] = ob_yes['bid1_price']
                except Exception:
                    pass

                try:
                    if child_info['no_token_id']:
                        ob_no = OrderbookService.fetch(
                            client, child_info['no_token_id'])
                        if ob_no['success']:
                            child_data['no_price'] = ob_no['bid1_price']
                except Exception:
                    pass

            children[child_id] = child_data

        return {
            'success': True,
            'title': parent_info['title'],
            'children': children
        }


class AccountIterator:
    """账户迭代器 - 统一处理多账户操作"""

    def __init__(self, configs: list, clients: list):
        """
        Args:
            configs: TraderConfig列表
            clients: Client列表
        """
        self.configs = configs
        self.clients = clients

    def iterate(self, selected_indices: list, callback,
                show_progress: bool = True, progress_prefix: str = '处理账户') -> dict:
        """遍历选中的账户执行操作

        Args:
            selected_indices: 账户索引列表 [1, 2, 3, ...] (1-based)
            callback: 回调函数 func(acc_idx, client, config) -> result
            show_progress: 是否显示进度
            progress_prefix: 进度条前缀

        Returns:
            {acc_idx: result, ...}
        """
        results = {}
        total = len(selected_indices)
        errors = []

        for i, acc_idx in enumerate(selected_indices):
            if acc_idx < 1 or acc_idx > len(self.configs):
                continue

            config = self.configs[acc_idx - 1]
            client = self.clients[acc_idx - 1]

            if show_progress:
                ProgressBar.show_progress(
                    i, total, prefix=progress_prefix, suffix=config.remark)

            try:
                results[acc_idx] = callback(acc_idx, client, config)
            except Exception as e:
                results[acc_idx] = {'error': str(e)}
                errors.append((config.remark, str(e)))

        if show_progress:
            ProgressBar.show_progress(
                total, total, prefix=progress_prefix, suffix='完成')

        # 显示错误
        for remark, error in errors:
            print(f"  [!] [{remark}] 异常: {error}")

        return results

    def iterate_all(self, callback, show_progress: bool = True,
                    progress_prefix: str = '处理账户') -> dict:
        """遍历所有账户"""
        all_indices = list(range(1, len(self.configs) + 1))
        return self.iterate(all_indices, callback, show_progress, progress_prefix)

    def iterate_parallel(self, selected_indices: list, callback,
                         max_workers: int = 5, show_progress: bool = True) -> dict:
        """并行遍历账户 (使用线程池)

        Args:
            selected_indices: 账户索引列表
            callback: 回调函数 func(acc_idx, client, config) -> result
            max_workers: 最大并发数
            show_progress: 是否显示进度

        Returns:
            {acc_idx: result, ...}
        """
        results = {}
        total = len(selected_indices)
        completed = 0

        def worker(acc_idx):
            config = self.configs[acc_idx - 1]
            client = self.clients[acc_idx - 1]
            return acc_idx, callback(acc_idx, client, config)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker, idx): idx for idx in selected_indices
                       if 1 <= idx <= len(self.configs)}

            for future in as_completed(futures):
                try:
                    acc_idx, result = future.result()
                    results[acc_idx] = result
                except Exception as e:
                    acc_idx = futures[future]
                    results[acc_idx] = {'error': str(e)}

                completed += 1
                if show_progress:
                    ProgressBar.show_progress(completed, total, prefix='并行处理')

        return results

    def get_balances(self, selected_indices: list, get_balance_func,
                     show_progress: bool = True) -> dict:
        """获取多个账户余额

        Args:
            selected_indices: 账户索引列表
            get_balance_func: 获取余额函数 func(config) -> float

        Returns:
            {acc_idx: balance, ...}
        """
        def callback(acc_idx, client, config):
            return get_balance_func(config)

        return self.iterate(selected_indices, callback, show_progress, '查询余额')

    def filter_by_balance(self, selected_indices: list, get_balance_func,
                          min_balance: float) -> tuple:
        """按余额筛选账户

        Returns:
            (sufficient_indices, insufficient_list)
            sufficient_indices: 余额充足的账户索引列表
            insufficient_list: [(remark, balance, required), ...]
        """
        balances = self.get_balances(selected_indices, get_balance_func)

        sufficient = []
        insufficient = []

        for acc_idx in selected_indices:
            config = self.configs[acc_idx - 1]
            balance = balances.get(acc_idx, 0)

            if isinstance(balance, dict) and 'error' in balance:
                insufficient.append((config.remark, 0, min_balance))
            elif balance >= min_balance:
                sufficient.append(acc_idx)
            else:
                insufficient.append((config.remark, balance, min_balance))

        return sufficient, insufficient


class PositionService:
    """持仓服务模块 - 统一获取和处理持仓"""

    @staticmethod
    def get_positions(client, market_id: int = 0, token_id: str = None) -> list:
        """获取持仓列表

        Args:
            client: SDK客户端
            market_id: 按市场ID过滤 (0表示不过滤)
            token_id: 按Token ID过滤

        Returns:
            解析后的持仓列表 [{...}, ...]
        """
        try:
            response = client.get_my_positions()
            if response.errno != 0:
                return []

            positions = response.result.list if hasattr(
                response.result, 'list') else []
            result = []

            for p in positions:
                shares = int(
                    float(p.shares_owned if hasattr(p, 'shares_owned') else 0))
                if shares <= 0:
                    continue

                # 过滤
                if token_id and str(p.token_id) != str(token_id):
                    continue
                if market_id and hasattr(p, 'market_id') and p.market_id != market_id:
                    continue

                parsed = PositionDisplay.parse_sdk_position(p)
                if parsed:
                    parsed['token_id'] = str(p.token_id) if hasattr(
                        p, 'token_id') else None
                    result.append(parsed)

            return result
        except Exception:
            return []

    @staticmethod
    def get_token_balance(client, token_id: str) -> int:
        """获取特定token的持仓数量"""
        positions = PositionService.get_positions(client, token_id=token_id)
        return positions[0]['shares'] if positions else 0

    @staticmethod
    def get_position_by_token(client, token_id: str) -> dict:
        """获取特定token的持仓详情"""
        positions = PositionService.get_positions(client, token_id=token_id)
        return positions[0] if positions else None

    @staticmethod
    def get_positions_summary(client) -> dict:
        """获取持仓汇总

        Returns:
            {
                'total_value': float,
                'total_cost': float,
                'total_pnl': float,
                'pnl_percent': float,
                'position_count': int,
                'positions': list
            }
        """
        positions = PositionService.get_positions(client)

        total_value = sum(p.get('current_value', 0) for p in positions)
        total_cost = sum(p.get('cost', 0) for p in positions)
        total_pnl = total_value - total_cost
        pnl_percent = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        return {
            'total_value': total_value,
            'total_cost': total_cost,
            'total_pnl': total_pnl,
            'pnl_percent': pnl_percent,
            'position_count': len(positions),
            'positions': positions
        }

    @staticmethod
    def wait_for_position_update(client, token_id: str, initial_balance: int,
                                 expected_direction: str, timeout: int = 10,
                                 check_interval: float = 1.0) -> tuple:
        """等待持仓更新

        Args:
            client: SDK客户端
            token_id: Token ID
            initial_balance: 初始持仓
            expected_direction: 'increase' 或 'decrease'
            timeout: 超时秒数
            check_interval: 检查间隔秒数

        Returns:
            (success, new_balance)
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                current = PositionService.get_token_balance(client, token_id)

                if expected_direction == 'increase' and current > initial_balance:
                    return True, current
                elif expected_direction == 'decrease' and current < initial_balance:
                    return True, current

                time.sleep(check_interval)
            except Exception:
                time.sleep(check_interval)

        return False, initial_balance


def handle_insufficient_balance(insufficient_accounts: list) -> tuple:
    """处理余额不足的账户

    Args:
        insufficient_accounts: [(idx, remark, balance, required), ...] 或 [(remark, balance, required), ...] 余额不足的账户列表

    Returns:
        (action, skip_remarks)
        action: 'continue' 继续执行, 'skip' 跳过不足账户, 'cancel' 取消
        skip_remarks: 需要跳过的账户备注集合（仅当action='skip'时有效）
    """
    if not insufficient_accounts:
        return ('continue', None)

    print(f"\n[!] 余额不足警告:")
    for item in insufficient_accounts:
        if len(item) == 3:
            remark, balance, required = item
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")
        elif len(item) == 4:
            _, remark, balance, required = item
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")

    print(f"\n请选择操作:")
    print(f"  [1] 继续 - 忽略警告继续执行")
    print(f"  [2] 跳过 - 跳过余额不足的账户，仅使用余额充足的账户")
    print(f"  [3] 停止 - 取消操作")

    while True:
        choice = input("\n请选择 (1/2/3): ").strip()
        if choice == '1':
            return ('continue', None)
        elif choice == '2':
            # 获取需要跳过的账户备注列表
            skip_remarks = set()
            for item in insufficient_accounts:
                if len(item) == 3:
                    remark, _, _ = item
                elif len(item) == 4:
                    _, remark, _, _ = item
                skip_remarks.add(remark)
            return ('skip', skip_remarks)
        elif choice == '3':
            return ('cancel', None)
        else:
            print("  无效输入，请输入 1、2 或 3")


# ============ 市场列表服务 ============

class MarketListService:
    """市场列表服务 - 后台获取和缓存市场列表 (SSOT: Single Source of Truth)

    所有市场数据的读写都必须通过此服务，确保数据一致性。
    支持：
    - 程序启动时自动加载
    - 后台定期自动刷新
    - 线程安全的读写操作
    """

    import threading

    _markets_cache = []  # 市场列表缓存
    _cache_time = 0  # 缓存时间
    _loading = False  # 是否正在加载
    _loaded = False  # 是否已加载完成
    _lock = threading.Lock()  # 读写锁

    # 后台刷新相关
    _client = None  # SDK客户端引用
    _auto_refresh_enabled = False  # 是否启用自动刷新
    _refresh_interval = 60  # 刷新间隔（秒）
    _refresh_thread = None  # 刷新线程
    _stop_event = threading.Event()  # 停止事件

    # Opinion.trade 市场链接前缀
    MARKET_URL_PREFIX = "https://opinion.trade/market/"

    @classmethod
    def initialize(cls, client, auto_refresh: bool = True, refresh_interval: int = 60):
        """初始化市场列表服务（程序启动时调用）

        Args:
            client: SDK客户端
            auto_refresh: 是否启用自动刷新
            refresh_interval: 刷新间隔（秒），默认60秒
        """
        import threading

        with cls._lock:
            cls._client = client
            cls._refresh_interval = refresh_interval

        # 立即执行首次加载
        cls._fetch_and_update()

        # 启动自动刷新
        if auto_refresh:
            cls.start_auto_refresh()

    @classmethod
    def start_auto_refresh(cls):
        """启动后台自动刷新线程"""
        import threading

        if cls._auto_refresh_enabled:
            return

        cls._auto_refresh_enabled = True
        cls._stop_event.clear()

        def refresh_loop():
            while not cls._stop_event.is_set():
                # 等待刷新间隔
                cls._stop_event.wait(cls._refresh_interval)
                if cls._stop_event.is_set():
                    break
                # 执行刷新
                cls._fetch_and_update()

        cls._refresh_thread = threading.Thread(
            target=refresh_loop, daemon=True, name="MarketListRefresh")
        cls._refresh_thread.start()

    @classmethod
    def stop_auto_refresh(cls):
        """停止后台自动刷新"""
        cls._auto_refresh_enabled = False
        cls._stop_event.set()
        if cls._refresh_thread and cls._refresh_thread.is_alive():
            cls._refresh_thread.join(timeout=2)
        cls._refresh_thread = None

    @classmethod
    def _fetch_and_update(cls):
        """获取并更新市场数据（内部方法）"""
        import threading

        if cls._loading or cls._client is None:
            return

        with cls._lock:
            if cls._loading:
                return
            cls._loading = True

        try:
            markets = cls._fetch_all_markets(cls._client)
            with cls._lock:
                cls._markets_cache = markets
                cls._cache_time = time.time()
                cls._loaded = True
        except Exception:
            pass  # 静默失败，保留旧缓存
        finally:
            with cls._lock:
                cls._loading = False

    @classmethod
    def start_background_fetch(cls, client, callback=None):
        """启动后台线程获取市场列表（兼容旧接口）

        Args:
            client: SDK客户端
            callback: 加载完成后的回调函数（已废弃，保留兼容）
        """
        import threading

        # 如果已经初始化过，直接返回
        if cls._client is not None and cls._loaded:
            if callback:
                callback(cls._markets_cache)
            return

        # 使用新的初始化方法
        cls._client = client

        if cls._loading:
            return

        with cls._lock:
            cls._loading = True

        def fetch_markets():
            try:
                markets = cls._fetch_all_markets(client)
                with cls._lock:
                    cls._markets_cache = markets
                    cls._cache_time = time.time()
                    cls._loaded = True
                if callback:
                    callback(markets)
            except Exception as e:
                pass  # 静默失败
            finally:
                with cls._lock:
                    cls._loading = False

        thread = threading.Thread(target=fetch_markets, daemon=True)
        thread.start()

    @classmethod
    def _fetch_all_markets(cls, client, limit: int = 50) -> list:
        """获取所有活跃市场并按到期时间排序

        优先使用 SDK 的 get_markets 方法，失败时回退到 HTTP API
        """
        from datetime import datetime

        markets = []

        # 方法1: 使用 SDK 的 get_markets 方法
        try:
            result = client.get_markets()
            if result.errno == 0 and result.result:
                # SDK 返回 result.result.list（不是 data）
                market_list = getattr(result.result, 'list', None) or []
                for m in market_list:
                    # 从 SDK 对象获取属性
                    market_id = getattr(m, 'market_id', None)
                    if not market_id:
                        continue

                    # SDK 使用 cutoff_at（秒级时间戳，不是毫秒）
                    cutoff_at = getattr(m, 'cutoff_at', 0) or 0
                    end_time = datetime.fromtimestamp(
                        cutoff_at) if cutoff_at else None

                    title = getattr(m, 'market_title', '') or ''
                    # 判断是否分类市场：有 child_markets 且不为空
                    child_markets = getattr(m, 'child_markets', None)
                    is_cat = bool(child_markets and len(child_markets) > 0)
                    volume = float(getattr(m, 'volume', 0) or 0)

                    markets.append({
                        'market_id': market_id,
                        'title': title,
                        'end_time': end_time,
                        'end_time_str': end_time.strftime('%m-%d %H:%M') if end_time else '-',
                        'is_categorical': is_cat,
                        'volume': volume,
                        'slug': '',
                        'url': f"{cls.MARKET_URL_PREFIX}{market_id}",
                    })

                if markets:
                    # 按到期时间排序（最近到期的在前，None 排最后）
                    markets.sort(
                        key=lambda x: x['end_time'] if x['end_time'] else datetime.max)
                    return markets
        except Exception:
            pass  # SDK 方法失败，尝试 HTTP API

        # 方法2: 回退到 HTTP API (兼容旧版本)
        try:
            import requests
            urls_to_try = [
                "https://proxy.opinion.trade:8443/api/bsc/api/v2/markets",
                "https://proxy.opinion.trade:8443/api/bsc/api/v2/market/list",
            ]

            for url in urls_to_try:
                try:
                    params = {'chainId': 56, 'limit': limit}
                    response = requests.get(url, params=params, timeout=15)

                    if response.status_code == 200:
                        data = response.json()
                        if data.get('errno') == 0:
                            result = data.get('result', {})
                            market_list = result.get(
                                'list', []) or result.get('markets', []) or []
                            if isinstance(result, list):
                                market_list = result

                            for m in market_list:
                                end_time_ms = m.get(
                                    'endTime', 0) or m.get('end_time', 0)
                                end_time = datetime.fromtimestamp(
                                    end_time_ms / 1000) if end_time_ms else None
                                market_id = m.get(
                                    'marketId') or m.get('market_id')
                                slug = m.get('slug', '') or m.get(
                                    'marketSlug', '')
                                title = m.get('marketTitle', '') or m.get(
                                    'title', '') or m.get('market_title', '')

                                if market_id:
                                    markets.append({
                                        'market_id': market_id,
                                        'title': title,
                                        'end_time': end_time,
                                        'end_time_str': end_time.strftime('%m-%d %H:%M') if end_time else '-',
                                        'is_categorical': m.get('isCategorical', False) or m.get('is_categorical', False),
                                        'volume': float(m.get('volume', 0) or 0),
                                        'slug': slug,
                                        'url': f"{cls.MARKET_URL_PREFIX}{slug}" if slug else f"{cls.MARKET_URL_PREFIX}{market_id}",
                                    })
                            if markets:
                                break
                except Exception:
                    continue
        except Exception:
            pass

        # 按到期时间排序
        markets.sort(key=lambda x: x['end_time']
                     if x['end_time'] else datetime.max)
        return markets

    @classmethod
    def get_cached_markets(cls) -> list:
        """获取缓存的市场列表（线程安全）"""
        with cls._lock:
            return cls._markets_cache.copy()  # 返回副本避免外部修改

    @classmethod
    def get_market_by_id(cls, market_id: int) -> dict:
        """根据ID获取单个市场信息（线程安全）

        Args:
            market_id: 市场ID

        Returns:
            市场信息字典，未找到返回 None
        """
        with cls._lock:
            for m in cls._markets_cache:
                if m['market_id'] == market_id:
                    return m.copy()
        return None

    @classmethod
    def get_cache_age(cls) -> float:
        """获取缓存年龄（秒）"""
        if cls._cache_time == 0:
            return float('inf')
        return time.time() - cls._cache_time

    @classmethod
    def refresh_now(cls):
        """立即刷新市场数据（同步）"""
        cls._fetch_and_update()

    @classmethod
    def is_loaded(cls) -> bool:
        """是否已加载完成"""
        return cls._loaded

    @classmethod
    def is_loading(cls) -> bool:
        """是否正在加载"""
        return cls._loading

    @classmethod
    def get_recent_markets(cls, max_count: int = 10) -> list:
        """获取最近到期的市场列表

        Args:
            max_count: 最多返回数量

        Returns:
            市场列表，每个元素包含 market_id, title, end_time_str, is_categorical, url
        """
        with cls._lock:
            if not cls._loaded:
                return []
            return cls._markets_cache[:max_count]

    @classmethod
    def display_recent_markets(cls, max_count: int = 10):
        """显示最近到期的市场列表（简洁版，用于输入市场ID时）

        Args:
            max_count: 最多显示数量
        """
        with cls._lock:
            loaded = cls._loaded
            loading = cls._loading
            markets = cls._markets_cache[:max_count] if loaded else []

        if not loaded:
            if loading:
                print("\n(市场列表加载中...)")
            else:
                print("\n(市场列表未加载)")
            return

        if not markets:
            print("\n(暂无活跃市场)")
            return

        if not markets:
            print("\n(暂无活跃市场)")
            return

        print(f"\n最近到期的市场:")
        print(f"{'─'*80}")
        print(f"  {'ID':<8} {'到期时间':<14} {'名称'}")
        print(f"{'─'*80}")

        for m in markets:
            market_id = m['market_id']
            end_time = m['end_time_str']
            title = m['title'][:50] + \
                '...' if len(m['title']) > 50 else m['title']
            cat_mark = ' [分类]' if m['is_categorical'] else ''
            print(f"  {market_id:<8} {end_time:<14} {title}{cat_mark}")
            print(f"           └─ {m['url']}")

        print(f"{'─'*80}")

    @classmethod
    def display_markets_full(cls, max_count: int = 20):
        """显示完整市场列表（详细版）

        Args:
            max_count: 最多显示数量
        """
        with cls._lock:
            loaded = cls._loaded
            loading = cls._loading
            markets = cls._markets_cache[:max_count] if loaded else []
            total_count = len(cls._markets_cache)

        if not loaded:
            if loading:
                print("\n(市场列表加载中...)")
            else:
                print("\n暂无市场数据")
            return

        if not markets:
            print("\n暂无市场数据")
            return

        print(f"\n{'='*80}")
        print(f"{'活跃市场列表':^80}")
        print(f"{'='*80}")

        for i, m in enumerate(markets, 1):
            market_id = m['market_id']
            end_time = m['end_time_str']
            title = m['title']
            url = m['url']
            volume = m['volume']
            cat_mark = '[分类市场]' if m['is_categorical'] else '[二元市场]'

            print(f"\n{i}. {title}")
            print(
                f"   ID: {market_id}  |  到期: {end_time}  |  交易量: ${volume:,.0f}  |  {cat_mark}")
            print(f"   链接: {url}")

        print(f"\n{'='*80}")
        if total_count > max_count:
            print(f"(共 {total_count} 个市场，仅显示前 {max_count} 个)")

    @classmethod
    def search_markets(cls, keyword: str) -> list:
        """搜索市场（线程安全）"""
        keyword = keyword.lower()
        with cls._lock:
            return [m.copy() for m in cls._markets_cache
                    if keyword in m['title'].lower() or keyword in str(m['market_id'])]

    @classmethod
    def get_market_url(cls, market_id: int) -> str:
        """获取市场链接"""
        m = cls.get_market_by_id(market_id)
        if m:
            return m['url']
        return f"{cls.MARKET_URL_PREFIX}{market_id}"


def handle_insufficient_balance(insufficient_list: list) -> tuple:
    """处理余额不足的选择（便捷函数）

    Args:
        insufficient_list: [(remark, balance, required), ...]

    Returns:
        (action, skip_remarks)
    """
    return UserConfirmation.handle_insufficient_balance_choice(insufficient_list)
