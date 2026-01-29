from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER, MARKET_ORDER
from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
from opinion_clob_sdk import Client
from opinion_trader.core.enhanced import (
    TradeSummary, TradeRecord, OrderCalculator,
    MergeSplitService, EnhancedOrderService, OrderInputHelper
)
from opinion_trader.services.orderbook_manager import OrderbookManager, OrderbookState, MultiTokenOrderbookManager
from opinion_trader.websocket.client import OpinionWebSocket, WebSocketMonitor
from opinion_trader.services.services import (
    OrderbookService, OrderBuilder, UserConfirmation,
    MarketInfoService, AccountIterator, PositionService,
    handle_insufficient_balance, MarketListService
)
from opinion_trader.display.display import (
    ProgressBar, TableDisplay, PositionDisplay,
    BalanceDisplay, OrderDisplay, OrderbookDisplay
)
from opinion_trader.config.models import TraderConfig, MarketMakerConfig, MarketMakerState
from opinion_trader.utils.console import (
    console, header, section, divider, menu,
    success, error, warning, info, dim,
    kv, bullet, ask, confirm,
    create_table, print_table, rule
)
import asyncio
import random
import time
import os
import sys
import threading
import requests
import json
import signal
import atexit
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime


class DaemonProcess:
    """守护进程管理类"""

    PID_FILE = "/tmp/opinion_trade.pid"
    LOG_FILE = "opinion_trade.log"

    @classmethod
    def is_running(cls) -> tuple:
        """检查是否有守护进程在运行，返回 (is_running, pid)"""
        if not os.path.exists(cls.PID_FILE):
            return False, None
        try:
            with open(cls.PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # 检查进程是否存在
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            # 进程不存在或PID无效，清理过期的PID文件
            cls._remove_pid_file()
            return False, None

    @classmethod
    def _remove_pid_file(cls):
        """删除PID文件"""
        try:
            if os.path.exists(cls.PID_FILE):
                os.remove(cls.PID_FILE)
        except:
            pass

    @classmethod
    def _write_pid_file(cls):
        """写入PID文件"""
        with open(cls.PID_FILE, 'w') as f:
            f.write(str(os.getpid()))

    @classmethod
    def stop_daemon(cls) -> bool:
        """停止守护进程"""
        running, pid = cls.is_running()
        if not running:
            print("没有运行中的守护进程")
            return False

        try:
            print(f"正在停止守护进程 (PID: {pid})...")
            os.kill(pid, signal.SIGTERM)
            # 等待进程结束
            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except OSError:
                    print("✓ 守护进程已停止")
                    cls._remove_pid_file()
                    return True
            # 强制杀死
            os.kill(pid, signal.SIGKILL)
            print("✓ 守护进程已强制停止")
            cls._remove_pid_file()
            return True
        except Exception as e:
            print(f"✗ 停止失败: {e}")
            return False

    @classmethod
    def status(cls):
        """显示守护进程状态"""
        running, pid = cls.is_running()
        if running:
            print(f"✓ 守护进程运行中 (PID: {pid})")
            print(f"  日志文件: {os.path.abspath(cls.LOG_FILE)}")
            # 显示最后几行日志
            if os.path.exists(cls.LOG_FILE):
                print("\n  最近日志:")
                try:
                    with open(cls.LOG_FILE, 'r') as f:
                        lines = f.readlines()
                        for line in lines[-10:]:
                            print(f"  {line.rstrip()}")
                except:
                    pass
        else:
            print("✗ 没有运行中的守护进程")

    @classmethod
    def daemonize(cls):
        """将当前进程转为守护进程（双fork方式）"""
        # 检查是否已有守护进程在运行
        running, pid = cls.is_running()
        if running:
            print(f"✗ 已有守护进程在运行 (PID: {pid})")
            print(f"  使用 'python trade.py stop' 停止")
            sys.exit(1)

        # 第一次fork
        try:
            pid = os.fork()
            if pid > 0:
                # 父进程退出
                print(f"✓ 守护进程已启动")
                print(f"  日志文件: {os.path.abspath(cls.LOG_FILE)}")
                print(f"  查看状态: python trade.py status")
                print(f"  停止进程: python trade.py stop")
                sys.exit(0)
        except OSError as e:
            print(f"✗ fork失败: {e}")
            sys.exit(1)

        # 创建新会话
        os.setsid()

        # 第二次fork
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.exit(1)

        # 重定向标准输入输出
        sys.stdout.flush()
        sys.stderr.flush()

        # 打开日志文件和/dev/null
        try:
            dev_null = open('/dev/null', 'r+')
            log_file = open(cls.LOG_FILE, 'a', buffering=1)

            # 重定向 - 使用文件描述符数字而非 fileno()
            os.dup2(dev_null.fileno(), 0)  # stdin
            os.dup2(log_file.fileno(), 1)  # stdout
            os.dup2(log_file.fileno(), 2)  # stderr
        except Exception as e:
            # 如果重定向失败，尝试继续运行
            pass

        # 写入PID文件
        cls._write_pid_file()

        # 注册退出时清理
        atexit.register(cls._remove_pid_file)

        # 处理终止信号
        def signal_handler(signum, frame):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 收到终止信号，正在退出...")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)


# 从拆分的模块导入


# 启动 Banner
header("Opinion.trade 自动交易程序", "v3.0.0")
console.print()
console.print("[bold]版权声明[/bold]", justify="center")
divider()
console.print("[dim]本软件受版权保护，仅授权给指定用户个人使用。[/dim]")
console.print()
console.print("[yellow]严禁以下行为：[/yellow]")
bullet("通过互联网或其他方式传播、复制、转发本软件")
bullet("出售、出租或以任何形式交易本软件")
bullet("未经授权进行以盈利为目的的二次开发")
bullet("将本软件提供给未经授权的第三方使用")
console.print()
console.print("[dim]违反上述条款将承担相应的法律责任。[/dim]")
divider()
console.print()

# Opinion CLOB SDK imports


class OpinionSDKTrader:
    """Opinion.trade SDK 自动交易策略"""

    def __init__(self, configs: List[TraderConfig]):
        self.configs = configs
        self.clients = []
        self.clients_initialized = False  # 标记clients是否已初始化

    def translate_error(self, errmsg: str) -> str:
        """翻译常见错误信息"""
        if not errmsg:
            return "未知错误"

        # 最低金额错误
        import re
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

    def check_balance_sufficient(self, client, config, required_amount: float) -> tuple:
        """检查余额是否足够
        返回: (是否足够, 可用余额)
        """
        try:
            available = self.get_usdt_balance(config)
            return (available >= required_amount, available)
        except Exception as e:
            print(f"  [!] 查询余额异常: {e}")
            return (False, 0)

    def get_account_balances(self, selected_indices: list, show_progress: bool = True) -> dict:
        """获取多个账户的余额（带进度条显示）
        返回: {acc_idx: available_balance}  注意：acc_idx 是 0-based
        """
        balances = {}
        total = len(selected_indices)
        results = []  # 缓存结果用于显示

        for i, acc_idx in enumerate(selected_indices):
            config = self.configs[acc_idx]
            if show_progress:
                ProgressBar.show_progress(
                    i, total, prefix='查询余额', suffix=f'{config.remark}')
            try:
                total_bal, available_bal, net_worth, portfolio = self.get_usdt_balance(
                    config, return_full=True)
                balances[acc_idx] = available_bal
                results.append((acc_idx, config.remark, total_bal,
                               available_bal, net_worth, portfolio, None))
            except Exception as e:
                balances[acc_idx] = 0
                results.append((acc_idx, config.remark, 0, 0, 0, 0, str(e)))

        if show_progress:
            ProgressBar.show_progress(total, total, prefix='查询余额', suffix='完成')

        # 显示查询结果
        print()
        total_balance = 0
        total_available = 0
        total_net_worth = 0
        total_portfolio = 0
        for acc_idx, remark, total_bal, available_bal, net_worth, portfolio, error in results:
            if error:
                print(f"  账户ID:{acc_idx+1}  备注:{remark}  ✗ 查询失败")
            else:
                print(
                    f"  账户ID:{acc_idx+1}  备注:{remark}  总余额:{total_bal:.2f}  可用余额:{available_bal:.2f}  持仓:{portfolio:.2f}  净资产:{net_worth:.2f}")
                total_balance += total_bal
                total_available += available_bal
                total_net_worth += net_worth
                total_portfolio += portfolio
        print(
            f"\n  总计: 总余额:{total_balance:.2f}  可用余额:{total_available:.2f}  持仓:{total_portfolio:.2f}  净资产:{total_net_worth:.2f}")

        return balances

    def _init_all_clients(self):
        """初始化所有客户端（在代理设置后调用）"""
        if self.clients_initialized:
            return

        self.clients = []
        for config in self.configs:
            client = self._create_client(config)
            self.clients.append(client)
        self.clients_initialized = True

        # 客户端初始化完成后，立即启动市场列表服务（后台加载+自动刷新）
        if self.clients:
            MarketListService.initialize(
                self.clients[0],
                auto_refresh=True,
                refresh_interval=60  # 每60秒刷新一次
            )

    def _create_client(self, config: TraderConfig) -> Client:
        """创建Opinion SDK客户端"""
        print(f"\n[初始化] 备注: {config.remark}")
        print(
            f"[初始化] EOA地址: {config.eoa_address[:10]}...{config.eoa_address[-6:]}")
        if config.proxy_address:
            print(
                f"[初始化] 代理地址: {config.proxy_address[:10]}...{config.proxy_address[-6:]}")
        else:
            print(f"[初始化] 代理地址: 未获取（将使用EOA地址）")

        # 基础配置
        # 如果没有代理地址，使用EOA地址作为备选
        multi_sig_addr = config.proxy_address if config.proxy_address else config.eoa_address

        client_params = {
            'host': 'https://proxy.opinion.trade:8443',
            'apikey': config.api_key,
            'chain_id': 56,  # BNB Chain
            'rpc_url': 'https://bsc-dataseed.binance.org',
            'private_key': config.private_key,
            'multi_sig_addr': multi_sig_addr  # 使用代理地址进行交易
        }

        # 创建Client（直连模式，不使用代理）
        client = Client(**client_params)

        return client

    def parse_account_selection(self, input_str: str, total_accounts: int) -> List[int]:
        """
        解析账户选择输入
        支持格式:
        - 留空: 返回所有账户
        - "2 9 10": 返回指定账户ID [2, 9, 10]
        - "5-15": 返回范围内账户ID [5, 6, 7, ..., 15]
        - "1-5 8 10-12": 混合格式 [1,2,3,4,5,8,10,11,12]
        - "101 102": 通过备注名选择账户
        - "1-5 101 103": 混合使用ID和备注名
        返回: 账户索引列表 (1-based)
        """
        input_str = input_str.strip()

        # 留空返回全部
        if not input_str:
            return list(range(1, total_accounts + 1))

        # 创建备注到索引的映射
        remark_to_idx = {}
        for idx, config in enumerate(self.configs, 1):
            remark_to_idx[config.remark.strip()] = idx

        selected = set()
        parts = input_str.replace(',', ' ').split()

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if '-' in part:
                # 范围格式: 5-15
                try:
                    start, end = part.split('-')
                    start = int(start)
                    end = int(end)
                    if start > end:
                        start, end = end, start
                    for i in range(start, end + 1):
                        if 1 <= i <= total_accounts:
                            selected.add(i)
                except ValueError:
                    print(f"  [!] 忽略无效输入: {part}")
            else:
                # 先尝试作为备注名匹配（优先级更高）
                if part in remark_to_idx:
                    selected.add(remark_to_idx[part])
                else:
                    # 再尝试作为数字（账户索引）
                    try:
                        num = int(part)
                        if 1 <= num <= total_accounts:
                            selected.add(num)
                        else:
                            print(
                                f"  [!] '{part}'既不是有效账户ID(1-{total_accounts})，也不是已知备注名，已忽略")
                    except ValueError:
                        # 不是数字也不是备注名
                        print(f"  [!] 备注名'{part}'不存在，已忽略")

        return sorted(list(selected))

    def prompt_market_id(self, prompt: str = "请输入市场ID") -> int:
        """提示用户输入市场ID，自动显示最近到期的市场列表

        Args:
            prompt: 提示语

        Returns:
            市场ID，返回0表示取消
        """
        # 如果市场列表还没加载完成，等待一下
        import time as _time
        wait_count = 0
        # 等待直到加载完成，或等待超时（最多5秒）
        while not MarketListService.is_loaded() and wait_count < 10:
            if wait_count == 0:
                print("\n正在获取市场列表...")
            _time.sleep(0.5)
            wait_count += 1

        # 显示最近到期的市场列表
        MarketListService.display_recent_markets(max_count=10)

        while True:
            user_input = input(f"\n{prompt} (留空返回): ").strip()

            if not user_input:
                return 0

            try:
                market_id = int(user_input)
                if market_id > 0:
                    return market_id
                print("✗ 市场ID必须大于0")
            except ValueError:
                print("✗ 请输入有效的数字")

    def split_amounts(self, total_amount: float, num_trades: int) -> List[float]:
        """拆分金额"""
        min_amount = total_amount * 0.1
        max_amount = total_amount * 0.5

        amounts = []
        remaining = total_amount

        for i in range(num_trades - 1):
            remaining_trades = num_trades - i
            max_current = min(max_amount, remaining -
                              min_amount * (remaining_trades - 1))
            min_current = max(min_amount, remaining -
                              max_amount * (remaining_trades - 1))

            amount = random.uniform(min_current, max_current)
            amount = round(amount, 2)

            amounts.append(amount)
            remaining -= amount

        amounts.append(round(remaining, 2))
        return amounts

    def get_usdt_balance(self, config, return_available=True, return_both=False, return_full=False):
        """通过API查询USDT余额

        Args:
            config: 账户配置
            return_available: True返回可用余额(扣除挂单占用)，False返回总余额
            return_both: True返回(总余额, 可用余额)元组
            return_full: True返回(总余额, 可用余额, 净资产, 持仓市值)元组
        """
        try:
            eoa_address = config.eoa_address
            profile_url = f"https://proxy.opinion.trade:8443/api/bsc/api/v2/user/{eoa_address}/profile?chainId=56"

            response = requests.get(
                profile_url,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('errno') == 0:
                    result = data.get('result', {})
                    balances = result.get('balance', [])
                    # netWorth = 净资产, portfolio = 持仓市值
                    net_worth = float(result.get('netWorth', 0) or 0)
                    portfolio = float(result.get('portfolio', 0) or 0)

                    if balances and len(balances) > 0:
                        total_balance_str = balances[0].get(
                            'totalBalance', '0')
                        available_balance_str = balances[0].get(
                            'availableBalance', total_balance_str)

                        total_balance = float(total_balance_str)
                        available_balance = float(available_balance_str)

                        if return_full:
                            return (total_balance, available_balance, net_worth, portfolio)
                        elif return_both:
                            return (total_balance, available_balance)
                        elif return_available:
                            return available_balance
                        else:
                            return total_balance
                    else:
                        if return_full:
                            return (0, 0, net_worth, portfolio)

            if return_full:
                return (0, 0, 0, 0)
            if return_both:
                return (0, 0)
            return 0
        except Exception as e:
            print(f"  [!] 查询持仓异常: {e}")
            if return_full:
                return (0, 0, 0, 0)
            if return_both:
                return (0, 0)
            return 0

    def display_account_balances(self, selected_account_indices: list, title: str = "正在检查选中账户的USDT余额...") -> dict:
        """统一的账户余额查询和显示模块（实时显示）

        Args:
            selected_account_indices: 选中的账户索引列表 (1-based)
            title: 显示标题

        Returns:
            dict: {账户索引: 可用余额} 的字典
        """
        print(f"\n{title}")

        available_amounts = {}
        total_net_worth = 0
        total_portfolio = 0

        for idx in selected_account_indices:
            config = self.configs[idx - 1]
            remark = config.remark if config.remark else "-"

            try:
                eoa_address = config.eoa_address
                profile_url = f"https://proxy.opinion.trade:8443/api/bsc/api/v2/user/{eoa_address}/profile?chainId=56"

                response = requests.get(
                    profile_url,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('errno') == 0:
                        result = data.get('result', {})
                        balances = result.get('balance', [])
                        net_worth = float(result.get('netWorth', 0) or 0)
                        portfolio = float(result.get('portfolio', 0) or 0)
                        usdt_balance = 0

                        if balances and len(balances) > 0:
                            total_balance_str = balances[0].get(
                                'totalBalance', '0')
                            available_balance_str = balances[0].get(
                                'availableBalance', total_balance_str)
                            total_balance_val = float(total_balance_str)
                            usdt_balance = float(available_balance_str)

                            # 实时显示结果
                            if total_balance_val != usdt_balance:
                                locked = total_balance_val - usdt_balance
                                print(
                                    f"  账户ID:{idx}  备注:{remark}  可用:{usdt_balance:.2f}  挂单:{locked:.2f}  持仓:{portfolio:.2f}  净资产:{net_worth:.2f}")
                            else:
                                print(
                                    f"  账户ID:{idx}  备注:{remark}  可用:{usdt_balance:.2f}  持仓:{portfolio:.2f}  净资产:{net_worth:.2f}")
                            total_net_worth += net_worth
                            total_portfolio += portfolio
                        else:
                            print(f"  账户ID:{idx}  备注:{remark}  [!] 无余额数据")

                        available_amounts[idx] = usdt_balance
                    else:
                        print(
                            f"  账户ID:{idx}  备注:{remark}  ✗ API错误: {data.get('errmsg', '未知')}")
                        available_amounts[idx] = 0
                else:
                    print(
                        f"  账户ID:{idx}  备注:{remark}  ✗ HTTP {response.status_code}")
                    available_amounts[idx] = 0

            except Exception as e:
                print(f"  账户ID:{idx}  备注:{remark}  ✗ 异常: {e}")
                available_amounts[idx] = 0

        total_balance = sum(available_amounts.values())
        print(
            f"\n✓ 总可用: {total_balance:.2f}  总持仓: {total_portfolio:.2f}  总净资产: {total_net_worth:.2f}")

        return available_amounts

    def format_price(self, price):
        """格式化价格显示（*100并去掉小数点后多余的0）"""
        # 先四舍五入到0.1分精度，避免浮点数精度问题
        price_cent = round(price * 100, 1)
        if price_cent == int(price_cent):
            return f"{int(price_cent)}"
        else:
            return f"{price_cent:.1f}"

    def get_all_positions(self, client, market_id=0):
        """获取所有持仓（自动翻页）"""
        all_positions = []
        page = 1
        limit = 100  # 每页获取100条

        while True:
            try:
                response = client.get_my_positions(
                    market_id=market_id, page=page, limit=limit)
                if response.errno != 0:
                    break

                positions = response.result.list if hasattr(
                    response.result, 'list') else []
                if not positions:
                    break

                all_positions.extend(positions)

                # 如果返回的数量小于limit，说明已经是最后一页
                if len(positions) < limit:
                    break

                page += 1
                # 防止无限循环
                if page > 100:
                    break
            except Exception as e:
                # 记录异常但继续返回已获取的数据
                print(f"  [!] 获取持仓分页异常: {e}")
                break

        return all_positions

    def get_all_orders(self, client, market_id=0, status=""):
        """获取所有挂单（自动翻页）"""
        all_orders = []
        page = 1
        limit = 100  # 每页获取100条

        while True:
            try:
                response = client.get_my_orders(
                    market_id=market_id, status=status, limit=limit, page=page)
                if response.errno != 0:
                    break

                orders = response.result.list if hasattr(
                    response.result, 'list') else []
                if not orders:
                    break

                all_orders.extend(orders)

                # 如果返回的数量小于limit，说明已经是最后一页
                if len(orders) < limit:
                    break

                page += 1
                # 防止无限循环
                if page > 100:
                    break
            except Exception as e:
                # 记录异常但继续返回已获取的数据
                print(f"  [!] 获取订单分页异常: {e}")
                break

        return all_orders

    def wait_for_position_update(self, client, token_id, initial_balance, expected_change, timeout=15):
        """等待持仓更新（买入后等持仓到账，卖出后等持仓减少）"""
        print(f"  等待持仓更新...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = client.get_my_positions()
                if response.errno == 0:
                    positions = response.result.list if hasattr(
                        response.result, 'list') else []
                    for position in positions:
                        if str(position.token_id) == str(token_id):
                            current_balance = int(
                                float(position.shares_owned if hasattr(position, 'shares_owned') else 0))

                            if expected_change > 0:  # 买入，期待增加
                                if current_balance > initial_balance:
                                    print(
                                        f"  ✓ 持仓已更新: {initial_balance} → {current_balance}")
                                    return True, current_balance
                            else:  # 卖出，期待减少
                                if current_balance < initial_balance:
                                    print(
                                        f"  ✓ 持仓已更新: {initial_balance} → {current_balance}")
                                    return True, current_balance
                            break
                time.sleep(1)
            except Exception as e:
                print(f"  [!] 查询订单簿异常: {e}")
                time.sleep(1)

        print(f"  [!]  等待超时，持仓可能未及时更新")
        return False, initial_balance

    def get_sell_prices_reference(self, client, token_id):
        """获取卖1到卖5的价格参考"""
        ob = OrderbookService.fetch(client, token_id)
        if ob['success']:
            return [(i + 1, price) for i, (price, _) in enumerate(ob['asks'][:5])]
        return []

    def execute_quick_mode(self, client, config, market_id, token_id, selected_token_name, total_trades, min_amount, max_amount):
        """执行快速模式：买卖交替"""
        print(f"\n{'='*60}")
        print(f"{'开始执行快速模式':^60}")
        print(f"{'='*60}")

        # 获取盘口数据并检查流动性
        print(f"\n正在获取盘口信息...")
        ob = OrderbookService.fetch(client, token_id)
        if not ob['success']:
            print(f"✗ 无法获取盘口数据: {ob.get('error', '')}")
            return

        if not ob['bids'] or not ob['asks']:
            print(f"✗ 买盘或卖盘为空")
            return

        bid_depth = ob['bid_depth']
        ask_depth = ob['ask_depth']

        # 显示盘口信息
        OrderbookDisplay.show(
            ob['bids'], ob['asks'],
            mode=OrderbookDisplay.MODE_WITH_DEPTH,
            max_rows=5,
            format_price_func=self.format_price
        )

        # 检查流动性
        # 快速模式：买入看卖盘深度，卖出看买盘深度
        buy_times = (total_trades + 1) // 2  # 买入次数
        max_total_buy = max_amount * buy_times

        print(f"\n盘口深度检查:")
        print(f"  预计买入次数: {buy_times}")
        print(f"  单次金额范围: ${min_amount:.2f} - ${max_amount:.2f}")
        print(f"  最大可能买入总额: ${max_total_buy:.2f}")
        print(f"  卖1盘口深度: ${ask_depth:.2f}")

        liquidity = OrderbookService.check_liquidity(
            ob, max_total_buy, side='buy')
        if not liquidity['sufficient']:
            print(f"\n[!]  警告: 买入时卖盘深度可能不足!")
            print(f"  卖盘深度: ${liquidity['available']:.2f}")
            print(f"  最大可能买入: ${liquidity['required']:.2f}")
            print(f"  缺口: ${liquidity['shortage']:.2f}")
            print(f"\n  注意: 实际金额随机，可能小于最大值")

            if not UserConfirmation.yes_no("是否继续?"):
                print("✗ 已取消")
                return
        else:
            print(f"  ✓ 卖盘深度充足")

        # 同样检查卖出时的买盘深度
        sell_times = total_trades // 2
        if sell_times > 0:
            print(f"\n  预计卖出次数: {sell_times}")
            print(f"  买1盘口深度: ${bid_depth:.2f}")
            if bid_depth < max_total_buy:
                print(f"  [!]  卖出时买盘深度可能不足")
            else:
                print(f"  ✓ 买盘深度充足")

        # 查询初始USDT余额
        current_usdt_balance = self.get_usdt_balance(config)
        print(f"\n初始账户余额: ${current_usdt_balance:.2f}")

        # 检查余额是否足够至少一次交易
        if current_usdt_balance < min_amount:
            print(f"\n✗ 余额不足!")
            print(f"  当前余额: ${current_usdt_balance:.2f}")
            print(f"  最低需要: ${min_amount:.2f}")
            print(f"  提示: 请充值或降低最低金额")
            return

        # 如果余额不够最大金额，给出警告
        if current_usdt_balance < max_amount:
            print(f"\n[!]  警告: 余额不足以支持最大金额")
            print(f"  当前余额: ${current_usdt_balance:.2f}")
            print(f"  最大金额: ${max_amount:.2f}")
            print(f"  将按实际余额进行交易")

            # 调整金额范围
            max_amount = current_usdt_balance * 0.95  # 留5%余地
            if max_amount < min_amount:
                min_amount = current_usdt_balance * 0.8
            print(f"  调整后范围: ${min_amount:.2f} - ${max_amount:.2f}")

        # 查询初始持仓
        initial_position = 0
        try:
            positions_response = client.get_my_positions()
            if positions_response.errno == 0:
                positions = positions_response.result.list if hasattr(
                    positions_response.result, 'list') else []
                for position in positions:
                    if str(position.token_id) == str(token_id):
                        initial_position = int(
                            float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
                        break
            print(f"初始持仓: {initial_position} tokens")
        except Exception as e:
            print(f"[!]  无法查询初始持仓: {e}")

        # 开始交易循环
        completed_trades = 0  # 实际完成的交易次数
        i = 1
        while completed_trades < total_trades:
            print(f"\n{'─'*60}")
            print(f"第{i}次尝试 (已完成{completed_trades}/{total_trades})")
            print(f"{'─'*60}")

            # 判断是买还是卖
            if completed_trades % 2 == 0:  # 偶数次完成（0,2,4...）：下一步买入
                # 随机生成本次金额
                amount = random.uniform(min_amount, max_amount)
                amount = round(amount, 2)

                print(f"\n【买入】金额: ${amount}")

                # 查询买入前的持仓
                try:
                    positions_response = client.get_my_positions()
                    if positions_response.errno == 0:
                        positions = positions_response.result.list if hasattr(
                            positions_response.result, 'list') else []
                        before_buy_position = 0
                        for position in positions:
                            if str(position.token_id) == str(token_id):
                                before_buy_position = int(
                                    float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
                                break
                        print(f"  买入前持仓: {before_buy_position} tokens")
                    else:
                        print(f"  [!]  无法查询买入前持仓")
                        before_buy_position = initial_position
                except Exception as e:
                    print(f"  [!]  查询买入前持仓异常: {e}")
                    before_buy_position = initial_position

                # 获取卖1价格
                try:
                    ob = OrderbookService.fetch(client, token_id)
                    if not ob['success'] or not ob['asks']:
                        print(f"  ✗ 无法获取盘口数据，重试...")
                        i += 1
                        time.sleep(2)
                        continue

                    price = ob['ask1_price']
                    print(f"  使用价格: {self.format_price(price)}¢ (卖1)")

                    # 执行买入（限价单）
                    order_data = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.BUY,
                        orderType=LIMIT_ORDER,
                        price=f"{price:.6f}",
                        makerAmountInQuoteToken=round(amount, 2)
                    )

                    response = client.place_order(
                        order_data, check_approval=True)

                    if response.errno == 0:
                        print(f"  ✓ 买入订单提交成功")

                        # 等待持仓到账
                        success, new_position = self.wait_for_position_update(
                            client, token_id, before_buy_position, expected_change=1
                        )

                        # 如果wait函数返回成功，直接使用
                        if success:
                            initial_position = new_position
                            completed_trades += 1
                            print(
                                f"  ✓ 买入完成，持仓: {before_buy_position} → {new_position} tokens")
                        else:
                            # wait超时，再查一次确认
                            print(f"  等待超时，再次查询确认...")
                            time.sleep(2)
                            try:
                                positions_response = client.get_my_positions()
                                if positions_response.errno == 0:
                                    positions = positions_response.result.list if hasattr(
                                        positions_response.result, 'list') else []
                                    final_position = 0
                                    for position in positions:
                                        if str(position.token_id) == str(token_id):
                                            final_position = int(
                                                float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
                                            break

                                    # 只要持仓增加了，就算成功
                                    if final_position > before_buy_position:
                                        print(
                                            f"  ✓ 确认成功！持仓已增加: {before_buy_position} → {final_position} tokens")
                                        initial_position = final_position
                                        completed_trades += 1
                                    else:
                                        print(
                                            f"  ✗ 持仓未增加 (仍为{final_position})，可能未成交，重试...")
                                        i += 1
                                        time.sleep(2)
                                        continue
                                else:
                                    print(f"  ✗ 无法确认持仓，重试...")
                                    i += 1
                                    time.sleep(2)
                                    continue
                            except Exception as e:
                                print(f"  ✗ 查询异常: {e}，重试...")
                                i += 1
                                time.sleep(2)
                                continue
                    elif response.errno == 10207:
                        print(f"  ✗ 余额不足错误")
                        try:
                            available = float(response.errmsg.split(
                                'only ')[1].split(' available')[0])
                            print(f"  实际可用: ${available:.2f}")
                            print(f"  需要金额: ${amount:.2f}")
                        except Exception as e:
                            print(f"  余额解析异常: {e}")
                            print(f"  错误信息: {response.errmsg}")
                        print(f"  提示: 请降低单次交易金额或充值")
                        return
                    elif response.errno == 10403:
                        print(f"  ✗ 地区限制错误: 你的IP地址不支持，请更换IP")
                        print(f"  提示: 检查SOCKS5代理配置是否正确，或更换非受限地区的代理")
                        return
                    else:
                        print(f"  ✗ 买入失败: errno={response.errno}")
                        if hasattr(response, 'errmsg'):
                            print(f"  错误信息: {response.errmsg}")
                        i += 1
                        time.sleep(2)
                        continue

                except Exception as e:
                    error_msg = str(e)
                    if "Missing dependencies for SOCKS" in error_msg or "SOCKS" in error_msg:
                        print(f"  ✗ SOCKS代理错误: {e}")
                        print(f"  提示: 请运行 'pip install pysocks' 安装SOCKS支持")
                        print(f"  或在配置文件中移除SOCKS5代理配置")
                        return
                    else:
                        print(f"  ✗ 买入异常: {e}")
                        i += 1
                        time.sleep(2)
                        continue

            else:  # 奇数次完成（1,3,5...）：下一步卖出
                print(f"\n【卖出】")

                # 查询当前持仓
                try:
                    current_position = PositionService.get_token_balance(
                        client, token_id)
                    if current_position <= 0:
                        print(f"  [!]  当前无持仓，重试...")
                        i += 1
                        time.sleep(2)
                        continue

                    print(f"  当前持仓: {current_position} tokens")

                    # 获取买1价格
                    ob = OrderbookService.fetch(client, token_id)
                    if not ob['success'] or not ob['bids']:
                        print(f"  ✗ 无法获取盘口数据，重试...")
                        i += 1
                        time.sleep(2)
                        continue

                    price = ob['bid1_price']
                    print(f"  使用价格: {self.format_price(price)}¢ (买1)")

                    # 执行卖出（限价单，全仓）
                    order_data = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.SELL,
                        orderType=LIMIT_ORDER,
                        price=f"{price:.6f}",
                        makerAmountInBaseToken=current_position
                    )

                    response = client.place_order(
                        order_data, check_approval=True)

                    if response.errno == 0:
                        print(f"  ✓ 卖出订单提交成功")

                        # 等待持仓减少
                        print(f"  等待持仓更新...")
                        time.sleep(3)

                        # 查询持仓是否减少
                        try:
                            positions_response = client.get_my_positions()
                            if positions_response.errno == 0:
                                positions = positions_response.result.list if hasattr(
                                    positions_response.result, 'list') else []
                                new_position = 0
                                for position in positions:
                                    if str(position.token_id) == str(token_id):
                                        new_position = int(
                                            float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
                                        break

                                if new_position < current_position:
                                    print(
                                        f"  ✓ 持仓已减少: {current_position} → {new_position} tokens")
                                    initial_position = new_position
                                    completed_trades += 1

                                    # 等待资金到账（轮询查询余额）
                                    print(f"  等待资金到账...")
                                    start_time = time.time()
                                    while time.time() - start_time < 12:
                                        new_balance = self.get_usdt_balance(
                                            config)
                                        if new_balance > current_usdt_balance:
                                            print(
                                                f"  ✓ 资金已到账: ${current_usdt_balance:.2f} → ${new_balance:.2f}")
                                            current_usdt_balance = new_balance
                                            break
                                        time.sleep(1)

                                    print(f"  ✓ 卖出完成")
                                else:
                                    print(
                                        f"  [!]  持仓未减少 (仍为{new_position})，订单可能未成交，重试...")
                                    i += 1
                                    time.sleep(2)
                                    continue
                            else:
                                print(f"  ✗ 无法确认持仓，重试...")
                                i += 1
                                time.sleep(2)
                                continue
                        except Exception as e:
                            print(f"  ✗ 查询异常: {e}，重试...")
                            i += 1
                            time.sleep(2)
                            continue
                    elif response.errno == 10403:
                        print(f"  ✗ 地区限制错误: 你的IP地址不支持，请更换IP")
                        print(f"  提示: 检查SOCKS5代理配置是否正确，或更换非受限地区的代理")
                        return
                    else:
                        print(f"  ✗ 卖出失败: errno={response.errno}")
                        if hasattr(response, 'errmsg'):
                            print(f"  错误信息: {response.errmsg}")
                        i += 1
                        time.sleep(2)
                        continue

                except Exception as e:
                    error_msg = str(e)
                    if "Missing dependencies for SOCKS" in error_msg or "SOCKS" in error_msg:
                        print(f"  ✗ SOCKS代理错误: {e}")
                        print(f"  提示: 请运行 'pip install pysocks' 安装SOCKS支持")
                        print(f"  或在配置文件中移除SOCKS5代理配置")
                        return
                    elif "504" in error_msg or "Gateway Time-out" in error_msg:
                        print(f"  [!] 卖出: 网关超时(504)，订单可能已提交，请稍后检查")
                    elif "502" in error_msg or "Bad Gateway" in error_msg:
                        print(f"  [!] 卖出: 网关错误(502)，请稍后重试")
                    elif "503" in error_msg or "Service Unavailable" in error_msg:
                        print(f"  [!] 卖出: 服务暂时不可用(503)，请稍后重试")
                    elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        print(f"  [!] 卖出: 请求超时，请检查网络连接")
                    elif "Connection" in error_msg:
                        print(f"  [!] 卖出: 连接失败，请检查网络或代理")
                    else:
                        print(f"  ✗ 卖出异常: {e}")
                    i += 1
                    time.sleep(2)
                    continue

            i += 1
            # 短暂延迟
            time.sleep(1)

        # 最后一次如果是奇数，询问是否挂单
        if total_trades % 2 == 1:
            print(f"\n{'─'*60}")
            print("最后一次是买入，是否挂单卖出？")
            print(f"{'─'*60}")

            if UserConfirmation.yes_no("是否挂单?"):
                # 查询当前持仓
                current_position = PositionService.get_token_balance(
                    client, token_id)
                if current_position > 0:
                    # 显示卖1-卖5价格
                    sell_prices = self.get_sell_prices_reference(
                        client, token_id)
                    if sell_prices:
                        print(f"\n当前盘口（卖盘）:")
                        for num, price in sell_prices:
                            print(f"  卖{num}: {price:.6f}")

                        print(f"\n请选择挂单价格:")
                        print(f"  1-5: 使用卖1到卖5的价格")
                        print(f"  0: 自定义价格")

                        price_choice = input("请输入选项: ").strip()

                        if price_choice in ['1', '2', '3', '4', '5']:
                            idx = int(price_choice) - 1
                            if idx < len(sell_prices):
                                sell_price = sell_prices[idx][1]
                            else:
                                print(f"[!]  选择超出范围，使用卖1")
                                sell_price = sell_prices[0][1]
                        elif price_choice == '0':
                            custom_price = input("请输入自定义价格: ").strip()
                            try:
                                sell_price = float(custom_price)
                            except Exception:
                                print(f"✗ 无效价格")
                                return
                        else:
                            print(f"✗ 无效选择")
                            return

                        # 执行挂单
                        print(
                            f"\n挂单卖出 {current_position} tokens @ {sell_price:.6f}")
                        order_data = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.SELL,
                            orderType=LIMIT_ORDER,
                            price=f"{sell_price:.6f}",
                            makerAmountInBaseToken=current_position
                        )

                        response = client.place_order(
                            order_data, check_approval=True)

                        if response.errno == 0:
                            print(f"✓ 挂单成功")
                        elif response.errno == 10403:
                            print(f"✗ 地区限制错误: 你的IP地址不支持，请更换IP")
                            print(f"提示: 检查SOCKS5代理配置是否正确，或更换非受限地区的代理")
                        else:
                            print(f"✗ 挂单失败: errno={response.errno}")
                else:
                    print(f"[!]  当前无持仓")

        print(f"\n{'='*60}")
        print(f"{'快速模式执行完成':^60}")
        print(f"{'='*60}")

    def execute_low_loss_mode(self, client, config, market_id, token_id, selected_token_name, total_trades, min_amount, max_amount):
        """执行低损耗模式：先买后挂单"""
        print(f"\n{'='*60}")
        print(f"{'开始执行低损耗模式':^60}")
        print(f"{'='*60}")

        # 计算买入次数和卖出次数
        buy_count = total_trades // 2
        sell_count = total_trades // 2

        print(f"\n将执行: {buy_count}次买入 + {sell_count}次挂卖")

        # 获取盘口数据并检查流动性
        print(f"\n正在获取盘口信息...")
        ob = OrderbookService.fetch(client, token_id)
        if not ob['success']:
            print(f"✗ 无法获取盘口数据: {ob.get('error', '')}")
            return

        if not ob['bids'] or not ob['asks']:
            print(f"✗ 买盘或卖盘为空")
            return

        ask_depth = ob['ask_depth']

        # 显示盘口信息
        OrderbookDisplay.show(
            ob['bids'], ob['asks'],
            mode=OrderbookDisplay.MODE_WITH_DEPTH,
            max_rows=5,
            format_price_func=self.format_price
        )

        # 检查流动性
        max_total_buy = max_amount * buy_count

        print(f"\n盘口深度检查:")
        print(f"  买入次数: {buy_count}")
        print(f"  单次金额范围: ${min_amount:.2f} - ${max_amount:.2f}")
        print(f"  最大可能买入总额: ${max_total_buy:.2f}")
        print(f"  卖1盘口深度: ${ask_depth:.2f}")

        liquidity = OrderbookService.check_liquidity(
            ob, max_total_buy, side='buy')
        if not liquidity['sufficient']:
            print(f"\n[!]  警告: 买入时卖盘深度可能不足!")
            print(f"  卖盘深度: ${liquidity['available']:.2f}")
            print(f"  最大可能买入: ${liquidity['required']:.2f}")
            print(f"  缺口: ${liquidity['shortage']:.2f}")
            print(f"\n  注意: 实际金额随机，可能小于最大值")

            if not UserConfirmation.yes_no("是否继续?"):
                print("✗ 已取消")
                return
        else:
            print(f"  ✓ 卖盘深度充足")

        # 查询初始USDT余额
        current_usdt_balance = self.get_usdt_balance(config)
        print(f"\n初始账户余额: ${current_usdt_balance:.2f}")

        # 查询初始持仓
        initial_position = PositionService.get_token_balance(client, token_id)
        print(f"初始持仓: {initial_position} tokens\n")

        # 记录每次买入的金额（用于后续挂单）
        buy_amounts = []

        # 第一阶段：买入
        print(f"{'='*60}")
        print(f"第一阶段：执行{buy_count}次买入")
        print(f"{'='*60}")

        for i in range(1, buy_count + 1):
            print(f"\n【买入 {i}/{buy_count}】")

            # 每次重新随机金额
            amount = random.uniform(min_amount, max_amount)
            amount = round(amount, 2)
            buy_amounts.append(amount)

            print(f"  金额: ${amount}")

            # 获取卖1价格
            try:
                ob = OrderbookService.fetch(client, token_id)
                if not ob['success'] or not ob['asks']:
                    print(f"  ✗ 无法获取盘口数据")
                    continue

                price = ob['ask1_price']
                print(f"  价格: {self.format_price(price)}¢ (卖1)")

                # 执行买入（限价单）
                order_data = PlaceOrderDataInput(
                    marketId=market_id,
                    tokenId=token_id,
                    side=OrderSide.BUY,
                    orderType=LIMIT_ORDER,
                    price=f"{price:.6f}",
                    makerAmountInQuoteToken=round(amount, 2)
                )

                response = client.place_order(order_data, check_approval=True)

                if response.errno == 0:
                    print(f"  ✓ 买入成功")
                elif response.errno == 10403:
                    print(f"  ✗ 地区限制错误: 你的IP地址不支持，请更换IP")
                    print(f"  提示: 检查SOCKS5代理配置是否正确，或更换非受限地区的代理")
                    return
                else:
                    print(f"  ✗ 买入失败: errno={response.errno}")
                    if hasattr(response, 'errmsg'):
                        print(f"  错误信息: {response.errmsg}")

            except Exception as e:
                error_msg = str(e)
                if "Missing dependencies for SOCKS" in error_msg or "SOCKS" in error_msg:
                    print(f"  ✗ SOCKS代理错误: {e}")
                    print(f"  提示: 请运行 'pip install pysocks' 安装SOCKS支持")
                    print(f"  或在配置文件中移除SOCKS5代理配置")
                    return
                else:
                    print(f"  ✗ 买入异常: {e}")

            # 短暂延迟
            time.sleep(1)

        # 等待所有买入完成
        print(f"\n等待持仓到账...")
        time.sleep(15)

        # 查询当前总持仓
        total_position = PositionService.get_token_balance(client, token_id)
        print(f"✓ 当前总持仓: {total_position} tokens")

        if total_position <= 0:
            print(f"[!]  当前无持仓，无法挂卖")
            return

        # 第二阶段：挂单卖出
        print(f"\n{'='*60}")
        print(f"第二阶段：执行{sell_count}次挂卖")
        print(f"{'='*60}")

        # 显示卖1-卖5价格参考
        sell_prices = self.get_sell_prices_reference(client, token_id)
        if sell_prices:
            print(f"\n当前盘口（卖盘）:")
            for num, price in sell_prices:
                print(f"  卖{num}: {price:.6f}")

        remaining_position = total_position

        for i in range(1, sell_count + 1):
            print(f"\n【挂卖 {i}/{sell_count}】")

            # 计算本次挂单数量
            if i < sell_count:
                # 前N-1次：按照对应的买入金额计算
                # 假设价格不变，shares ≈ amount / price
                # 为简化，直接按比例分配
                ratio = buy_amounts[i-1] / sum(buy_amounts)
                sell_shares = int(total_position * ratio)
            else:
                # 最后一次：剩余全部
                sell_shares = remaining_position

            if sell_shares <= 0:
                print(f"  [!]  无可卖数量，跳过")
                continue

            print(f"  数量: {sell_shares} tokens")

            # 用户选择挂单价格
            print(f"\n请选择挂单价格:")
            print(f"  1-5: 使用卖1到卖5的价格")
            print(f"  0: 自定义价格")

            price_choice = input("请输入选项: ").strip()

            if price_choice in ['1', '2', '3', '4', '5']:
                idx = int(price_choice) - 1
                if sell_prices and idx < len(sell_prices):
                    sell_price = sell_prices[idx][1]
                elif sell_prices:
                    print(f"  [!]  选择超出范围，使用卖1")
                    sell_price = sell_prices[0][1]
                else:
                    print(f"  ✗ 无法获取盘口价格")
                    continue
            elif price_choice == '0':
                custom_price = input("  请输入自定义价格: ").strip()
                try:
                    sell_price = float(custom_price)
                except Exception:
                    print(f"  ✗ 无效价格，跳过")
                    continue
            else:
                print(f"  ✗ 无效选择，跳过")
                continue

            print(f"  价格: {sell_price:.6f}")

            # 执行挂单
            try:
                order_data = PlaceOrderDataInput(
                    marketId=market_id,
                    tokenId=token_id,
                    side=OrderSide.SELL,
                    orderType=LIMIT_ORDER,
                    price=f"{sell_price:.6f}",
                    makerAmountInBaseToken=sell_shares
                )

                response = client.place_order(order_data, check_approval=True)

                if response.errno == 0:
                    print(f"  ✓ 挂单成功")
                    remaining_position -= sell_shares
                elif response.errno == 10403:
                    print(f"  ✗ 地区限制错误: 你的IP地址不支持，请更换IP")
                    print(f"  提示: 检查SOCKS5代理配置是否正确，或更换非受限地区的代理")
                    return
                else:
                    print(f"  ✗ 挂单失败: errno={response.errno}")
                    if hasattr(response, 'errmsg'):
                        print(f"  错误信息: {response.errmsg}")

            except Exception as e:
                error_msg = str(e)
                if "Missing dependencies for SOCKS" in error_msg or "SOCKS" in error_msg:
                    print(f"  ✗ SOCKS代理错误: {e}")
                    print(f"  提示: 请运行 'pip install pysocks' 安装SOCKS支持")
                    print(f"  或在配置文件中移除SOCKS5代理配置")
                    return
                else:
                    print(f"  ✗ 挂单异常: {e}")

            # 短暂延迟
            time.sleep(1)

        print(f"\n{'='*60}")
        print(f"{'低损耗模式执行完成':^60}")
        print(f"{'='*60}")

    def query_account_assets(self):
        """查询账户资产详情"""
        print(f"\n{'='*60}")
        print(f"{'查询账户资产详情':^60}")
        print(f"{'='*60}")

        total_position_value = 0
        total_balance = 0
        total_net_worth = 0

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            print(f"\n{'─'*60}")
            print(f"{config.remark}")
            print(f"{'─'*60}")

            try:
                # 1. 查询余额
                balance = self.get_usdt_balance(config)

                # 2. 查询持仓总市值
                position_value = 0
                positions = self.get_all_positions(client)
                for position in positions:
                    try:
                        current_value = float(position.current_value_in_quote_token if hasattr(
                            position, 'current_value_in_quote_token') and position.current_value_in_quote_token else 0)
                        position_value += current_value
                    except (ValueError, TypeError, AttributeError):
                        continue

                # 3. 计算净资产
                net_worth = position_value + balance

                # 显示
                print(f"  持仓: ${position_value:.2f}")
                print(f"  余额: ${balance:.2f}")
                print(f"  净资产: ${net_worth:.2f}")

                # 累加总计
                total_position_value += position_value
                total_balance += balance
                total_net_worth += net_worth

            except Exception as e:
                print(f"  ✗ 查询异常: {e}")

        # 显示汇总
        print(f"\n{'='*60}")
        print(f"{'[#] 全部账户汇总':^60}")
        print(f"{'='*60}")
        print(f"  总持仓: ${total_position_value:.2f}")
        print(f"  总余额: ${total_balance:.2f}")
        print(f"  总净资产: ${total_net_worth:.2f}")
        print(f"{'='*60}")

    def query_positions(self):
        """查询TOKEN持仓"""
        print(f"\n{'='*60}")
        print(f"{'查询TOKEN持仓':^60}")
        print(f"{'='*60}")
        print("  1. 查询所有持仓")
        print("  2. 查询指定市场持仓")
        print("  0. 返回主菜单")

        choice = input("\n请选择 (0-2): ").strip()

        if choice == '0' or not choice:
            return
        elif choice == '1':
            self.query_all_positions()
        elif choice == '2':
            self.query_market_positions()
        else:
            print("✗ 无效选择")

    def query_all_positions(self):
        """查询所有持仓"""
        print(f"\n{'='*60}")
        print(f"{'查询所有账户的所有持仓':^60}")
        print(f"{'='*60}")

        # 汇总统计
        total_value = 0
        total_cost = 0

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            try:
                print(f"\n{'─'*60}")
                print(f"{config.remark}")
                print(f"{'─'*60}")

                positions = self.get_all_positions(client)

                if not positions:
                    print("  无持仓")
                    continue

                # 过滤有持仓的并解析数据
                parsed_positions = []
                for p in positions:
                    if int(float(p.shares_owned if hasattr(p, 'shares_owned') else 0)) > 0:
                        parsed = PositionDisplay.parse_sdk_position(p)
                        if parsed:
                            parsed_positions.append(parsed)

                if not parsed_positions:
                    print("  无持仓")
                    continue

                # 使用统一模块显示
                account_value, account_cost, _ = PositionDisplay.show_positions_table(
                    parsed_positions, title=None, show_summary=True, indent=2
                )

                total_value += account_value
                total_cost += account_cost

            except Exception as e:
                print(f"  ✗ 查询异常: {e}")

        # 显示总汇总
        if total_value > 0 or total_cost > 0:
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost *
                             100) if total_cost > 0 else 0
            print(f"\n{'='*60}")
            print(f"[#] 全部账户汇总:")
            print(f"   总市值: ${total_value:.2f}")
            print(f"   总成本: ${total_cost:.2f}")
            print(
                f"   总盈亏: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} ({'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.1f}%)")
            print(f"{'='*60}")

    def query_market_positions(self):
        """查询指定市场持仓 - 按账户分组显示"""
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 获取市场信息
        try:
            client = self.clients[0]

            # 使用 MarketInfoService 获取分类市场信息
            market_result = MarketInfoService.get_all_child_markets_info(
                client, market_id, include_prices=True)

            if market_result['success']:
                # 这是一个分类市场
                print(f"\n✓ 找到分类市场: {market_result['title']}")
                child_info = market_result['children']
                print(f"  包含 {len(child_info)} 个子市场")

                # 总计
                grand_total_value = 0
                grand_total_cost = 0

                # 按账户遍历
                for idx, (acc_client, config) in enumerate(zip(self.clients, self.configs), 1):
                    print(f"\n{'─'*60}")
                    print(f"{config.remark}")
                    print(f"{'─'*60}")

                    try:
                        positions = self.get_all_positions(acc_client)

                        # 收集该账户在此分类市场下的所有持仓
                        account_positions = []

                        for position in positions:
                            try:
                                token_id = str(position.token_id)
                                shares = int(float(position.shares_owned if hasattr(
                                    position, 'shares_owned') else 0))

                                if shares <= 0:
                                    continue

                                # 查找匹配的子市场
                                for child_market_id, info in child_info.items():
                                    if token_id == info['yes_token_id'] or token_id == info['no_token_id']:
                                        side = 'Yes' if token_id == info['yes_token_id'] else 'No'
                                        price = info['yes_price'] if side == 'Yes' else info['no_price']

                                        current_value = float(position.current_value_in_quote_token if hasattr(
                                            position, 'current_value_in_quote_token') and position.current_value_in_quote_token else 0)
                                        pnl = float(position.unrealized_pnl if hasattr(
                                            position, 'unrealized_pnl') and position.unrealized_pnl else 0)
                                        cost = current_value - pnl

                                        account_positions.append({
                                            'child_market_id': child_market_id,
                                            'child_title': info['title'][:16],
                                            'side': side,
                                            'shares': shares,
                                            'price': price,
                                            'value': current_value,
                                            'cost': cost,
                                            'pnl': pnl
                                        })
                                        break
                            except (ValueError, TypeError, AttributeError):
                                continue

                        if not account_positions:
                            print("  无持仓")
                            continue

                        # 转换为统一格式并显示
                        display_positions = []
                        for pos in account_positions:
                            current_price = pos['value'] / \
                                pos['shares'] if pos['shares'] > 0 else 0
                            display_positions.append({
                                'root_market_id': pos['child_market_id'],
                                'market_title': pos['child_title'],
                                'side': pos['side'],
                                'shares': pos['shares'],
                                'current_price': current_price,
                                'current_value': pos['value'],
                                'cost': pos['cost'],
                                'pnl': pos['pnl']
                            })
                        account_value, account_cost, _ = PositionDisplay.show_positions_table(
                            display_positions, title=None, show_summary=True, indent=2
                        )
                        grand_total_value += account_value
                        grand_total_cost += account_cost

                    except Exception as e:
                        print(f"  ✗ 查询异常: {e}")

                # 显示总计
                if grand_total_value > 0 or grand_total_cost > 0:
                    grand_total_pnl = grand_total_value - grand_total_cost
                    total_pnl_pct = (
                        grand_total_pnl / grand_total_cost * 100) if grand_total_cost > 0 else 0
                    print(f"\n{'='*60}")
                    print(f"[#] 全部账户汇总:")
                    print(f"   总市值: ${grand_total_value:.2f}")
                    print(f"   总成本: ${grand_total_cost:.2f}")
                    print(
                        f"   总盈亏: {'+' if grand_total_pnl >= 0 else ''}{grand_total_pnl:.2f} ({'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.1f}%)")
                    print(f"{'='*60}")

            else:
                # 不是分类市场，作为普通市场处理
                market_info = MarketInfoService.get_market_info(
                    client, market_id)
                if not market_info['success'] or not market_info['yes_token_id']:
                    error_msg = market_info.get('error', '未知错误')
                    print(f"✗ {error_msg}")
                    return

                print(f"\n市场: {market_info['title']}")

                yes_token_id = market_info['yes_token_id']
                no_token_id = market_info['no_token_id']

                # 总计
                total_value = 0
                total_cost = 0

                # 按账户遍历
                for idx, (acc_client, config) in enumerate(zip(self.clients, self.configs), 1):
                    print(f"\n{'─'*60}")
                    print(f"{config.remark}")
                    print(f"{'─'*60}")

                    try:
                        positions = self.get_all_positions(acc_client)

                        # 查找该市场的持仓
                        account_positions = []

                        for position in positions:
                            try:
                                token_id = str(position.token_id)
                                shares = int(float(position.shares_owned if hasattr(
                                    position, 'shares_owned') else 0))

                                if shares <= 0:
                                    continue

                                if token_id == yes_token_id or token_id == no_token_id:
                                    side = 'Yes' if token_id == yes_token_id else 'No'

                                    current_value = float(position.current_value_in_quote_token if hasattr(
                                        position, 'current_value_in_quote_token') and position.current_value_in_quote_token else 0)
                                    pnl = float(position.unrealized_pnl if hasattr(
                                        position, 'unrealized_pnl') and position.unrealized_pnl else 0)
                                    cost = current_value - pnl

                                    account_positions.append({
                                        'side': side,
                                        'shares': shares,
                                        'value': current_value,
                                        'cost': cost,
                                        'pnl': pnl
                                    })
                            except (ValueError, TypeError, AttributeError):
                                continue

                        if not account_positions:
                            print("  无持仓")
                            continue

                        # 转换为统一格式并显示
                        display_positions = []
                        for pos in account_positions:
                            current_price = pos['value'] / \
                                pos['shares'] if pos['shares'] > 0 else 0
                            display_positions.append({
                                'side': pos['side'],
                                'shares': pos['shares'],
                                'current_price': current_price,
                                'current_value': pos['value'],
                                'cost': pos['cost'],
                                'pnl': pos['pnl']
                            })
                        PositionDisplay.show_simple_positions_table(
                            display_positions, indent=2)

                        # 计算账户汇总
                        account_value = sum(p['value']
                                            for p in account_positions)
                        account_cost = sum(p['cost']
                                           for p in account_positions)
                        if account_value > 0 or account_cost > 0:
                            account_pnl = account_value - account_cost
                            pnl_pct = (account_pnl / account_cost *
                                       100) if account_cost > 0 else 0
                            print(
                                f"  💰 账户汇总: 市值 ${account_value:.2f} | 成本 ${account_cost:.2f} | 盈亏 {'+' if account_pnl >= 0 else ''}{account_pnl:.2f} ({'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%)")

                        total_value += account_value
                        total_cost += account_cost

                    except Exception as e:
                        print(f"  ✗ 查询异常: {e}")

                # 显示总计
                if total_value > 0 or total_cost > 0:
                    total_pnl = total_value - total_cost
                    pnl_pct = (total_pnl / total_cost *
                               100) if total_cost > 0 else 0
                    print(f"\n{'='*60}")
                    print(f"[#] 全部账户汇总:")
                    print(f"   总市值: ${total_value:.2f}")
                    print(f"   总成本: ${total_cost:.2f}")
                    print(
                        f"   总盈亏: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} ({'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%)")
                    print(f"{'='*60}")

        except Exception as e:
            print(f"✗ 查询异常: {e}")

    def query_open_orders(self):
        """查询所有挂单"""
        print(f"\n{'='*60}")
        print(f"{'查询所有挂单':^60}")
        print(f"{'='*60}")

        market_id_input = input("\n请输入市场ID (留空查询所有市场): ").strip()
        market_id_filter = int(market_id_input) if market_id_input else None

        # 如果指定了市场ID，检查是否为分类市场
        target_market_ids = []
        child_market_names = {}  # {子市场ID: 子市场名称}
        parent_market_id = None
        is_categorical = False

        if market_id_filter:
            client = self.clients[0]
            try:
                categorical_response = client.get_categorical_market(
                    market_id=market_id_filter)
                if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                    market_data = categorical_response.result.data
                    print(f"\n✓ 找到分类市场: {market_data.market_title}")
                    parent_market_id = market_id_filter
                    is_categorical = True
                    if hasattr(market_data, 'child_markets') and market_data.child_markets:
                        for child in market_data.child_markets:
                            target_market_ids.append(child.market_id)
                            child_market_names[child.market_id] = child.market_title
                        print(f"  包含 {len(target_market_ids)} 个子市场")
                    else:
                        target_market_ids = [market_id_filter]
                else:
                    target_market_ids = [market_id_filter]
            except Exception:
                target_market_ids = [market_id_filter]

        print(f"\n正在查询所有账户的挂单...")

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            try:
                print(f"\n{'─'*60}")
                print(f"{config.remark}")
                print(f"{'─'*60}")

                orders = self.get_all_orders(client)

                # 过滤未完成的订单
                pending_orders = [o for o in orders if hasattr(
                    o, 'status') and o.status == 1]

                # 如果指定了市场ID，进一步过滤（支持分类市场）
                if target_market_ids:
                    pending_orders = [o for o in pending_orders if hasattr(
                        o, 'market_id') and o.market_id in target_market_ids]

                if not pending_orders:
                    print("  无挂单")
                    continue

                # 解析挂单数据并使用统一模块显示
                parsed_orders = [OrderDisplay.parse_sdk_order(
                    o) for o in pending_orders]
                parsed_orders = [o for o in parsed_orders if o]  # 过滤None
                OrderDisplay.show_orders_table(
                    parsed_orders, indent=2, format_price_func=self.format_price)

            except Exception as e:
                print(f"✗ {config.remark} 查询异常: {e}")

    def _execute_sell_for_market(self, market_id: int, selected_account_indices: list,
                                 market_title: str = None, cached_positions: list = None):
        """执行指定市场的卖出（仅卖出模式专用）

        Args:
            market_id: 市场ID
            selected_account_indices: 选中的账户索引列表
            market_title: 市场标题（可选，避免重复查询）
            cached_positions: 已查询的持仓信息（可选，避免重复查询）
        """
        print(f"\n{'='*60}")
        print(f"{'卖出指定市场持仓':^60}")
        print(f"{'='*60}")

        # 获取市场信息（如果没有传入）
        if not market_title:
            client = self.clients[0]
            market_response = client.get_market(market_id=market_id)
            if market_response.errno != 0 or not market_response.result or not market_response.result.data:
                print(f"✗ 无法获取市场信息")
                return
            market_data = market_response.result.data
            market_title = market_data.market_title if hasattr(
                market_data, 'market_title') else f"市场{market_id}"

        print(f"\n市场: {market_title}")
        print(f"市场ID: {market_id}")

        # 如果有缓存的持仓信息，直接使用缓存（已包含挂单占用信息）
        if cached_positions:
            positions_to_sell = []
            total_available = 0

            for pos_info in cached_positions:
                idx = pos_info['idx']
                if idx not in selected_account_indices:
                    continue

                client = pos_info.get('client') or self.clients[idx - 1]
                config = pos_info.get('config') or self.configs[idx - 1]
                remark = config.remark if hasattr(
                    config, 'remark') else f"账户{idx}"
                shares = pos_info['shares']
                side = pos_info['side']
                token_id = pos_info.get('token_id')
                available = pos_info.get('available', shares)
                pending_amount = pos_info.get('pending', 0)

                if available <= 0:
                    continue

                positions_to_sell.append({
                    'idx': idx,
                    'client': client,
                    'config': config,
                    'token_id': token_id,
                    'side': side,
                    'shares': shares,
                    'available': available,
                    'pending': pending_amount
                })

                # 显示持仓信息
                if pending_amount > 0:
                    print(
                        f"  账户ID:{idx}  {remark}: {side} 可用{available}份 (总{shares}, 挂单占用{pending_amount})")
                else:
                    print(f"  账户ID:{idx}  {remark}: {side} 可用{available}份")
                total_available += available

        else:
            # 没有缓存，完整查询持仓
            print(f"\n查询持仓:")
            positions_to_sell = []
            total_available = 0

            for idx in selected_account_indices:
                client = self.clients[idx - 1]
                config = self.configs[idx - 1]
                remark = config.remark if hasattr(
                    config, 'remark') else f"账户{idx}"

                try:
                    positions = self.get_all_positions(
                        client, market_id=market_id)

                    for position in positions:
                        shares = int(float(position.shares_owned if hasattr(
                            position, 'shares_owned') else 0))
                        if shares <= 0:
                            continue

                        token_id = position.token_id if hasattr(
                            position, 'token_id') else None
                        side = position.outcome_side_enum if hasattr(
                            position, 'outcome_side_enum') else 'N/A'

                        # 查询挂单占用
                        pending_amount = 0
                        try:
                            orders = self.get_all_orders(client)
                            for order in orders:
                                order_market_id = order.market_id if hasattr(
                                    order, 'market_id') else None
                                order_outcome_side = order.outcome_side if hasattr(
                                    order, 'outcome_side') else None
                                order_side = order.side if hasattr(
                                    order, 'side') else None
                                order_status = order.status if hasattr(
                                    order, 'status') else None

                                pos_outcome_side = 1 if side == 'Yes' else 2
                                if (order_market_id == market_id and
                                    order_outcome_side == pos_outcome_side and
                                        order_side == 2 and order_status == 1):
                                    order_shares = float(order.order_shares if hasattr(
                                        order, 'order_shares') else 0)
                                    filled_shares = float(order.filled_shares if hasattr(
                                        order, 'filled_shares') else 0)
                                    pending_amount += int(order_shares -
                                                          filled_shares)
                        except Exception:
                            pass

                        available = shares - pending_amount
                        if available <= 0:
                            continue

                        positions_to_sell.append({
                            'idx': idx,
                            'client': client,
                            'config': config,
                            'token_id': token_id,
                            'side': side,
                            'shares': shares,
                            'available': available,
                            'pending': pending_amount
                        })

                        # 实时显示
                        if pending_amount > 0:
                            print(
                                f"  账户ID:{idx}  {remark}: {side} 可用{available}份 (总{shares}, 挂单{pending_amount})")
                        else:
                            print(
                                f"  账户ID:{idx}  {remark}: {side} 可用{available}份")
                        total_available += available

                except Exception as e:
                    print(f"  账户ID:{idx}  {remark}: [!] 查询异常: {e}")

        if not positions_to_sell:
            print(f"\n✗ 选中账户在市场 {market_id} 无可卖持仓")
            return

        print(f"\n✓ 找到 {len(positions_to_sell)} 个持仓，总计 {total_available} 份")

        # 获取盘口数据（用于分层挂单配置）
        # 优先使用持仓的token_id，否则从市场信息获取
        first_token_id = positions_to_sell[0]['token_id']
        first_side = positions_to_sell[0]['side']

        # 如果持仓没有token_id，从市场信息获取
        if not first_token_id:
            try:
                market_response = self.clients[0].get_market(
                    market_id=market_id)
                if market_response.errno == 0 and market_response.result and market_response.result.data:
                    market_data = market_response.result.data
                    if first_side == 'Yes':
                        first_token_id = market_data.yes_token_id if hasattr(
                            market_data, 'yes_token_id') else None
                    else:
                        first_token_id = market_data.no_token_id if hasattr(
                            market_data, 'no_token_id') else None
            except Exception:
                pass

        bid_details = []
        ask_details = []
        orderbook_error = None
        if not first_token_id:
            orderbook_error = "无法获取 token_id (持仓和市场信息都没有)"
        else:
            try:
                orderbook = self.clients[0].get_orderbook(
                    token_id=first_token_id)
                if orderbook.errno != 0:
                    orderbook_error = f"API错误: {orderbook.errmsg if hasattr(orderbook, 'errmsg') else orderbook.errno}"
                elif not orderbook.result:
                    orderbook_error = "API返回空结果"
                else:
                    if orderbook.result.bids:
                        bids = sorted(orderbook.result.bids,
                                      key=lambda x: float(x.price), reverse=True)
                        bid_cumulative = 0
                        for i, bid in enumerate(bids[:10]):
                            price = float(bid.price)
                            size = int(float(bid.size))
                            bid_cumulative += price * size
                            bid_details.append(
                                (i + 1, price, size, bid_cumulative))
                    if orderbook.result.asks:
                        asks = sorted(orderbook.result.asks,
                                      key=lambda x: float(x.price))
                        ask_cumulative = 0
                        for i, ask in enumerate(asks[:10]):
                            price = float(ask.price)
                            size = int(float(ask.size))
                            ask_cumulative += price * size
                            ask_details.append(
                                (i + 1, price, size, ask_cumulative))
            except Exception as e:
                orderbook_error = f"获取异常: {e}"

        # 选择卖出策略
        print("\n卖出策略:")
        print("  1. 限价单 (单档价格)")
        print("  2. 市价单 (立即成交)")
        print("  3. 分层挂单 (多档价格分散)")
        sell_strategy = input("请选择 (1/2/3): ").strip()

        layered_config = None
        use_market_order = False

        if sell_strategy == '3':
            # 分层挂单模式
            if not bid_details and not ask_details:
                print(
                    f"[!] 无盘口数据，无法使用分层挂单 ({orderbook_error or '盘口为空'})，自动切换为市价单")
                use_market_order = True
            else:
                layered_config = self._configure_layered_order(
                    'sell', bid_details, ask_details, self.format_price)
                if not layered_config:
                    print("[!] 分层配置取消，自动切换为市价单")
                    use_market_order = True
        elif sell_strategy == '2':
            use_market_order = True
        elif sell_strategy != '1':
            print("✗ 无效选择")
            return

        # 如果是限价单，询问价格选择
        use_bid_price = False
        if not use_market_order and not layered_config:
            print("\n限价单价格选择:")
            print("  1. 买1价格（直接成交）")
            print("  2. 卖1价格（挂单等待）")
            price_choice = input("请选择 (1/2): ").strip()
            use_bid_price = (price_choice == '1')

        # 确认
        if layered_config:
            method_name = "分层挂单"
        elif use_market_order:
            method_name = "市价单（立即成交）"
        else:
            method_name = "买1价格（直接成交）" if use_bid_price else "卖1价格（挂单等待）"

        print(f"\n卖出方式: {method_name}")
        confirm = input(f"确认卖出? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("✗ 已取消")
            return

        # 执行卖出
        print(f"\n{'='*60}")
        print(f"{'开始执行卖出':^60}")
        print(f"{'='*60}")

        success_count = 0
        fail_count = 0

        for pos in positions_to_sell:
            client = pos['client']
            config = pos['config']
            token_id = pos['token_id']
            available = pos['available']
            side = pos['side']
            remark = config.remark if hasattr(
                config, 'remark') else f"账户{pos['idx']}"

            print(f"\n{remark} - {side}: 卖出 {available} 份")

            try:
                # 分层挂单模式
                if layered_config:
                    layered_result = self._execute_layered_order(
                        client, market_id, token_id, 'sell',
                        layered_config, total_shares=available
                    )
                    print(
                        f"  分层卖出完成: 成功{layered_result['success']}笔, 失败{layered_result['failed']}笔")
                    success_count += layered_result['success']
                    fail_count += layered_result['failed']
                    continue

                # 获取当前价格
                orderbook = client.get_orderbook(token_id=token_id)
                if orderbook.errno != 0:
                    print(f"  ✗ 获取盘口失败")
                    fail_count += 1
                    continue

                if use_market_order:
                    # 市价单：使用买1价格
                    bids = sorted(orderbook.result.bids, key=lambda x: float(
                        x.price), reverse=True) if orderbook.result.bids else []
                    if not bids:
                        print(f"  ✗ 无买盘，无法成交")
                        fail_count += 1
                        continue
                    price = float(bids[0].price)
                elif use_bid_price:
                    bids = sorted(orderbook.result.bids, key=lambda x: float(
                        x.price), reverse=True) if orderbook.result.bids else []
                    if not bids:
                        print(f"  ✗ 无买盘，无法直接成交")
                        fail_count += 1
                        continue
                    price = float(bids[0].price)
                else:
                    asks = sorted(orderbook.result.asks, key=lambda x: float(
                        x.price)) if orderbook.result.asks else []
                    if asks:
                        price = float(asks[0].price)
                    else:
                        bids = sorted(orderbook.result.bids, key=lambda x: float(
                            x.price), reverse=True) if orderbook.result.bids else []
                        if bids:
                            bid1_price = float(bids[0].price)
                            print(f"  [!] 无卖盘，无法挂单等待")
                            print(
                                f"     买1价格: {self.format_price(bid1_price)}¢ (立即成交)")
                            use_bid = input(
                                f"     是否改用买1价格立即成交? (y/n): ").strip().lower()
                            if use_bid == 'y':
                                price = bid1_price
                                print(
                                    f"  ✓ 改用买1价格: {self.format_price(price)}¢")
                            else:
                                print(f"  ✗ 跳过此持仓")
                                fail_count += 1
                                continue
                        else:
                            print(f"  ✗ 无卖盘也无买盘，跳过此持仓")
                            fail_count += 1
                            continue

                print(f"  价格: {self.format_price(price)}¢")

                # 执行卖出
                order_data = PlaceOrderDataInput(
                    marketId=market_id,
                    tokenId=token_id,
                    side=OrderSide.SELL,
                    orderType=LIMIT_ORDER,
                    price=f"{price:.6f}",
                    makerAmountInBaseToken=int(available)
                )
                result = client.place_order(order_data, check_approval=True)

                if result.errno == 0:
                    print(f"  ✓ 卖出成功")
                    success_count += 1
                else:
                    print(
                        f"  ✗ 卖出失败: {result.errmsg if hasattr(result, 'errmsg') else result.errno}")
                    fail_count += 1

            except Exception as e:
                print(f"  ✗ 异常: {e}")
                fail_count += 1

            time.sleep(0.3)

        # 汇总
        print(f"\n{'='*60}")
        print(f"执行完成: 成功 {success_count}, 失败 {fail_count}")
        print(f"{'='*60}")

    def sell_all_positions(self):
        """卖出所有持仓（一键清仓）"""
        print(f"\n{'='*60}")
        print(f"{'卖出所有持仓（一键清仓）':^60}")
        print(f"{'='*60}")

        # 选择卖出方式
        print("\n卖出方式选择:")
        print("  1. 买1价格（直接成交）")
        print("  2. 卖1价格（挂单等待）")
        sell_method = input("请选择 (1/2): ").strip()

        if sell_method not in ['1', '2']:
            print("✗ 无效选择")
            return

        use_bid_price = (sell_method == '1')  # 买1价格直接成交
        method_name = "买1价格（直接成交）" if use_bid_price else "卖1价格（挂单等待）"

        # 收集所有账户的所有持仓（实时显示）
        print(f"\n查询持仓:")
        all_positions_data = []
        total_available = 0

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            remark = config.remark if hasattr(config, 'remark') else f"账户{idx}"
            try:
                positions = self.get_all_positions(client)

                for position in positions:
                    try:
                        shares = int(float(position.shares_owned if hasattr(
                            position, 'shares_owned') else 0))
                        if shares <= 0:
                            continue

                        token_id = position.token_id if hasattr(
                            position, 'token_id') else None
                        market_id = position.market_id if hasattr(
                            position, 'market_id') else None
                        root_market_id = position.root_market_id if hasattr(
                            position, 'root_market_id') and position.root_market_id else market_id
                        market_title = position.market_title if hasattr(
                            position, 'market_title') else ''
                        side = position.outcome_side_enum if hasattr(
                            position, 'outcome_side_enum') else 'N/A'

                        # 查询挂单占用
                        pending_amount = 0
                        try:
                            orders = self.get_all_orders(client)
                            for order in orders:
                                order_market_id = order.market_id if hasattr(
                                    order, 'market_id') else None
                                order_outcome_side = order.outcome_side if hasattr(
                                    order, 'outcome_side') else None
                                order_side = order.side if hasattr(
                                    order, 'side') else None
                                order_status = order.status if hasattr(
                                    order, 'status') else None

                                pos_outcome_side = 1 if side == 'Yes' else 2
                                if (order_market_id == market_id and
                                    order_outcome_side == pos_outcome_side and
                                        order_side == 2 and order_status == 1):
                                    order_shares = float(order.order_shares if hasattr(
                                        order, 'order_shares') else 0)
                                    filled_shares = float(order.filled_shares if hasattr(
                                        order, 'filled_shares') else 0)
                                    pending_amount += int(order_shares -
                                                          filled_shares)
                        except Exception:
                            pass

                        available = shares - pending_amount
                        if available <= 0:
                            continue

                        # 构建显示名称
                        if root_market_id != market_id and market_title:
                            display_name = f"{root_market_id}#{market_title[:12]}"
                        else:
                            display_name = f"{market_id}#{side}"

                        all_positions_data.append({
                            'client': client,
                            'config': config,
                            'token_id': token_id,
                            'market_id': market_id,
                            'side': side,
                            'shares': shares,
                            'available': available,
                            'pending': pending_amount,
                            'display_name': display_name
                        })

                        # 实时显示
                        if pending_amount > 0:
                            print(
                                f"  {remark}: {display_name} {side} 可用{available} (总{shares}, 挂单{pending_amount})")
                        else:
                            print(
                                f"  {remark}: {display_name} {side} 可用{available}")
                        total_available += available

                    except Exception:
                        continue

            except Exception as e:
                print(f"  {remark}: [!] 查询异常 - {e}")

        if not all_positions_data:
            print("\n✗ 所有账户均无可卖持仓")
            return

        print(
            f"\n✓ 找到 {len(all_positions_data)} 个持仓，总计 {total_available} tokens")
        print(f"卖出方式: {method_name}")

        # 确认
        confirm = input(f"\n确认卖出所有持仓? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("✗ 已取消")
            return

        # 执行卖出
        print(f"\n{'='*60}")
        print(f"{'开始执行卖出':^60}")
        print(f"{'='*60}")

        success_count = 0
        fail_count = 0

        for pos in all_positions_data:
            client = pos['client']
            config = pos['config']
            token_id = pos['token_id']
            available = pos['available']
            display_name = pos['display_name']
            side = pos['side']

            print(
                f"\n{config.remark} - {display_name} {side}: 卖出 {available} tokens")

            try:
                # 获取当前价格
                orderbook = client.get_orderbook(token_id=token_id)
                if orderbook.errno != 0:
                    print(f"  ✗ 获取盘口失败")
                    fail_count += 1
                    continue

                if use_bid_price:
                    # 买1价格
                    bids = sorted(orderbook.result.bids, key=lambda x: float(
                        x.price), reverse=True) if orderbook.result.bids else []
                    if not bids:
                        print(f"  ✗ 无买盘，无法直接成交")
                        fail_count += 1
                        continue
                    price = float(bids[0].price)
                else:
                    # 卖1价格（挂单等待）
                    asks = sorted(orderbook.result.asks, key=lambda x: float(
                        x.price)) if orderbook.result.asks else []
                    if asks:
                        price = float(asks[0].price)
                    else:
                        # 无卖盘，询问用户是否改用买1价格
                        bids = sorted(orderbook.result.bids, key=lambda x: float(
                            x.price), reverse=True) if orderbook.result.bids else []
                        if bids:
                            bid1_price = float(bids[0].price)
                            print(f"  [!] 无卖盘，无法挂单等待")
                            print(
                                f"     买1价格: {self.format_price(bid1_price)}¢ (立即成交)")
                            use_bid = input(
                                f"     是否改用买1价格立即成交? (y/n): ").strip().lower()
                            if use_bid == 'y':
                                price = bid1_price
                                print(
                                    f"  ✓ 改用买1价格: {self.format_price(price)}¢")
                            else:
                                print(f"  ✗ 跳过此持仓")
                                fail_count += 1
                                continue
                        else:
                            print(f"  ✗ 无卖盘也无买盘，跳过此持仓")
                            fail_count += 1
                            continue

                print(f"  价格: {self.format_price(price)}¢")

                # 执行卖出
                market_id = pos['market_id']
                order_data = PlaceOrderDataInput(
                    marketId=market_id,
                    tokenId=token_id,
                    side=OrderSide.SELL,
                    orderType=LIMIT_ORDER,
                    price=f"{price:.6f}",
                    makerAmountInBaseToken=int(available)
                )
                result = client.place_order(order_data, check_approval=True)

                if result.errno == 0:
                    print(f"  ✓ 卖出成功")
                    success_count += 1
                else:
                    print(
                        f"  ✗ 卖出失败: {result.errmsg if hasattr(result, 'errmsg') else result.errno}")
                    fail_count += 1

            except Exception as e:
                print(f"  ✗ 异常: {e}")
                fail_count += 1

            # 短暂延迟避免请求过快
            time.sleep(0.3)

        # 汇总
        print(f"\n{'='*60}")
        print(f"执行完成: 成功 {success_count}, 失败 {fail_count}")
        print(f"{'='*60}")

    def cancel_orders_menu(self):
        """撤单菜单"""
        print(f"\n{'='*60}")
        print(f"{'撤销挂单':^60}")
        print(f"{'='*60}")
        print("  1. 撤销所有挂单")
        print("  2. 撤销指定市场的挂单")
        print("  3. 撤销指定订单ID")
        print("  0. 返回主菜单")

        cancel_choice = input("\n请选择 (0-3): ").strip()

        if cancel_choice == '0':
            return
        elif cancel_choice == '1':
            self.cancel_all_orders()
        elif cancel_choice == '2':
            self.cancel_market_orders()
        elif cancel_choice == '3':
            self.cancel_specific_order()
        else:
            print("✗ 无效选择")

    def cancel_all_orders(self):
        """撤销所有挂单"""
        print(f"\n[!]  警告: 将撤销所有账户的所有挂单！")
        confirm = input("确认请输入 'yes': ").strip().lower()

        if confirm != 'yes':
            print("✗ 已取消")
            return

        print(f"\n正在撤销所有挂单...")

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            try:
                print(f"\n{config.remark}")

                # 获取所有挂单
                orders_response = client.get_my_orders()

                if orders_response.errno != 0:
                    print(f"  ✗ 获取订单失败")
                    continue

                orders = orders_response.result.list if hasattr(
                    orders_response.result, 'list') else []
                pending_orders = [o for o in orders if hasattr(
                    o, 'status') and o.status == 1]

                if not pending_orders:
                    print(f"  无挂单")
                    continue

                # 撤销每个订单
                cancelled = 0
                for order in pending_orders:
                    order_id = order.order_id if hasattr(
                        order, 'order_id') else None
                    if order_id:
                        try:
                            cancel_response = client.cancel_order(order_id)
                            if cancel_response.errno == 0:
                                cancelled += 1
                                print(f"  ✓ 撤销订单: {order_id}")
                            else:
                                print(
                                    f"  ✗ 撤销失败 {order_id}: errno={cancel_response.errno}")
                        except Exception as e:
                            print(f"  ✗ 撤销异常 {order_id}: {e}")

                print(f"  撤销完成: {cancelled}/{len(pending_orders)}")

            except Exception as e:
                print(f"  ✗ {config.remark} 异常: {e}")

        print(f"\n✓ 所有账户撤单完成")

    def cancel_market_orders(self):
        """撤销指定市场的挂单"""
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 检查是否为分类市场
        client = self.clients[0]
        child_market_ids = []

        try:
            # 尝试作为分类市场获取
            categorical_response = client.get_categorical_market(
                market_id=market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                # 这是一个分类市场，获取所有子市场ID
                market_data = categorical_response.result.data
                print(f"\n✓ 找到分类市场: {market_data.market_title}")

                if hasattr(market_data, 'child_markets') and market_data.child_markets:
                    child_market_ids = [
                        child.market_id for child in market_data.child_markets]
                    print(f"  包含 {len(child_market_ids)} 个子市场")
                    for child in market_data.child_markets:
                        print(
                            f"    - {child.market_title} (ID: {child.market_id})")
        except Exception:
            pass

        # 如果不是分类市场或没有子市场，就只撤销当前市场
        if not child_market_ids:
            target_market_ids = [market_id]
            print(f"\n[!]  警告: 将撤销所有账户在市场{market_id}的挂单！")
        else:
            target_market_ids = child_market_ids
            print(f"\n[!]  警告: 将撤销所有账户在市场{market_id}及其所有子市场的挂单！")

        confirm = input("确认请输入 'yes': ").strip().lower()

        if confirm != 'yes':
            print("✗ 已取消")
            return

        print(f"\n正在撤销挂单...")

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            try:
                print(f"\n{config.remark}")

                # 获取所有挂单
                orders_response = client.get_my_orders()

                if orders_response.errno != 0:
                    print(f"  ✗ 获取订单失败")
                    continue

                orders = orders_response.result.list if hasattr(
                    orders_response.result, 'list') else []

                # 过滤目标市场的未完成订单
                market_orders = [o for o in orders
                                 if hasattr(o, 'status') and o.status == 1
                                 and hasattr(o, 'market_id') and o.market_id in target_market_ids]

                if not market_orders:
                    print(f"  无挂单")
                    continue

                # 按市场ID分组显示
                from collections import defaultdict
                orders_by_market = defaultdict(list)
                for order in market_orders:
                    orders_by_market[order.market_id].append(order)

                # 撤销每个订单
                cancelled = 0
                for mid, orders_in_market in orders_by_market.items():
                    print(f"  市场{mid}: {len(orders_in_market)}个挂单")
                    for order in orders_in_market:
                        order_id = order.order_id if hasattr(
                            order, 'order_id') else None
                        if order_id:
                            try:
                                cancel_response = client.cancel_order(order_id)
                                if cancel_response.errno == 0:
                                    cancelled += 1
                                    print(f"    ✓ 撤销订单: {order_id}")
                                else:
                                    print(
                                        f"    ✗ 撤销失败 {order_id}: errno={cancel_response.errno}")
                            except Exception as e:
                                print(f"    ✗ 撤销异常 {order_id}: {e}")

                print(f"  撤销完成: {cancelled}/{len(market_orders)}")

            except Exception as e:
                print(f"  ✗ {config.remark} 异常: {e}")

        print(f"\n✓ 所有账户撤单完成")

    def cancel_specific_order(self):
        """撤销指定订单 - 先选账户，再从挂单列表中选择"""
        # 第一步：选择账户
        print(f"\n请选择账户:")
        for idx, config in enumerate(self.configs, 1):
            print(f"  {idx}. {config.remark}")
        print(f"  留空返回")

        account_choice = input(f"\n请选择 (1-{len(self.configs)}，留空返回): ").strip()

        if not account_choice:
            return

        try:
            account_idx = int(account_choice)
            if account_idx < 1 or account_idx > len(self.clients):
                print("✗ 无效的账户选择")
                return
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        client = self.clients[account_idx - 1]
        config = self.configs[account_idx - 1]

        # 第二步：查询该账户的挂单
        print(f"\n正在查询 {config.remark} 的挂单...")

        try:
            orders_response = client.get_my_orders()

            if orders_response.errno != 0:
                print(f"✗ 获取订单失败: errno={orders_response.errno}")
                return

            orders = orders_response.result.list if hasattr(
                orders_response.result, 'list') else []
            pending_orders = [o for o in orders if hasattr(
                o, 'status') and o.status == 1]

            if not pending_orders:
                print(f"✓ 该账户没有挂单")
                return

            # 第三步：显示挂单列表
            print(f"\n{config.remark} 的挂单列表:")
            print(f"{'─'*80}")
            print(
                f"  {'序号':<4} {'订单ID':<12} {'方向':<6} {'价格(¢)':<10} {'数量':<12} {'金额($)':<10} {'市场ID':<10}")
            print(f"{'─'*80}")

            for i, order in enumerate(pending_orders, 1):
                order_id = order.order_id if hasattr(
                    order, 'order_id') else 'N/A'
                side = 'YES' if (hasattr(order, 'side')
                                 and order.side == 1) else 'NO'
                price = float(order.price) if hasattr(order, 'price') else 0
                size = float(order.original_size) if hasattr(
                    order, 'original_size') else 0
                amount = price * size / 100  # 价格是美分，转换为美元
                market_id = order.market_id if hasattr(
                    order, 'market_id') else 'N/A'

                print(
                    f"  {i:<4} {order_id:<12} {side:<6} {price:<10.1f} {size:<12.2f} {amount:<10.2f} {market_id:<10}")

            print(f"{'─'*80}")
            print(f"  0. 撤销全部挂单 ({len(pending_orders)}个)")
            print(f"  留空返回")

            # 第四步：选择要撤销的订单
            order_choice = input(
                f"\n请选择要撤销的订单 (1-{len(pending_orders)}，0=全部，留空返回): ").strip()

            if not order_choice:
                return

            if order_choice == '0':
                # 撤销全部
                confirm = input(
                    f"\n确认撤销全部 {len(pending_orders)} 个挂单? (y/n): ").strip().lower()
                if confirm != 'y':
                    print("✗ 已取消")
                    return

                print(f"\n正在撤销全部挂单...")
                cancelled = 0
                for order in pending_orders:
                    order_id = order.order_id if hasattr(
                        order, 'order_id') else None
                    if order_id:
                        try:
                            cancel_response = client.cancel_order(order_id)
                            if cancel_response.errno == 0:
                                cancelled += 1
                                print(f"  ✓ 撤销订单: {order_id}")
                            else:
                                print(
                                    f"  ✗ 撤销失败 {order_id}: errno={cancel_response.errno}")
                        except Exception as e:
                            print(f"  ✗ 撤销异常 {order_id}: {e}")

                print(f"\n✓ 撤销完成: {cancelled}/{len(pending_orders)}")
            else:
                # 撤销指定订单
                try:
                    order_idx = int(order_choice)
                    if order_idx < 1 or order_idx > len(pending_orders):
                        print("✗ 无效的选择")
                        return
                except ValueError:
                    print("✗ 请输入有效的数字")
                    return

                selected_order = pending_orders[order_idx - 1]
                order_id = selected_order.order_id if hasattr(
                    selected_order, 'order_id') else None

                if not order_id:
                    print("✗ 无法获取订单ID")
                    return

                print(f"\n正在撤销订单 {order_id}...")

                cancel_response = client.cancel_order(order_id)

                if cancel_response.errno == 0:
                    print(f"✓ 撤销成功")
                else:
                    print(f"✗ 撤销失败: errno={cancel_response.errno}")
                    if hasattr(cancel_response, 'errmsg'):
                        print(f"  错误信息: {cancel_response.errmsg}")

        except Exception as e:
            print(f"✗ 操作异常: {e}")

    def claim_menu(self):
        """Claim菜单 - 领取已结算市场的收益"""
        print(f"\n{'='*60}")
        print(f"{'Claim - 领取已结算市场收益':^60}")
        print(f"{'='*60}")
        print("  1. 自动扫描并Claim所有可领取的市场")
        print("  2. 指定市场ID进行Claim")
        print("  0. 返回主菜单")

        claim_choice = input("\n请选择 (0-2): ").strip()

        if claim_choice == '0':
            return
        elif claim_choice == '1':
            self.claim_all_resolved()
        elif claim_choice == '2':
            self.claim_specific_market()
        else:
            print("✗ 无效选择")

    def claim_all_resolved(self):
        """自动扫描并Claim所有可领取的市场"""
        print(f"\n{'='*60}")
        print(f"{'扫描所有账户的可Claim持仓':^60}")
        print(f"{'='*60}")

        # 统计信息
        total_claimed = 0
        total_failed = 0
        total_skipped = 0

        for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
            print(f"\n{config.remark}")
            print(f"{'─'*40}")

            try:
                # 获取所有持仓
                positions_response = client.get_my_positions()

                if positions_response.errno != 0:
                    print(f"  ✗ 获取持仓失败: errno={positions_response.errno}")
                    continue

                positions = positions_response.result.list if hasattr(
                    positions_response.result, 'list') else []

                if not positions:
                    print(f"  无持仓")
                    continue

                # 筛选可claim的持仓（已结算的市场）
                claimable_markets = {}  # {market_id: market_title}

                for pos in positions:
                    market_id = pos.market_id if hasattr(
                        pos, 'market_id') else None
                    market_status = pos.market_status if hasattr(
                        pos, 'market_status') else None
                    shares = float(pos.shares_owned) if hasattr(
                        pos, 'shares_owned') else 0

                    # status=4 表示已结算(RESOLVED)，且有持仓
                    # TopicStatusResolving=3, TopicStatusResolved=4
                    if market_id and market_status == 4 and shares > 0:
                        market_title = pos.market_title if hasattr(
                            pos, 'market_title') else f"市场{market_id}"
                        if market_id not in claimable_markets:
                            claimable_markets[market_id] = market_title

                if not claimable_markets:
                    print(f"  无可Claim的持仓")
                    total_skipped += 1
                    continue

                print(f"  找到 {len(claimable_markets)} 个可Claim的市场:")
                for mid, title in claimable_markets.items():
                    print(f"    [{mid}] {title[:40]}...")

                # 执行claim（带重试机制）
                for market_id, market_title in claimable_markets.items():
                    max_retries = 3
                    retry_delay = 3  # 秒
                    success = False

                    for attempt in range(max_retries):
                        try:
                            if attempt == 0:
                                print(f"  正在Claim市场 {market_id}...", end=" ")
                            else:
                                print(f"  重试第{attempt}次...", end=" ")

                            tx_hash, safe_tx_hash, return_value = client.redeem(
                                market_id=market_id)

                            if tx_hash:
                                print(f"✓ 成功 (tx: {tx_hash[:16]}...)")
                                total_claimed += 1
                            else:
                                print(f"✓ 成功")
                                total_claimed += 1
                            success = True
                            break  # 成功则跳出重试循环

                        except Exception as e:
                            error_msg = str(e)
                            if 'NoPositionsToRedeem' in error_msg or 'no positions' in error_msg.lower():
                                print(f"⊘ 无可领取 (可能已领取)")
                                total_skipped += 1
                                success = True  # 标记为已处理
                                break
                            elif attempt < max_retries - 1:
                                # 还有重试机会
                                print(f"✗ 失败，{retry_delay}秒后重试...")
                                if error_msg:
                                    print(f"    错误: {error_msg[:80]}")
                                time.sleep(retry_delay)
                                retry_delay *= 2  # 指数退避
                            else:
                                # 最后一次重试也失败
                                print(f"✗ 失败 (已重试{max_retries}次)")
                                if error_msg:
                                    print(f"    错误: {error_msg[:80]}")
                                total_failed += 1

                    # 延迟，避免请求过快
                    if success:
                        time.sleep(2)

            except Exception as e:
                print(f"  ✗ 账户异常: {e}")
                total_failed += 1

        # 汇总
        print(f"\n{'='*60}")
        print(f"Claim完成统计:")
        print(f"  ✓ 成功: {total_claimed}")
        print(f"  ⊘ 跳过: {total_skipped}")
        print(f"  ✗ 失败: {total_failed}")
        print(f"{'='*60}")

    def claim_specific_market(self):
        """指定市场ID进行Claim"""
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 选择账户
        print(f"\n请选择要Claim的账户:")
        for idx, config in enumerate(self.configs, 1):
            print(f"  {idx}. {config.remark}")
        print(f"  0. 所有账户")
        print(f"  留空返回")

        account_choice = input(f"\n请选择 (0-{len(self.configs)}，留空返回): ").strip()

        if not account_choice:
            return

        if account_choice == '0':
            # 所有账户
            selected_indices = list(range(1, len(self.clients) + 1))
        else:
            try:
                idx = int(account_choice)
                if idx < 1 or idx > len(self.clients):
                    print("✗ 无效的账户选择")
                    return
                selected_indices = [idx]
            except ValueError:
                print("✗ 请输入有效的数字")
                return

        # 确认
        print(f"\n将对 {len(selected_indices)} 个账户执行市场 {market_id} 的Claim")
        confirm = input("确认请输入 'yes': ").strip().lower()
        if confirm != 'yes':
            print("✗ 已取消")
            return

        # 执行claim（带重试机制）
        print(f"\n开始Claim...")
        success_count = 0
        fail_count = 0

        for idx in selected_indices:
            client = self.clients[idx - 1]
            config = self.configs[idx - 1]

            max_retries = 3
            retry_delay = 3  # 秒
            claimed = False

            for attempt in range(max_retries):
                try:
                    if attempt == 0:
                        print(f"\n{config.remark}", end=" ")
                    else:
                        print(f"  重试第{attempt}次...", end=" ")

                    tx_hash, safe_tx_hash, return_value = client.redeem(
                        market_id=market_id)

                    if tx_hash:
                        print(f"✓ 成功 (tx: {tx_hash[:16]}...)")
                    else:
                        print(f"✓ 成功")
                    success_count += 1
                    claimed = True
                    break  # 成功则跳出重试循环

                except Exception as e:
                    error_msg = str(e)
                    if 'NoPositionsToRedeem' in error_msg or 'no positions' in error_msg.lower():
                        print(f"⊘ 无可领取")
                        claimed = True  # 标记为已处理
                        break
                    elif 'non-resolved' in error_msg.lower():
                        print(f"✗ 市场未结算")
                        fail_count += 1
                        break  # 市场未结算无需重试
                    elif attempt < max_retries - 1:
                        # 还有重试机会
                        print(f"✗ 失败，{retry_delay}秒后重试...")
                        if error_msg:
                            print(f"    错误: {error_msg[:80]}")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        # 最后一次重试也失败
                        print(f"✗ 失败 (已重试{max_retries}次)")
                        if error_msg:
                            print(f"    错误: {error_msg[:80]}")
                        fail_count += 1

            if claimed:
                time.sleep(1)

        print(f"\n{'='*60}")
        print(f"Claim完成: 成功 {success_count}, 失败 {fail_count}")
        print(f"{'='*60}")

    def execute_quick_mode_multi(self, market_id, token_id, selected_token_name, total_trades, min_amount, max_amount, selected_account_indices=None):
        """快速模式多账户版本：所有账户先买后卖

        Args:
            selected_account_indices: 选中的账户索引列表 (1-based)，如果为None则使用所有账户
        """
        # 如果没有指定账户列表，使用所有账户
        if selected_account_indices is None:
            selected_account_indices = list(range(1, len(self.clients) + 1))

        print(f"\n{'='*60}")
        print(f"快速模式 - 多账户串行执行")
        print(f"账户数量: {len(selected_account_indices)}")
        print(f"{'='*60}")

        # total_trades表示交易次数，每次交易包含买入+卖出
        buy_count = total_trades   # 买入次数 = 交易次数
        sell_count = total_trades  # 卖出次数 = 交易次数

        print(f"\n策略: 所有账户先买{buy_count}次 → 等待持仓 → 再卖{sell_count}次")

        import threading

        # ============ 第一阶段：所有账户执行所有买入 ============
        print(f"\n{'='*60}")
        print(f"第一阶段：执行 {buy_count} 次买入")
        print(f"{'='*60}")

        for buy_round in range(1, buy_count + 1):
            print(f"\n--- 第{buy_round}轮买入 ---")

            def buy_for_account(account_idx, client, config):
                try:
                    # 使用统一的金额范围
                    amount = random.uniform(min_amount, max_amount)
                    amount = round(amount, 2)

                    print(f"[{config.remark}] 买入 ${amount}")

                    # 查询买入前持仓
                    before_position = 0
                    try:
                        pos_resp = client.get_my_positions()
                        if pos_resp.errno == 0:
                            for pos in pos_resp.result.list:
                                if str(pos.token_id) == str(token_id):
                                    before_position = int(
                                        float(pos.shares_owned))
                                    break
                    except Exception:
                        pass

                    # 获取卖1价格
                    try:
                        ob_resp = client.get_orderbook(token_id=token_id)
                        if ob_resp.errno != 0:
                            print(f"[{config.remark}] ✗ 无法获取盘口")
                            return

                        asks = sorted(ob_resp.result.asks, key=lambda x: float(
                            x.price)) if ob_resp.result.asks else []
                        if not asks:
                            print(f"[{config.remark}] ✗ 卖盘为空")
                            return

                        price = float(asks[0].price)

                        # 下单
                        order = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.BUY,
                            orderType=LIMIT_ORDER,
                            price=f"{price:.6f}",
                            makerAmountInQuoteToken=round(amount, 2)
                        )

                        resp = client.place_order(order, check_approval=True)

                        if resp.errno == 0:
                            print(
                                f"[{config.remark}] ✓ 订单提交成功 @ {self.format_price(price)}¢")
                        elif resp.errno == 10207:
                            print(f"[{config.remark}] ✗ 余额不足")
                        elif resp.errno == 10403:
                            print(f"[{config.remark}] ✗ 地区限制")
                        else:
                            print(f"[{config.remark}] ✗ 失败: errno={resp.errno}")

                    except Exception as e:
                        if "504" in str(e) or "Gateway Time-out" in str(e):
                            print(f"[{config.remark}] [!]  网关超时，订单可能已提交")
                        else:
                            print(f"[{config.remark}] ✗ 异常: {e}")

                except Exception as e:
                    print(f"[{config.remark}] ✗ 买入异常: {e}")

            # 串行执行选中账户（稳定模式，避免触发限流）
            for i, acc_idx in enumerate(selected_account_indices):
                client = self.clients[acc_idx - 1]
                config = self.configs[acc_idx - 1]
                buy_for_account(acc_idx, client, config)
                # 账户之间短暂延迟
                if i < len(selected_account_indices) - 1:
                    time.sleep(random.uniform(1, 2))

            # 等待持仓到账
            print(f"\n等待持仓更新...")
            time.sleep(5)

        # ============ 第二阶段：选中账户执行所有卖出 ============
        if sell_count > 0:
            print(f"\n{'='*60}")
            print(f"第二阶段：执行 {sell_count} 次卖出")
            print(f"{'='*60}")

            for sell_round in range(1, sell_count + 1):
                print(f"\n--- 第{sell_round}轮卖出 ---")

                def sell_for_account(account_idx, client, config):
                    try:
                        # 查询当前持仓
                        current_position = 0
                        try:
                            pos_resp = client.get_my_positions()
                            if pos_resp.errno == 0:
                                for pos in pos_resp.result.list:
                                    if str(pos.token_id) == str(token_id):
                                        current_position = int(
                                            float(pos.shares_owned))
                                        break
                        except Exception:
                            pass

                        if current_position <= 0:
                            print(f"[{config.remark}] [!]  无持仓")
                            return

                        print(f"[{config.remark}] 卖出 {current_position} tokens")

                        # 获取买1价格
                        try:
                            ob_resp = client.get_orderbook(token_id=token_id)
                            if ob_resp.errno != 0:
                                print(f"[{config.remark}] ✗ 无法获取盘口")
                                return

                            bids = sorted(ob_resp.result.bids, key=lambda x: float(
                                x.price), reverse=True)
                            if not bids:
                                print(f"[{config.remark}] ✗ 买盘为空")
                                return

                            price = float(bids[0].price)

                            # 下单
                            order = PlaceOrderDataInput(
                                marketId=market_id,
                                tokenId=token_id,
                                side=OrderSide.SELL,
                                orderType=LIMIT_ORDER,
                                price=f"{price:.6f}",
                                makerAmountInBaseToken=current_position
                            )

                            resp = client.place_order(
                                order, check_approval=True)

                            if resp.errno == 0:
                                print(
                                    f"[{config.remark}] ✓ 卖出成功 @ {self.format_price(price)}¢")
                            elif resp.errno == 10403:
                                print(f"[{config.remark}] ✗ 地区限制")
                            else:
                                print(
                                    f"[{config.remark}] ✗ 失败: errno={resp.errno}")

                        except Exception as e:
                            if "504" in str(e) or "Gateway Time-out" in str(e):
                                print(f"[{config.remark}] [!]  网关超时，订单可能已提交")
                            else:
                                print(f"[{config.remark}] ✗ 异常: {e}")

                    except Exception as e:
                        error_str = str(e)
                        if "504" in error_str or "Gateway Time-out" in error_str:
                            print(f"[{config.remark}] [!] 网关超时(504)，订单可能已提交")
                        elif "502" in error_str or "Bad Gateway" in error_str:
                            print(f"[{config.remark}] [!] 网关错误(502)，请稍后重试")
                        elif "503" in error_str or "Service Unavailable" in error_str:
                            print(f"[{config.remark}] [!] 服务不可用(503)，请稍后重试")
                        elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                            print(f"[{config.remark}] [!] 请求超时，请检查网络")
                        elif "Connection" in error_str:
                            print(f"[{config.remark}] [!] 连接失败，请检查代理")
                        else:
                            print(f"[{config.remark}] ✗ 卖出异常: {e}")

                # 串行执行选中账户（稳定模式，避免触发限流）
                for i, acc_idx in enumerate(selected_account_indices):
                    client = self.clients[acc_idx - 1]
                    config = self.configs[acc_idx - 1]
                    sell_for_account(acc_idx, client, config)
                    # 账户之间短暂延迟
                    if i < len(selected_account_indices) - 1:
                        time.sleep(random.uniform(1, 2))

                # 等待资金到账
                print(f"\n等待资金到账...")
                time.sleep(3)

        print(f"\n{'='*60}")
        print(f"{'快速模式执行完成':^60}")
        print(f"{'='*60}")

    def execute_low_loss_mode_multi(self, market_id, token_id, selected_token_name, total_trades, min_amount, max_amount, selected_account_indices=None):
        """低损耗模式多账户版本：所有账户先买后挂单

        Args:
            selected_account_indices: 选中的账户索引列表 (1-based)，如果为None则使用所有账户
        """
        # 如果没有指定账户列表，使用所有账户
        if selected_account_indices is None:
            selected_account_indices = list(range(1, len(self.clients) + 1))

        print(f"\n{'='*60}")
        print(f"低损耗模式 - 多账户串行执行")
        print(f"账户数量: {len(selected_account_indices)}")
        print(f"{'='*60}")

        # total_trades表示交易次数，每次交易包含买入+卖出
        buy_count = total_trades   # 买入次数 = 交易次数
        sell_count = total_trades  # 卖出次数 = 交易次数

        print(f"\n策略: 所有账户先买{buy_count}次 → 等待持仓 → 再挂卖{sell_count}次")

        import threading

        # ============ 第一阶段：所有账户执行所有买入 ============
        print(f"\n{'='*60}")
        print(f"第一阶段：执行 {buy_count} 次买入")
        print(f"{'='*60}")

        for buy_round in range(1, buy_count + 1):
            print(f"\n--- 第{buy_round}轮买入 ---")

            def buy_for_account(account_idx, client, config):
                try:
                    # 使用统一的金额范围
                    amount = random.uniform(min_amount, max_amount)
                    amount = round(amount, 2)

                    print(f"[{config.remark}] 买入 ${amount}")

                    # 获取卖1价格
                    try:
                        ob_resp = client.get_orderbook(token_id=token_id)
                        if ob_resp.errno != 0:
                            print(f"[{config.remark}] ✗ 无法获取盘口")
                            return

                        asks = sorted(ob_resp.result.asks, key=lambda x: float(
                            x.price)) if ob_resp.result.asks else []
                        if not asks:
                            print(f"[{config.remark}] ✗ 卖盘为空")
                            return

                        price = float(asks[0].price)

                        # 下单
                        order = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.BUY,
                            orderType=LIMIT_ORDER,
                            price=f"{price:.6f}",
                            makerAmountInQuoteToken=round(amount, 2)
                        )

                        resp = client.place_order(order, check_approval=True)

                        if resp.errno == 0:
                            print(
                                f"[{config.remark}] ✓ 订单提交成功 @ {self.format_price(price)}¢")
                        elif resp.errno == 10207:
                            print(f"[{config.remark}] ✗ 余额不足")
                        elif resp.errno == 10403:
                            print(f"[{config.remark}] ✗ 地区限制")
                        else:
                            print(f"[{config.remark}] ✗ 失败: errno={resp.errno}")

                    except Exception as e:
                        if "504" in str(e) or "Gateway Time-out" in str(e):
                            print(f"[{config.remark}] [!]  网关超时，订单可能已提交")
                        else:
                            print(f"[{config.remark}] ✗ 异常: {e}")

                except Exception as e:
                    print(f"[{config.remark}] ✗ 买入异常: {e}")

            # 串行执行选中账户（稳定模式，避免触发限流）
            for i, acc_idx in enumerate(selected_account_indices):
                client = self.clients[acc_idx - 1]
                config = self.configs[acc_idx - 1]
                buy_for_account(acc_idx, client, config)
                # 账户之间短暂延迟
                if i < len(selected_account_indices) - 1:
                    time.sleep(random.uniform(1, 2))

            # 等待持仓到账
            print(f"\n等待持仓更新...")
            time.sleep(5)

        # ============ 第二阶段：选中账户挂单卖出 ============
        print(f"\n{'='*60}")
        print(f"第二阶段：执行 {sell_count} 次挂单卖出")
        print(f"{'='*60}")

        # 获取卖1-卖5价格供用户参考
        try:
            ob_resp = self.clients[0].get_orderbook(token_id=token_id)
            if ob_resp.errno == 0:
                asks = sorted(ob_resp.result.asks,
                              key=lambda x: float(x.price))
                print(f"\n当前卖盘参考:")
                for i, ask in enumerate(asks[:5], 1):
                    print(f"  卖{i}: {self.format_price(float(ask.price))}¢")
        except Exception:
            pass

        print(f"\n请选择挂单价格:")
        print(f"  1. 卖1价格（最低）")
        print(f"  2. 卖2价格")
        print(f"  3. 卖3价格")
        print(f"  4. 卖4价格")
        print(f"  5. 卖5价格（最高）")
        print(f"  0. 自定义价格")

        price_choice = input("\n请选择 (0-5): ").strip()

        if price_choice == '0':
            custom_price = float(input("请输入自定义价格（分，如99.5）: ").strip())
            sell_price = custom_price / 100
        else:
            price_level = int(price_choice) if price_choice else 1
            try:
                ob_resp = self.clients[0].get_orderbook(token_id=token_id)
                asks = sorted(ob_resp.result.asks,
                              key=lambda x: float(x.price))
                sell_price = float(asks[price_level - 1].price)
            except Exception:
                print("✗ 获取价格失败")
                return

        print(f"\n挂单价格: {self.format_price(sell_price)}¢")

        for sell_round in range(1, sell_count + 1):
            print(f"\n--- 第{sell_round}轮挂单 ---")

            def sell_for_account(account_idx, client, config):
                try:
                    # 查询当前持仓
                    current_position = 0
                    try:
                        pos_resp = client.get_my_positions()
                        if pos_resp.errno == 0:
                            for pos in pos_resp.result.list:
                                if str(pos.token_id) == str(token_id):
                                    current_position = int(
                                        float(pos.shares_owned))
                                    break
                    except Exception:
                        pass

                    if current_position <= 0:
                        print(f"[{config.remark}] [!]  无持仓")
                        return

                    print(f"[{config.remark}] 挂卖 {current_position} tokens")

                    # 下单
                    try:
                        order = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.SELL,
                            orderType=LIMIT_ORDER,
                            price=f"{sell_price:.6f}",
                            makerAmountInBaseToken=current_position
                        )

                        resp = client.place_order(order, check_approval=True)

                        if resp.errno == 0:
                            print(f"[{config.remark}] ✓ 挂单成功")
                        elif resp.errno == 10403:
                            print(f"[{config.remark}] ✗ 地区限制")
                        else:
                            print(f"[{config.remark}] ✗ 失败: errno={resp.errno}")

                    except Exception as e:
                        if "504" in str(e) or "Gateway Time-out" in str(e):
                            print(f"[{config.remark}] [!]  网关超时，订单可能已提交")
                        else:
                            print(f"[{config.remark}] ✗ 异常: {e}")

                except Exception as e:
                    print(f"[{config.remark}] ✗ 挂单异常: {e}")

            # 串行执行选中账户（稳定模式，避免触发限流）
            for i, acc_idx in enumerate(selected_account_indices):
                client = self.clients[acc_idx - 1]
                config = self.configs[acc_idx - 1]
                sell_for_account(acc_idx, client, config)
                # 账户之间短暂延迟
                if i < len(selected_account_indices) - 1:
                    time.sleep(random.uniform(1, 2))

            time.sleep(2)

        print(f"\n{'='*60}")
        print(f"{'低损耗模式执行完成':^60}")
        print(f"{'='*60}")

    def run_trading_session(self):
        """运行交易会话"""
        print("=" * 60)
        print("Opinion.trade SDK 自动交易策略")
        print("=" * 60)

        # 默认直连模式

        # 现在初始化所有客户端
        print(f"\n{'='*60}")
        print(f"{'初始化账户客户端':^60}")
        print(f"{'='*60}")
        self._init_all_clients()
        success(f"已初始化 {len(self.clients)} 个账户")
        success("市场列表服务已启动（后台自动刷新）")

        # ============ 主菜单 ============
        while True:
            section("主菜单")
            menu("请选择操作", [
                ("1", "开始交易"),
                ("2", "合并/拆分"),
                ("3", "查询挂单"),
                ("4", "撤销挂单"),
                ("5", "查询TOKEN持仓"),
                ("6", "查询账户资产详情"),
                ("7", "Claim (领取已结算市场收益)"),
                ("0", "[red]退出程序[/red]"),
            ])

            menu_choice = ask("\n请选择", default="0")

            if menu_choice == '0':
                success("程序退出")
                return
            elif menu_choice == '1':
                # 开始交易
                self.trading_menu()
            elif menu_choice == '2':
                # 合并/拆分
                self.merge_split_menu()
            elif menu_choice == '3':
                # 查询挂单
                self.query_open_orders()
            elif menu_choice == '4':
                # 撤销挂单
                self.cancel_orders_menu()
            elif menu_choice == '5':
                # 查询TOKEN持仓
                self.query_positions()
            elif menu_choice == '6':
                # 查询账户资产详情
                self.query_account_assets()
            elif menu_choice == '7':
                # Claim领取收益
                self.claim_menu()
            else:
                print("✗ 无效选择")

    def parse_custom_strategy(self, strategy_str: str) -> list:
        """
        解析自定义策略字符串
        格式: 买50买100买60卖200 或 卖x买x卖x买x卖x
        返回: [('buy', 50), ('buy', 100), ('buy', 60), ('sell', 200)]

        规则:
        - 买/卖 后面跟金额（数字）
        - 买/卖 后面跟 x 表示卖出全部持仓
        - 连续相同操作表示并发执行（如 买买买 = 同时买3次）
        """
        import re

        strategy_str = strategy_str.strip().lower()
        # 替换中文
        strategy_str = strategy_str.replace('买', 'b').replace('卖', 's')

        operations = []
        i = 0
        while i < len(strategy_str):
            if strategy_str[i] in ['b', 's']:
                op_type = 'buy' if strategy_str[i] == 'b' else 'sell'
                i += 1

                # 读取金额或x
                amount_str = ''
                while i < len(strategy_str) and (strategy_str[i].isdigit() or strategy_str[i] == '.' or strategy_str[i] == 'x'):
                    amount_str += strategy_str[i]
                    i += 1

                if amount_str == 'x' or amount_str == '':
                    amount = 'x'  # x表示卖出全部或使用默认金额
                else:
                    try:
                        amount = float(amount_str)
                    except Exception:
                        amount = 'x'

                operations.append((op_type, amount))
            else:
                i += 1  # 跳过无效字符

        return operations

    def group_operations(self, operations: list) -> list:
        """
        将连续相同操作分组
        输入: [('buy', 50), ('buy', 100), ('sell', 200)]
        输出: [
            {'type': 'buy', 'amounts': [50, 100], 'concurrent': True},
            {'type': 'sell', 'amounts': [200], 'concurrent': False}
        ]
        """
        if not operations:
            return []

        groups = []
        current_group = {
            'type': operations[0][0],
            'amounts': [operations[0][1]],
            'concurrent': False
        }

        for i in range(1, len(operations)):
            op_type, amount = operations[i]
            if op_type == current_group['type']:
                # 同类型操作，加入当前组，标记为并发
                current_group['amounts'].append(amount)
                current_group['concurrent'] = True
            else:
                # 不同类型，保存当前组，开始新组
                groups.append(current_group)
                current_group = {
                    'type': op_type,
                    'amounts': [amount],
                    'concurrent': False
                }

        groups.append(current_group)
        return groups

    def limit_order_menu(self, selected_account_indices: list):
        """挂单模式菜单 - 自定义价格挂单买入或卖出"""
        print(f"\n{'='*60}")
        print(f"{'挂单模式（自定义价格）':^60}")
        print(f"{'='*60}")

        # 1. 选择挂单方向
        print("\n挂单方向:")
        print("  1. 挂单买入")
        print("  2. 挂单卖出")
        print("  3. 挂单买入 → 成交后自动卖1挂出")
        print("  0. 返回")
        direction_choice = input("请选择 (0-3): ").strip()

        if direction_choice == '0' or not direction_choice:
            return
        elif direction_choice not in ['1', '2', '3']:
            print("✗ 无效选择")
            return

        is_buy = (direction_choice in ['1', '3'])
        auto_sell_after_buy = (direction_choice == '3')
        direction_name = "买入" if is_buy else "卖出"
        if auto_sell_after_buy:
            print(f"\n✓ 已选择: 挂单买入 → 成交后自动卖1挂出")
        else:
            print(f"\n✓ 已选择: 挂单{direction_name}")

        # 2. 输入市场ID
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 3. 获取市场信息
        client = self.clients[0]

        try:
            print(f"\n正在获取市场 {market_id} 的信息...")

            categorical_response = client.get_categorical_market(
                market_id=market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                market_data = categorical_response.result.data
                if not hasattr(market_data, 'market_title') or not market_data.market_title:
                    print(f"✗ 市场 {market_id} 数据不完整")
                    return

                parent_market_title = market_data.market_title
                print(f"\n✓ 找到分类市场: {parent_market_title}")

                if hasattr(market_data, 'child_markets') and market_data.child_markets and len(market_data.child_markets) > 0:
                    child_markets = market_data.child_markets

                    print(f"\n找到 {len(child_markets)} 个子市场:")
                    for idx, child in enumerate(child_markets, 1):
                        title = child.market_title if hasattr(
                            child, 'market_title') else 'N/A'
                        child_id = child.market_id if hasattr(
                            child, 'market_id') else 'N/A'
                        print(f"  {idx}. [{child_id}] {title}")
                    print(f"  0. 返回")

                    choice_input = input(
                        f"\n请选择子市场 (0-{len(child_markets)}): ").strip()
                    if not choice_input or choice_input == '0':
                        return

                    try:
                        choice = int(choice_input)
                    except ValueError:
                        print("✗ 请输入有效的数字")
                        return

                    if choice < 1 or choice > len(child_markets):
                        print("✗ 无效的选择")
                        return

                    selected_child = child_markets[choice - 1]
                    market_id = selected_child.market_id

                    detail_response = client.get_market(market_id=market_id)
                    if detail_response.errno != 0 or not detail_response.result or not detail_response.result.data:
                        print(f"✗ 获取子市场详细信息失败")
                        return

                    market_data = detail_response.result.data
                else:
                    print(f"  (无子市场，直接交易此市场)")
            else:
                market_response = client.get_market(market_id=market_id)

                if market_response.errno != 0 or not market_response.result or not market_response.result.data:
                    print(f"✗ 市场 {market_id} 不存在")
                    return

                market_data = market_response.result.data
                print(f"\n✓ 找到二元市场: {market_data.market_title}")

        except Exception as e:
            print(f"✗ 获取市场信息失败: {e}")
            return

        # 4. 选择交易方向
        print(f"\n请选择交易方向:")
        print(f"  1. YES")
        print(f"  2. NO")
        print(f"  0. 返回")
        side_choice = input("请输入选项 (0-2): ").strip()

        if side_choice == '0' or not side_choice:
            return
        elif side_choice == '1':
            token_id = market_data.yes_token_id
            selected_token_name = "YES"
        elif side_choice == '2':
            token_id = market_data.no_token_id
            selected_token_name = "NO"
        else:
            print("✗ 无效选择")
            return

        print(f"\n✓ 已选择: {selected_token_name}")

        # 4.5 对于"挂单买入成交后卖1挂出"模式，检测是否有未挂出的持仓
        if auto_sell_after_buy:
            print(f"\n正在检测持仓和已挂单情况...")
            available_to_sell = {}  # 各账户可挂出的份额
            account_cost_prices = {}  # 各账户的成本价
            total_available = 0

            for acc_idx in selected_account_indices:
                acc_client = self.clients[acc_idx - 1]
                config = self.configs[acc_idx - 1]

                try:
                    # 获取持仓
                    position_shares = 0
                    cost_price = 0
                    positions_response = acc_client.get_my_positions()
                    if positions_response.errno == 0:
                        positions = positions_response.result.list if hasattr(
                            positions_response.result, 'list') else []
                        for position in positions:
                            if str(position.token_id) == str(token_id):
                                position_shares = int(float(position.shares_owned)) if hasattr(
                                    position, 'shares_owned') else 0
                                # 获取成本价
                                cost_price = float(position.avg_entry_price if hasattr(
                                    position, 'avg_entry_price') and position.avg_entry_price else 0)
                                break

                    # 获取已挂单卖出的份额
                    pending_sell_shares = 0
                    orders_response = acc_client.get_my_orders()
                    if orders_response.errno == 0:
                        orders = orders_response.result.list if hasattr(
                            orders_response.result, 'list') else []
                        for order in orders:
                            # 只统计该token的卖出挂单（status=1是pending）
                            if (hasattr(order, 'status') and order.status == 1 and
                                hasattr(order, 'token_id') and str(order.token_id) == str(token_id) and
                                    hasattr(order, 'side') and order.side == 'SELL'):
                                order_shares = float(
                                    order.shares if hasattr(order, 'shares') else 0)
                                filled_shares = float(order.filled_shares if hasattr(
                                    order, 'filled_shares') else 0)
                                pending_sell_shares += int(
                                    order_shares - filled_shares)

                    # 可挂出份额 = 持仓 - 已挂单卖出
                    avail = max(0, position_shares - pending_sell_shares)
                    available_to_sell[acc_idx] = avail
                    account_cost_prices[acc_idx] = cost_price
                    total_available += avail

                    cost_display = f"{cost_price*100:.1f}¢" if cost_price > 0 else "N/A"
                    print(
                        f"  [{config.remark}] 持仓: {position_shares}份, 成本: {cost_display}, 已挂卖单: {pending_sell_shares}份, 可挂出: {avail}份")

                except Exception as e:
                    available_to_sell[acc_idx] = 0
                    account_cost_prices[acc_idx] = 0
                    print(f"  [{config.remark}] 查询异常: {e}")

            # 如果有可挂出的份额，询问是否直接挂出
            if total_available > 0:
                print(f"\n检测到可挂出份额: {total_available}份")
                print(f"  1. 直接挂出这些份额（以买1价格）")
                print(f"  2. 继续新的挂单买入流程")
                resume_choice = input("请选择 (1-2): ").strip()

                if resume_choice == '1':
                    # 直接挂出模式
                    while True:
                        split_input = input("\n请输入要分几笔挂出: ").strip()
                        try:
                            split_count = int(split_input)
                            if split_count <= 0:
                                print("✗ 笔数必须大于0")
                                continue
                            break
                        except ValueError:
                            print("✗ 请输入有效的整数")

                    # 获取买1价格
                    ob = OrderbookService.fetch(client, token_id)
                    if not ob['success'] or not ob['bids']:
                        print("✗ 无买盘，无法挂卖")
                        return
                    sell_price = ob['bid1_price']
                    print(f"\n买1价格: {self.format_price(sell_price)}¢")

                    # 检测成本价，判断是否可能亏损
                    has_loss_risk = False
                    for acc_idx in selected_account_indices:
                        cost_price = account_cost_prices.get(acc_idx, 0)
                        if cost_price > 0 and sell_price < cost_price:
                            has_loss_risk = True
                            config = self.configs[acc_idx - 1]
                            loss_pct = (cost_price - sell_price) / \
                                cost_price * 100
                            print(
                                f"  [!] [{config.remark}] 买1价格 {self.format_price(sell_price)}¢ 低于成本价 {self.format_price(cost_price)}¢ (亏损 {loss_pct:.1f}%)")

                    if has_loss_risk:
                        print(f"\n[!] 警告: 当前买1价格低于部分账户成本价，继续挂单可能存在亏损!")
                        loss_confirm = input("输入 1 继续挂单，其他或回车返回主菜单: ").strip()
                        if loss_confirm != '1':
                            print("✗ 已取消")
                            return

                    # 确认信息
                    print(f"\n{'='*60}")
                    print(f"{'【挂卖确认】':^60}")
                    print(f"{'='*60}")
                    print(f"  市场: {market_data.market_title}")
                    print(f"  方向: {selected_token_name}")
                    print(f"  操作: 挂出之前买入成交的份额")
                    print(f"  价格: {self.format_price(sell_price)}¢ (买1)")
                    print(f"  总份额: {total_available}份")
                    print(f"  分笔数: {split_count}")
                    print(f"  账户数: {len(selected_account_indices)}")
                    print(f"{'='*60}")

                    confirm = input("\n确认无误请输入 'done': ").strip().lower()
                    if confirm != 'done':
                        print("✗ 已取消")
                        return

                    # 执行挂卖
                    self.execute_resume_sell(
                        selected_account_indices=selected_account_indices,
                        market_id=market_id,
                        token_id=token_id,
                        sell_price=sell_price,
                        split_count=split_count,
                        available_to_sell=available_to_sell
                    )
                    return
                # 如果选择2，继续下面的正常挂单买入流程

        # 5. 获取当前盘口信息
        print(f"\n正在获取盘口信息...")
        ob = OrderbookService.fetch(client, token_id)
        if ob['success']:
            # 显示盘口信息
            OrderbookDisplay.show(
                ob['bids'][:5], ob['asks'][:5],
                mode=OrderbookDisplay.MODE_SIMPLE,
                max_rows=5,
                show_summary=False,
                format_price_func=self.format_price
            )

            # 提示当前价格
            if is_buy:
                if ob['ask1_price'] > 0:
                    print(
                        f"\n  [*] 买入提示: 卖1价格 {self.format_price(ob['ask1_price'])}¢ 可立即成交")
                if ob['bid1_price'] > 0:
                    print(
                        f"  [*] 挂单提示: 低于买1价格 {self.format_price(ob['bid1_price'])}¢ 需等待成交")
            else:
                if ob['bid1_price'] > 0:
                    print(
                        f"\n  [*] 卖出提示: 买1价格 {self.format_price(ob['bid1_price'])}¢ 可立即成交")
                if ob['ask1_price'] > 0:
                    print(
                        f"  [*] 挂单提示: 高于卖1价格 {self.format_price(ob['ask1_price'])}¢ 需等待成交")
        else:
            print(f"[!] 获取盘口失败，继续...")

        # 6. 输入挂单价格（支持固定价格或区间随机）
        print(f"\n请输入挂单价格 (单位: 分，如 50 表示 50¢)")
        print(f"  - 固定价格: 直接输入数字，如 50")
        print(f"  - 区间随机: 输入 最低-最高，如 48-52")

        order_price = None  # 固定价格
        price_range = None  # 价格区间 (min, max)

        while True:
            price_input = input("挂单价格 (留空返回): ").strip()
            if not price_input:
                return

            try:
                if '-' in price_input:
                    # 区间模式
                    parts = price_input.split('-')
                    if len(parts) != 2:
                        print("✗ 区间格式错误，请使用 最低-最高 格式，如 48-52")
                        continue
                    min_price = float(parts[0].strip())
                    max_price = float(parts[1].strip())
                    if min_price <= 0 or max_price >= 100:
                        print("✗ 价格必须在 0-100 之间")
                        continue
                    if min_price > max_price:
                        print("✗ 最低价格不能大于最高价格")
                        continue
                    price_range = (min_price / 100, max_price / 100)  # 转换为小数
                    print(
                        f"✓ 挂单价格区间: {self.format_price(price_range[0])}¢ - {self.format_price(price_range[1])}¢ (每笔随机)")
                    break
                else:
                    # 固定价格模式
                    price_cent = float(price_input)
                    if price_cent <= 0 or price_cent >= 100:
                        print("✗ 价格必须在 0-100 之间")
                        continue
                    order_price = price_cent / 100  # 转换为小数
                    print(f"✓ 挂单价格: {self.format_price(order_price)}¢")
                    break
            except ValueError:
                print("✗ 请输入有效的数字")

        # 7. 输入挂单次数
        while True:
            num_input = input("\n请输入挂单次数: ").strip()
            try:
                num_orders = int(num_input)
                if num_orders <= 0:
                    print("✗ 次数必须大于0")
                    continue
                break
            except ValueError:
                print("✗ 请输入有效的整数")

        print(f"✓ 挂单次数: {num_orders}")

        # 8. 输入金额范围（买入）或份额范围（卖出）
        if is_buy:
            print(f"\n请输入单笔金额范围 (USDT):")
            while True:
                min_input = input("单笔最低金额 ($): ").strip()
                try:
                    min_amount = float(min_input)
                    if min_amount <= 0:
                        print("✗ 金额必须大于0")
                        continue
                    break
                except ValueError:
                    print("✗ 请输入有效的数字")

            while True:
                max_input = input("单笔最高金额 ($): ").strip()
                try:
                    max_amount = float(max_input)
                    if max_amount < min_amount:
                        print(f"✗ 最高金额必须 >= 最低金额 ${min_amount:.2f}")
                        continue
                    break
                except ValueError:
                    print("✗ 请输入有效的数字")

            print(f"✓ 单笔金额: ${min_amount:.2f} - ${max_amount:.2f}")
        else:
            # 卖出模式：查询持仓
            print(f"\n正在查询持仓...")
            account_positions = {}
            for acc_idx in selected_account_indices:
                acc_client = self.clients[acc_idx - 1]
                config = self.configs[acc_idx - 1]
                try:
                    positions_response = acc_client.get_my_positions()
                    if positions_response.errno == 0:
                        positions = positions_response.result.list if hasattr(
                            positions_response.result, 'list') else []
                        for position in positions:
                            if str(position.token_id) == str(token_id):
                                shares = int(float(position.shares_owned)) if hasattr(
                                    position, 'shares_owned') else 0
                                account_positions[acc_idx] = shares
                                print(f"  [{config.remark}] 持仓: {shares}份")
                                break
                        else:
                            account_positions[acc_idx] = 0
                            print(f"  [{config.remark}] 持仓: 0份")
                    else:
                        account_positions[acc_idx] = 0
                except Exception:
                    account_positions[acc_idx] = 0

            total_position = sum(account_positions.values())
            if total_position == 0:
                print(f"\n✗ 所有账户均无持仓，无法挂单卖出")
                return

            # 先询问是否全仓挂出
            print(f"\n是否全仓挂出?")
            print(f"  1. 是 - 全仓挂出")
            print(f"  2. 否 - 自定义份额")
            full_sell_choice = input("请选择 (1-2): ").strip()

            if full_sell_choice == '1':
                # 全仓挂出：每个账户的份额就是其持仓量
                # min_amount和max_amount设为0，表示全仓模式
                min_amount = 0
                max_amount = 0
                print(f"✓ 已选择: 全仓挂出")
            else:
                # 自定义份额
                print(f"\n请输入单笔份额范围:")
                while True:
                    min_input = input("单笔最低份额: ").strip()
                    try:
                        min_amount = int(min_input)
                        if min_amount <= 0:
                            print("✗ 份额必须大于0")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的整数")

                while True:
                    max_input = input("单笔最高份额: ").strip()
                    try:
                        max_amount = int(max_input)
                        if max_amount < min_amount:
                            print(f"✗ 最高份额必须 >= 最低份额 {min_amount}")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的整数")

                print(f"✓ 单笔份额: {min_amount} - {max_amount}")

        # 9. 确认信息
        print(f"\n{'='*60}")
        print(f"{'【挂单确认】':^60}")
        print(f"{'='*60}")
        print(f"  市场: {market_data.market_title}")
        print(f"  方向: {selected_token_name}")
        if auto_sell_after_buy:
            print(f"  操作: 挂单买入 → 成交后自动卖1挂出")
        else:
            print(f"  操作: 挂单{direction_name}")
        # 显示价格（支持固定价格或区间）
        if price_range:
            print(
                f"  价格: {self.format_price(price_range[0])}¢ - {self.format_price(price_range[1])}¢ (随机)")
        else:
            print(f"  价格: {self.format_price(order_price)}¢")
        print(f"  次数: {num_orders}")
        if is_buy:
            print(f"  单笔金额: ${min_amount:.2f} - ${max_amount:.2f}")
            print(
                f"  预计总金额: ${min_amount * num_orders:.2f} - ${max_amount * num_orders:.2f}")
        else:
            if min_amount == 0 and max_amount == 0:
                # 全仓模式
                print(f"  模式: 全仓挂出")
                print(f"  总份额: {total_position}份")
            else:
                print(f"  单笔份额: {min_amount} - {max_amount}")
                print(
                    f"  预计总份额: {min_amount * num_orders} - {max_amount * num_orders}")
        print(f"  账户数: {len(selected_account_indices)}")
        print(f"{'='*60}")

        confirm = input("\n确认无误请输入 'done': ").strip().lower()
        if confirm != 'done':
            print("✗ 已取消")
            return

        # 10. 执行挂单
        self.execute_limit_orders(
            selected_account_indices=selected_account_indices,
            market_id=market_id,
            token_id=token_id,
            selected_token_name=selected_token_name,
            is_buy=is_buy,
            order_price=order_price,
            price_range=price_range,
            num_orders=num_orders,
            min_amount=min_amount,
            max_amount=max_amount,
            account_positions=account_positions if not is_buy else None,
            auto_sell_after_buy=auto_sell_after_buy
        )

    def execute_limit_orders(self, selected_account_indices, market_id, token_id, selected_token_name, is_buy, order_price, num_orders, min_amount, max_amount, account_positions=None, auto_sell_after_buy=False, price_range=None):
        """执行挂单

        Args:
            price_range: 价格区间元组 (min_price, max_price)，如果设置则每笔随机取值
            order_price: 固定价格（当price_range为None时使用）
        """
        import threading

        print(f"\n{'='*60}")
        if auto_sell_after_buy:
            print(f"开始执行挂单买入 → 成交后自动卖1挂出")
        else:
            print(f"开始执行挂单{'买入' if is_buy else '卖出'}")
        print(f"{'='*60}")

        # 价格处理：支持固定价格或区间随机
        def get_order_price():
            """获取本次挂单价格（支持区间随机）"""
            if price_range:
                # 区间模式：每次随机取值
                return random.uniform(price_range[0], price_range[1])
            else:
                # 固定价格模式
                return order_price

        print_lock = threading.Lock()

        def execute_for_account(acc_idx):
            client = self.clients[acc_idx - 1]
            config = self.configs[acc_idx - 1]

            with print_lock:
                print(f"\n[{config.remark}] 开始挂单...")

            # 如果是买入，先查询账户余额并计算每笔金额
            account_amounts = []  # 预先计算好每笔金额
            if is_buy:
                # 查询账户余额
                account_balance = self.get_usdt_balance(config)
                total_needed = max_amount * num_orders

                if account_balance < total_needed:
                    # 余额不足，按账户余额/次数计算，随机*0.8-1.2
                    with print_lock:
                        print(
                            f"  [{config.remark}] [!] 余额不足: ${account_balance:.2f} < ${total_needed:.2f}")
                        print(f"  [{config.remark}] 调整为按余额分配...")

                    base_amount = account_balance / num_orders
                    remaining = account_balance

                    for i in range(num_orders):
                        if i == num_orders - 1:
                            # 最后一笔用剩余金额
                            amt = remaining
                        else:
                            # 随机*0.8-1.2
                            amt = base_amount * random.uniform(0.8, 1.2)
                            # 确保不超过剩余金额，且留够后续笔数的最低金额
                            remaining_orders = num_orders - i - 1
                            min_for_remaining = remaining_orders * \
                                (base_amount * 0.8)
                            max_allowed = remaining - min_for_remaining
                            amt = min(amt, max_allowed)
                            amt = max(amt, 1.5)  # 最低$1.5

                        amt = round(amt, 2)
                        account_amounts.append(amt)
                        remaining -= amt

                    with print_lock:
                        print(f"  [{config.remark}] 分配金额: {' + '.join([f'${a:.2f}' for a in account_amounts])} = ${
                              sum(account_amounts):.2f}")
                else:
                    # 余额充足，正常随机
                    for _ in range(num_orders):
                        amt = random.uniform(min_amount, max_amount)
                        account_amounts.append(round(amt, 2))

            success_count = 0
            fail_count = 0

            for i in range(1, num_orders + 1):
                try:
                    # 每笔挂单获取价格（支持区间随机）
                    current_price = get_order_price()
                    current_price_str = f"{current_price:.6f}"
                    current_price_display = self.format_price(
                        current_price) + '¢'

                    if is_buy:
                        # 买入：使用预先计算的金额
                        amount = account_amounts[i - 1]

                        order = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.BUY,
                            orderType=LIMIT_ORDER,
                            price=current_price_str,
                            makerAmountInQuoteToken=round(amount, 2)
                        )

                        result = client.place_order(order, check_approval=True)

                        with print_lock:
                            if result.errno == 0:
                                print(
                                    f"  [{config.remark}] ✓ 挂买#{i}: ${amount:.2f} @ {current_price_display}")
                                success_count += 1

                                # 如果启用了成交后自动卖1挂出
                                if auto_sell_after_buy:
                                    # 获取订单ID
                                    order_id = result.result.order_id if hasattr(
                                        result, 'result') and hasattr(result.result, 'order_id') else None
                                    if order_id:
                                        print(
                                            f"  [{config.remark}] 等待订单#{i}成交...")
                                        # 监控订单成交
                                        filled_shares = 0
                                        buy_cost_price = current_price  # 买入成本价
                                        max_wait = 60  # 最多等待60秒
                                        wait_time = 0
                                        while wait_time < max_wait:
                                            time.sleep(3)
                                            wait_time += 3
                                            # 查询订单状态
                                            try:
                                                orders_resp = client.get_my_orders()
                                                if orders_resp.errno == 0:
                                                    orders = orders_resp.result.list if hasattr(
                                                        orders_resp.result, 'list') else []
                                                    for o in orders:
                                                        if hasattr(o, 'order_id') and str(o.order_id) == str(order_id):
                                                            filled = float(o.filled_shares if hasattr(
                                                                o, 'filled_shares') else 0)
                                                            status = o.status if hasattr(
                                                                o, 'status') else 1
                                                            if filled > 0:
                                                                filled_shares = int(
                                                                    filled)
                                                                print(
                                                                    f"  [{config.remark}] 订单#{i}已成交: {filled_shares}份")
                                                                break
                                                            if status != 1:  # 非Pending状态
                                                                break
                                                    if filled_shares > 0:
                                                        break
                                            except Exception as e:
                                                print(
                                                    f"  [{config.remark}] 查询订单状态异常: {e}")

                                        if filled_shares > 0:
                                            # 获取卖1价格
                                            try:
                                                ob_resp = client.get_orderbook(
                                                    token_id=token_id)
                                                if ob_resp.errno == 0:
                                                    bids = sorted(ob_resp.result.bids, key=lambda x: float(
                                                        x.price), reverse=True) if ob_resp.result.bids else []
                                                    if bids:
                                                        sell1_price = float(
                                                            bids[0].price)
                                                        sell1_display = self.format_price(
                                                            sell1_price) + '¢'

                                                        # 检查卖1价格是否低于成本价
                                                        if sell1_price < buy_cost_price:
                                                            print(
                                                                f"  [{config.remark}] [!] 卖1价格 {sell1_display} 低于成本价 {current_price_display}")
                                                            # 这里不询问用户，直接跳过（因为是并发执行）
                                                            print(
                                                                f"  [{config.remark}] [!] 跳过自动挂卖（亏损）")
                                                        else:
                                                            # 以卖1价格挂出
                                                            sell_order = PlaceOrderDataInput(
                                                                marketId=market_id,
                                                                tokenId=token_id,
                                                                side=OrderSide.SELL,
                                                                orderType=LIMIT_ORDER,
                                                                price=f"{sell1_price:.6f}",
                                                                makerAmountInBaseToken=filled_shares
                                                            )
                                                            sell_result = client.place_order(
                                                                sell_order, check_approval=True)
                                                            if sell_result.errno == 0:
                                                                print(
                                                                    f"  [{config.remark}] ✓ 自动挂卖#{i}: {filled_shares}份 @ {sell1_display}")
                                                            else:
                                                                print(
                                                                    f"  [{config.remark}] ✗ 自动挂卖#{i}失败: {self.translate_error(sell_result.errmsg)}")
                                                    else:
                                                        print(
                                                            f"  [{config.remark}] ✗ 无买盘，无法自动挂卖")
                                                else:
                                                    print(
                                                        f"  [{config.remark}] ✗ 获取盘口失败")
                                            except Exception as e:
                                                print(
                                                    f"  [{config.remark}] ✗ 自动挂卖异常: {e}")
                                        else:
                                            print(
                                                f"  [{config.remark}] [!] 订单#{i}未成交，跳过自动挂卖")
                            else:
                                print(
                                    f"  [{config.remark}] ✗ 挂买#{i}: {self.translate_error(result.errmsg)}")
                                fail_count += 1
                    else:
                        # 卖出
                        if min_amount == 0 and max_amount == 0:
                            # 全仓模式：第一笔挂出全部持仓，后续跳过
                            if i == 1:
                                shares = account_positions.get(acc_idx, 0)
                                if shares <= 0:
                                    with print_lock:
                                        print(
                                            f"  [{config.remark}] ✗ 挂卖: 无可用持仓")
                                    fail_count += 1
                                    break  # 全仓模式下无持仓直接跳过所有循环
                            else:
                                # 全仓模式第2笔以后跳过
                                continue
                        else:
                            # 随机份额模式
                            shares = random.randint(min_amount, max_amount)

                            # 检查是否有足够持仓
                            if account_positions and account_positions.get(acc_idx, 0) < shares:
                                available = account_positions.get(acc_idx, 0)
                                if available <= 0:
                                    with print_lock:
                                        print(
                                            f"  [{config.remark}] ✗ 挂卖#{i}: 无可用持仓")
                                    fail_count += 1
                                    continue
                                shares = available

                        order = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.SELL,
                            orderType=LIMIT_ORDER,
                            price=current_price_str,
                            makerAmountInBaseToken=shares
                        )

                        result = client.place_order(order, check_approval=True)

                        with print_lock:
                            if result.errno == 0:
                                print(
                                    f"  [{config.remark}] ✓ 挂卖#{i}: {shares}份 @ {current_price_display}")
                                success_count += 1
                                # 更新剩余持仓
                                if account_positions:
                                    account_positions[acc_idx] = account_positions.get(
                                        acc_idx, 0) - shares
                            else:
                                print(
                                    f"  [{config.remark}] ✗ 挂卖#{i}: {self.translate_error(result.errmsg)}")
                                fail_count += 1

                    # 随机延迟
                    time.sleep(random.uniform(0.5, 1.5))

                except Exception as e:
                    with print_lock:
                        print(f"  [{config.remark}] ✗ 挂单#{i}异常: {e}")
                    fail_count += 1

            with print_lock:
                print(
                    f"  [{config.remark}] 完成: 成功{success_count}, 失败{fail_count}")

        # 串行执行所有账户（稳定模式，避免触发限流）
        for i, acc_idx in enumerate(selected_account_indices):
            execute_for_account(acc_idx)
            # 账户之间短暂延迟
            if i < len(selected_account_indices) - 1:
                time.sleep(random.uniform(1, 2))

        print(f"\n{'='*60}")
        print(f"{'挂单执行完成':^60}")
        print(f"{'='*60}")

    # ============ 做市商策略相关方法 ============

    def market_maker_menu(self, selected_account_indices: list):
        """做市商模式入口菜单"""
        print(f"\n{'='*60}")
        print(f"{'做市商模式':^60}")
        print(f"{'='*60}")

        # ===== 风险提示 =====
        print(f"\n{'='*60}")
        print(f"{'[!] 风险提示':^60}")
        print(f"{'='*60}")
        print("做市交易风险巨大，可能会出现巨大亏损！")
        print("可能的风险包括但不限于：")
        print("  - 价格剧烈波动导致单边持仓亏损")
        print("  - 被恶意操控盘口导致高买低卖")
        print("  - 市场流动性枯竭无法平仓")
        print("  - 网络延迟导致撤单不及时")
        print("一切亏损责任需要操作者自行承担，与软件作者无关。")
        print(f"{'='*60}")

        print("\n说明: 双边挂单策略，同时在买卖两侧挂单")
        print("      支持分层挂单（如买1-5-10分布），增加订单簿厚度")
        print("      支持垂直/金字塔/倒金字塔分布模式")
        print("      支持价格跟随、仓位管理、止损保护")

        risk_confirm = input("\n确认了解风险并继续？输入 yes 继续，其他按键返回: ").strip().lower()
        if risk_confirm != 'yes':
            print("已返回主菜单")
            return

        # 选择模式
        print("\n请选择模式:")
        print("  1. 单市场做市")
        print("  2. 批量多市场做市（多市场+多账户矩阵分配）")

        mode_choice = input("请选择 (1/2, 默认1): ").strip()
        if mode_choice == '2':
            self._batch_market_maker_menu(selected_account_indices)
            return

        # 1. 输入市场ID
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 2. 获取市场信息
        client = self.clients[0]

        try:
            print(f"\n正在获取市场 {market_id} 的信息...")

            # 先尝试作为分类市场获取
            categorical_response = client.get_categorical_market(
                market_id=market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                # 这是一个分类市场
                market_data = categorical_response.result.data
                if not hasattr(market_data, 'market_title') or not market_data.market_title:
                    print(f"✗ 市场 {market_id} 数据不完整")
                    return

                parent_market_title = market_data.market_title
                print(f"\n✓ 找到分类市场: {parent_market_title}")

                # 显示子市场列表
                if hasattr(market_data, 'child_markets') and market_data.child_markets:
                    child_markets = market_data.child_markets
                    print(f"\n子市场列表:")
                    for i, child in enumerate(child_markets, 1):
                        child_title = child.market_title if hasattr(
                            child, 'market_title') else f"子市场{i}"
                        child_id = child.market_id if hasattr(
                            child, 'market_id') else 0
                        print(f"  {i}. {child_title} (ID: {child_id})")

                    child_choice = input(
                        f"\n请选择子市场 (1-{len(child_markets)}): ").strip()
                    try:
                        child_idx = int(child_choice) - 1
                        if 0 <= child_idx < len(child_markets):
                            selected_child = child_markets[child_idx]
                            market_id = selected_child.market_id
                            print(f"✓ 已选择: {selected_child.market_title}")
                            # 获取子市场详细信息（包含token_id）
                            child_response = client.get_market(
                                market_id=market_id)
                            if child_response.errno != 0 or not child_response.result or not child_response.result.data:
                                print(f"✗ 无法获取子市场详细信息")
                                return
                            market_data = child_response.result.data
                        else:
                            print("✗ 选择无效")
                            return
                    except ValueError:
                        print("✗ 请输入有效的数字")
                        return
                else:
                    print("✗ 该分类市场没有子市场")
                    return
            else:
                # 尝试作为普通市场获取
                market_response = client.get_market(market_id=market_id)
                if market_response.errno != 0:
                    print(f"✗ 市场不存在或已下架，请检查市场ID ({market_response.errmsg})")
                    return
                market_data = market_response.result.data
                print(f"\n✓ 找到市场: {market_data.market_title}")

        except Exception as e:
            print(f"✗ 获取市场信息异常: {e}")
            return

        # 3. 选择YES/NO方向
        print(f"\n选择交易方向:")
        print("  1. YES")
        print("  2. NO")

        side_choice = input("请选择 (1/2): ").strip()
        if side_choice == '1':
            token_id = market_data.yes_token_id if hasattr(
                market_data, 'yes_token_id') else None
            selected_token_name = "YES"
        elif side_choice == '2':
            token_id = market_data.no_token_id if hasattr(
                market_data, 'no_token_id') else None
            selected_token_name = "NO"
        else:
            print("✗ 无效选择")
            return

        if not token_id:
            print("✗ 无法获取Token ID")
            return

        print(f"✓ 已选择: {selected_token_name} (Token: {token_id})")

        # 4. 显示当前盘口并获取价格
        current_bid1, current_ask1 = self._mm_show_orderbook(client, token_id)

        # 5. 配置做市参数（传入当前价格供参考）
        market_title_full = f"{market_data.market_title} - {selected_token_name}"
        config = self._configure_market_maker(
            market_id, token_id, market_title_full,
            current_bid1, current_ask1
        )
        if not config:
            return

        # 6. 显示配置确认
        self._mm_show_config(config, selected_account_indices)

        confirm = input("\n确认开始做市？输入 'start' 启动: ").strip().lower()
        if confirm != 'start':
            print("✗ 已取消")
            return

        # 7. 检查现有持仓并询问是否挂卖单（在选择运行模式之前完成所有input）
        existing_positions = {}
        initial_sell_orders = {}
        print(f"\n正在检查各账户现有持仓...")
        for acc_idx in selected_account_indices:
            client = self.clients[acc_idx - 1]
            cfg = self.configs[acc_idx - 1]
            shares, price, value = self._mm_get_current_position(
                client, config.token_id)
            if shares > 0:
                existing_positions[acc_idx] = {
                    'shares': shares,
                    'price': price,
                    'value': value,
                    'remark': cfg.remark
                }

        if existing_positions:
            print(f"\n发现以下账户有现有持仓:")
            for acc_idx, pos in existing_positions.items():
                print(
                    f"  [{pos['remark']}] {pos['shares']}份 @ {self.format_price(pos['price'])}¢ (价值${pos['value']:.2f})")

            sell_choice = input("\n是否将现有持仓挂卖单? (y/n, 默认y): ").strip().lower()
            if sell_choice != 'n':
                # 获取当前卖1价作为参考
                client = self.clients[selected_account_indices[0] - 1]
                orderbook = self._mm_get_orderbook(client, config.token_id)
                if orderbook and orderbook.asks:
                    ask1_price = float(orderbook.asks[0].price)
                    print(f"\n当前卖1价: {self.format_price(ask1_price)}¢")

                    price_input = input(
                        f"挂单价格 (默认卖1价 {self.format_price(ask1_price)}¢): ").strip()
                    if price_input:
                        sell_price = float(price_input) / 100  # 输入是分，转为美元
                    else:
                        sell_price = ask1_price

                    # 为每个有持仓的账户记录要挂的卖单
                    for acc_idx, pos in existing_positions.items():
                        initial_sell_orders[acc_idx] = {
                            'shares': pos['shares'],
                            'price': sell_price
                        }
                    print(f"✓ 将在做市启动后以 {self.format_price(sell_price)}¢ 挂卖单")
                else:
                    print("✗ 无法获取当前盘口，跳过挂卖单")

        # 保存初始卖单配置
        config.initial_sell_orders = initial_sell_orders

        # 8. 选择运行模式（所有input已完成，之后不再需要用户交互）
        print("\n[运行模式]")
        print("  1. 前台运行（关闭终端后停止）")
        print("  2. 后台运行（守护进程，关闭终端后继续运行）")
        mode_choice = input("请选择 (1/2, 默认1): ").strip()

        if mode_choice == '2':
            # 检查是否已有守护进程
            running, pid = DaemonProcess.is_running()
            if running:
                print(f"\n✗ 已有守护进程在运行 (PID: {pid})")
                print(f"  使用 'python trade.py stop' 停止")
                return

            print("\n正在启动后台守护进程...")
            # 转为守护进程
            DaemonProcess.daemonize()
            # 以下代码在守护进程中执行
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 守护进程启动")

        # 9. 启动做市商
        self._run_market_maker(config, selected_account_indices)

    def _configure_market_maker(self, market_id: int, token_id: str, market_title: str = "",
                                current_bid1: float = 0, current_ask1: float = 0):
        """交互式配置做市参数"""
        print(f"\n{'─'*40}")
        print("做市商参数配置")
        print(f"{'─'*40}")

        # 计算当前中间价供参考
        mid_price = (current_bid1 + current_ask1) / \
            2 if current_bid1 and current_ask1 else 0
        if mid_price:
            print(
                f"  当前买1: {self.format_price(current_bid1)}¢, 卖1: {self.format_price(current_ask1)}¢")
            print(f"  当前中间价: {self.format_price(mid_price)}¢")

        # ============ 仓位限制（强制必须设置）============
        print("\n[仓位限制] *** 必须设置，防止单边持仓过多 ***")
        print("  1. 按份额限制")
        print("  2. 按金额限制")
        print("  3. 按净资产百分比限制")

        max_shares = max_amount = max_percent = 0
        while True:
            limit_choice = input("请选择 (1-3): ").strip()
            if limit_choice == '1':
                shares_input = input("最大持仓份额: ").strip()
                if shares_input:
                    max_shares = int(shares_input)
                    if max_shares > 0:
                        break
                print("  [!] 请输入有效的份额限制")
            elif limit_choice == '2':
                amount_input = input("最大持仓金额（美元）: ").strip()
                if amount_input:
                    max_amount = float(amount_input)
                    if max_amount > 0:
                        break
                print("  [!] 请输入有效的金额限制")
            elif limit_choice == '3':
                percent_input = input("最大仓位百分比（如10表示10%）: ").strip()
                if percent_input:
                    max_percent = float(percent_input)
                    if max_percent > 0:
                        break
                print("  [!] 请输入有效的百分比限制")
            else:
                print("  [!] 请选择1、2或3")

        # ============ 价格边界保护（防止被带节奏）============
        print("\n[价格边界保护] 防止被恶意带节奏")
        print("  设置后，价格超出边界将暂停挂单")

        # 买入价格上限 (mid_price 是原始小数价格，如0.7455)
        if mid_price:
            suggested_max_buy = int((mid_price + 0.10) * 100)  # 建议：中间价+10分，取整
            max_buy_input = input(
                f"买入价格上限（分，建议{suggested_max_buy}，留空不限）: ").strip()
        else:
            max_buy_input = input("买入价格上限（分，留空不限）: ").strip()
        max_buy_price = float(max_buy_input) / \
            100 if max_buy_input else 0  # 转换为小数

        # 卖出价格下限
        if mid_price:
            suggested_min_sell = int((mid_price - 0.10) * 100)  # 建议：中间价-10分，取整
            min_sell_input = input(
                f"卖出价格下限（分，建议{suggested_min_sell}，留空不限）: ").strip()
        else:
            min_sell_input = input("卖出价格下限（分，留空不限）: ").strip()
        min_sell_price = float(min_sell_input) / \
            100 if min_sell_input else 0  # 转换为小数

        # 最大偏离度
        print("\n  偏离度保护: 相对于启动时中间价的最大偏离")
        deviation_input = input("最大价格偏离（分，如5表示±5分，留空不限）: ").strip()
        max_deviation = float(deviation_input) / \
            100 if deviation_input else 0  # 转换为小数

        # ============ 盘口深度验证 ============
        print("\n[盘口深度验证] 防止薄盘操控")
        print("  深度不足时将暂停挂单，等待深度恢复")
        depth_input = input("最小盘口深度（美元，建议100-1000，留空不限）: ").strip()
        min_depth = float(depth_input) if depth_input else 0

        # ============ 深度骤降保护 ============
        print("\n[深度骤降保护] 检测大量撤单时自动撤单")
        print("  当盘口深度在短时间内骤降时触发保护")
        depth_drop_enable = input("启用深度骤降保护？(y/n, 默认y): ").strip().lower()
        auto_cancel_on_depth_drop = depth_drop_enable != 'n'

        depth_drop_threshold = 50.0  # 默认50%
        depth_drop_window = 3  # 默认3次检查
        emergency_position_action = 'hold'
        emergency_sell_percent = 0

        if auto_cancel_on_depth_drop:
            threshold_input = input("深度骤降阈值（百分比，默认50，即下降50%触发）: ").strip()
            depth_drop_threshold = float(
                threshold_input) if threshold_input else 50.0

            window_input = input("检测窗口（检查次数，默认3）: ").strip()
            depth_drop_window = int(window_input) if window_input else 3

            # 紧急撤单时持仓处理方式
            print("\n  紧急撤单时，如果手中有持仓，如何处理？")
            print("    1. 只撤单，保留全部持仓（默认）")
            print("    2. 撤单后，市价卖出全部持仓")
            print("    3. 撤单后，市价卖出部分持仓，保留一定比例")
            position_action_choice = input("  请选择 (1-3, 默认1): ").strip() or '1'

            if position_action_choice == '2':
                print("\n  ⚠️  警告：市价卖出可能存在较大滑点！")
                print("     在盘口深度不足或剧烈波动时，实际成交价可能远低于预期。")
                print("  💡 提示：做市商推荐选择90¢以上的标的，风险更低。")
                confirm = input("  确认选择市价卖出全部？(y/n): ").strip().lower()
                if confirm == 'y':
                    emergency_position_action = 'sell_all'
                else:
                    print("  已改为保留全部持仓")
                    emergency_position_action = 'hold'
            elif position_action_choice == '3':
                print("\n  ⚠️  警告：市价卖出可能存在较大滑点！")
                print("     在盘口深度不足或剧烈波动时，实际成交价可能远低于预期。")
                print("  💡 提示：做市商推荐选择90¢以上的标的，风险更低。")
                sell_pct_input = input("  卖出比例（百分比，如60表示卖出60%保留40%）: ").strip()
                emergency_sell_percent = float(
                    sell_pct_input) if sell_pct_input else 50.0
                confirm = input(
                    f"  确认紧急时市价卖出{emergency_sell_percent}%？(y/n): ").strip().lower()
                if confirm == 'y':
                    emergency_position_action = 'sell_partial'
                else:
                    print("  已改为保留全部持仓")
                    emergency_position_action = 'hold'
                    emergency_sell_percent = 0
            else:
                emergency_position_action = 'hold'

        # ============ 价格参数 ============
        print("\n[价格参数]")
        print("  最小价差: 当买1和卖1价差小于此值时，暂停挂单")
        min_spread_input = input("最小价差阈值（分，默认0.1）: ").strip()
        min_spread = float(min_spread_input) if min_spread_input else 0.1

        print("  价格步长: 调整挂单价格的最小单位")
        price_step_input = input("价格调整步长（分，默认0.1）: ").strip()
        price_step = float(price_step_input) if price_step_input else 0.1

        # ============ 单笔金额 ============
        print("\n[单笔金额]")
        order_min_input = input("单笔最小金额（美元，默认5）: ").strip()
        order_min = float(order_min_input) if order_min_input else 5.0

        order_max_input = input("单笔最大金额（美元，默认20）: ").strip()
        order_max = float(order_max_input) if order_max_input else 20.0

        # ============ 止损设置 ============
        print("\n[止损设置] 选择一种止损方式:")
        print("  1. 按亏损百分比止损")
        print("  2. 按亏损金额止损")
        print("  3. 按价格止损")
        print("  0. 不设置止损")
        sl_choice = input("请选择 (0-3, 默认0): ").strip() or '0'

        sl_percent = sl_amount = sl_price = 0
        if sl_choice == '1':
            sl_percent = float(input("亏损百分比（如5表示亏5%止损）: ").strip() or '0')
        elif sl_choice == '2':
            sl_amount = float(input("亏损金额（美元）: ").strip() or '0')
        elif sl_choice == '3':
            sl_price = float(input("止损价格（分）: ").strip() or '0')

        # ============ 挂单策略选择 (二选一) ============
        print("\n[挂单策略选择] 网格策略与分层挂单二选一:")
        print("  1. 网格策略 - 追踪买入成本，买入后自动按 买入价+利润 挂卖单")
        print("  2. 分层挂单 - 在多个价格层级分散挂单，增加订单簿厚度")
        print("  0. 返回主菜单")
        strategy_choice = input("请选择 (0/1/2): ").strip()

        if strategy_choice == '0':
            print("返回主菜单...")
            return

        grid_enabled = False
        grid_profit_spread = 0.1
        grid_min_profit_spread = 0.05
        grid_levels = 5
        grid_level_spread = 0.1
        grid_amount_per_level = 10.0
        grid_auto_rebalance = True

        layered_enabled = False
        price_levels = [1]
        distribution_mode = 'uniform'
        custom_ratios = []

        if strategy_choice == '1':
            # ============ 网格策略配置 ============
            grid_enabled = True
            print("\n  网格参数配置:")
            print("  (例如: 买入价99.1 + 目标利润0.1 = 卖出价99.2)")

            # 利润价差
            profit_input = input("  目标利润(默认0.1): ").strip()
            grid_profit_spread = float(profit_input) if profit_input else 0.1

            # 最小利润价差
            min_profit_input = input("  最小利润(低于此值不卖，默认0.05): ").strip()
            grid_min_profit_spread = float(
                min_profit_input) if min_profit_input else 0.05

            # 网格层数
            levels_input = input("  网格层数（默认5）: ").strip()
            grid_levels = int(levels_input) if levels_input else 5

            # 层间距
            spread_input = input("  每层间隔(默认0.1): ").strip()
            grid_level_spread = float(spread_input) if spread_input else 0.1

            # 每层金额
            amount_input = input("  每层挂单金额（美元，默认10）: ").strip()
            grid_amount_per_level = float(
                amount_input) if amount_input else 10.0

            # 自动再平衡
            rebalance_input = input(
                "  卖出后自动在买1价重新挂买? (y/n, 默认y): ").strip().lower()
            grid_auto_rebalance = rebalance_input != 'n'

            print(f"\n  ✓ 网格策略已启用")
            print(f"    利润价差: {grid_profit_spread}")
            print(f"    网格层数: {grid_levels} 层")
            print(f"    层间距: {grid_level_spread}")
            print(f"    每层金额: ${grid_amount_per_level}")
            print(f"    自动再平衡: {'是' if grid_auto_rebalance else '否'}")

        elif strategy_choice == '2':
            # ============ 分层挂单配置 ============
            layered_enabled = True
            print("  设置价格层级（在哪些盘口深度挂单）")
            print("  示例: 1 5 10 表示在买1/卖1、买5/卖5、买10/卖10挂单")
            print("  常用: 1 3 5 7 10 或 1 2 3 4 5")

            levels_input = input("  价格层级 (默认 1 5 10): ").strip()
            if levels_input:
                try:
                    price_levels = [int(x) for x in levels_input.split()]
                    price_levels = sorted(set(price_levels))
                    if not all(x > 0 for x in price_levels):
                        raise ValueError("层级必须为正整数")
                except ValueError:
                    print("  [!] 格式错误，使用默认值")
                    price_levels = [1, 5, 10]
            else:
                price_levels = [1, 5, 10]

            print(f"  ✓ 价格层级: {price_levels}")

            # 分布模式
            print("\n  选择分布模式:")
            print("    1. 均匀分布（每层相等）")
            print("    2. 金字塔（第1层少，最后一层多）")
            print("    3. 倒金字塔（第1层多，最后一层少）")
            print("    4. 自定义比例")

            dist_choice = input("  请选择 (1-4，默认1): ").strip() or '1'
            dist_map = {'1': 'uniform', '2': 'pyramid',
                        '3': 'inverse_pyramid', '4': 'custom'}
            distribution_mode = dist_map.get(dist_choice, 'uniform')

            if distribution_mode == 'custom':
                print(f"  请输入各层的分配比例，共{len(price_levels)}层")
                print(f"  示例: 1 2 3 表示按 1:2:3 分配")
                while True:
                    ratios_input = input(
                        f"  分配比例 ({len(price_levels)}个数字): ").strip()
                    try:
                        custom_ratios = [float(x)
                                         for x in ratios_input.split()]
                        if len(custom_ratios) != len(price_levels):
                            print(f"  [!] 需要输入{len(price_levels)}个数字")
                            continue
                        if not all(x > 0 for x in custom_ratios):
                            print("  [!] 比例必须为正数")
                            continue
                        break
                    except ValueError:
                        print("  [!] 格式错误，请输入数字")

            dist_names = {'uniform': '垂直分布', 'pyramid': '金字塔',
                          'inverse_pyramid': '倒金字塔', 'custom': '自定义'}
            print(f"  ✓ 分布模式: {dist_names[distribution_mode]}")

        # 买卖共用分层配置
        layered_sell_enabled = layered_enabled
        sell_price_levels = price_levels
        sell_distribution_mode = distribution_mode
        sell_custom_ratios = custom_ratios

        layered_buy_enabled = layered_enabled
        buy_price_levels = price_levels
        buy_distribution_mode = distribution_mode
        buy_custom_ratios = custom_ratios

        # ============ 成本加成卖出配置 ============
        print("\n[成本加成卖出] 卖出价 = 平均买入成本 + 利润价差")
        print("  启用后卖单不再跟随市场价下跌，而是根据买入成本定价")
        cost_choice = input("是否启用成本加成定价? (y/n, 默认n): ").strip().lower()
        cost_based_sell_enabled = cost_choice == 'y'

        sell_profit_spread = 1.0
        min_cost_profit_spread = 0.5

        if cost_based_sell_enabled:
            profit_input = input("  卖出利润价差（分，默认1）: ").strip()
            sell_profit_spread = float(profit_input) if profit_input else 1.0

            min_input = input("  最小利润价差（分，默认0.5）: ").strip()
            min_cost_profit_spread = float(min_input) if min_input else 0.5

            print(f"\n  ✓ 成本加成已启用: 卖出价 = 均价 + {sell_profit_spread}¢")

        # ============ 运行参数 ============
        print("\n[运行参数]")
        interval_input = input("盘口检查间隔（秒，默认2）: ").strip()
        check_interval = float(interval_input) if interval_input else 2.0

        # ============ WebSocket 模式 ============
        print("\n[数据模式]")
        print("  1. 轮询模式（传统，稳定）")
        print("  2. WebSocket 模式（实时推送，低延迟）")
        ws_choice = input("请选择 (1/2, 默认2): ").strip()
        use_websocket = ws_choice != '1'  # 默认使用 WebSocket
        if use_websocket:
            print("  ✓ 已启用 WebSocket 实时数据模式")
        else:
            print("  ✓ 使用轮询模式")

        return MarketMakerConfig(
            market_id=market_id,
            token_id=token_id,
            market_title=market_title,
            min_spread=min_spread,
            price_step=price_step,
            max_buy_price=max_buy_price,
            min_sell_price=min_sell_price,
            max_price_deviation=max_deviation,
            min_orderbook_depth=min_depth,
            order_amount_min=order_min,
            order_amount_max=order_max,
            max_position_shares=max_shares,
            max_position_amount=max_amount,
            max_position_percent=max_percent,
            stop_loss_percent=sl_percent,
            stop_loss_amount=sl_amount,
            stop_loss_price=sl_price,
            check_interval=check_interval,
            depth_drop_threshold=depth_drop_threshold,
            depth_drop_window=depth_drop_window,
            auto_cancel_on_depth_drop=auto_cancel_on_depth_drop,
            emergency_position_action=emergency_position_action,
            emergency_sell_percent=emergency_sell_percent,
            # 分层挂单配置
            layered_sell_enabled=layered_sell_enabled,
            sell_price_levels=sell_price_levels,
            sell_distribution_mode=sell_distribution_mode,
            sell_custom_ratios=sell_custom_ratios,
            layered_buy_enabled=layered_buy_enabled,
            buy_price_levels=buy_price_levels,
            buy_distribution_mode=buy_distribution_mode,
            buy_custom_ratios=buy_custom_ratios,
            # 成本加成卖出配置
            cost_based_sell_enabled=cost_based_sell_enabled,
            sell_profit_spread=sell_profit_spread,
            min_cost_profit_spread=min_cost_profit_spread,
            # 网格策略配置
            grid_enabled=grid_enabled,
            grid_profit_spread=grid_profit_spread,
            grid_min_profit_spread=grid_min_profit_spread,
            grid_levels=grid_levels,
            grid_level_spread=grid_level_spread,
            grid_amount_per_level=grid_amount_per_level,
            grid_auto_rebalance=grid_auto_rebalance,
            use_websocket=use_websocket
        )

    def _mm_show_orderbook(self, client, token_id: str) -> tuple:
        """显示当前盘口信息（左右对称：买盘左边 | 卖盘右边）
        返回: (bid1_price, ask1_price)
        """
        bid1_price = 0
        ask1_price = 0
        ob = OrderbookService.fetch_and_display(
            client, token_id,
            title="盘口信息",
            mode=OrderbookDisplay.MODE_SIMPLE,
            max_rows=10,
            format_price_func=self.format_price
        )
        if ob['success']:
            bid1_price = ob['bid1_price']
            ask1_price = ob['ask1_price']

        return (bid1_price, ask1_price)

    def _mm_show_config(self, config: MarketMakerConfig, account_indices: list):
        """显示配置确认信息"""
        print(f"\n{'='*60}")
        print(f"{'做市商配置确认':^60}")
        print(f"{'='*60}")
        print(f"  参与账户: {len(account_indices)}个")
        print(f"  市场: {config.market_title or config.market_id}")
        print(f"  Token ID: {config.token_id}")

        print(f"\n  [仓位限制] (必须)")
        if config.max_position_shares > 0:
            print(f"    最大持仓: {config.max_position_shares}份")
        elif config.max_position_amount > 0:
            print(f"    最大持仓: ${config.max_position_amount}")
        elif config.max_position_percent > 0:
            print(f"    最大持仓: {config.max_position_percent}%净资产")

        print(f"\n  [价格边界保护]")
        if config.max_buy_price > 0:
            print(f"    买入上限: {self.format_price(config.max_buy_price)}¢")
        else:
            print(f"    买入上限: 不限制")
        if config.min_sell_price > 0:
            print(f"    卖出下限: {self.format_price(config.min_sell_price)}¢")
        else:
            print(f"    卖出下限: 不限制")
        if config.max_price_deviation > 0:
            print(f"    最大偏离: ±{config.max_price_deviation}¢")
        else:
            print(f"    偏离保护: 不限制")

        print(f"\n  [盘口深度验证]")
        if config.min_orderbook_depth > 0:
            print(f"    最小深度: ${config.min_orderbook_depth} (低于此深度暂停)")
        else:
            print(f"    不验证深度")

        print(f"\n  [深度骤降保护]")
        if config.auto_cancel_on_depth_drop:
            print(f"    已启用: 深度下降{config.depth_drop_threshold}%时紧急撤单")
            print(f"    检测窗口: {config.depth_drop_window}次检查")
            # 显示持仓处理方式
            if config.emergency_position_action == 'hold':
                print(f"    持仓处理: 只撤单，保留全部持仓")
            elif config.emergency_position_action == 'sell_all':
                print(f"    持仓处理: 撤单后市价卖出全部持仓")
            elif config.emergency_position_action == 'sell_partial':
                print(
                    f"    持仓处理: 卖出{config.emergency_sell_percent}%，保留{100-config.emergency_sell_percent}%")
        else:
            print(f"    未启用")

        print(f"\n  [价格参数]")
        print(f"    最小价差: {config.min_spread}¢")
        print(f"    价格步长: {config.price_step}¢")

        print(f"\n  [单笔金额]")
        print(
            f"    范围: ${config.order_amount_min} - ${config.order_amount_max}")

        print(f"\n  [止损设置]")
        if config.stop_loss_percent > 0:
            print(f"    亏损{config.stop_loss_percent}%止损")
        elif config.stop_loss_amount > 0:
            print(f"    亏损${config.stop_loss_amount}止损")
        elif config.stop_loss_price > 0:
            print(f"    跌破{config.stop_loss_price}¢止损")
        else:
            print(f"    不设置止损")

        print(f"\n  [运行参数]")
        print(f"    检查间隔: {config.check_interval}秒")
        print(
            f"    数据模式: {'WebSocket 实时推送' if config.use_websocket else '轮询模式'}")

        # 分层挂单配置
        dist_names = {'uniform': '垂直分布', 'pyramid': '金字塔',
                      'inverse_pyramid': '倒金字塔', 'custom': '自定义'}

        print(f"\n  [分层挂单]")
        if config.layered_sell_enabled or config.layered_buy_enabled:
            print(f"    已启用")
            print(f"    层级: {config.sell_price_levels}")
            print(
                f"    分布: {dist_names.get(config.sell_distribution_mode, '垂直分布')}")
        else:
            print(f"    未启用（仅在买1/卖1挂单）")

    def _batch_market_maker_menu(self, selected_account_indices: list):
        """批量多市场做市配置入口"""
        print(f"\n{'='*60}")
        print(f"{'批量多市场做市配置':^60}")
        print(f"{'='*60}")
        print("说明: 为多个市场分配不同账户进行做市")
        print("      每个市场可以分配一个或多个账户")

        # 1. 输入多个市场ID
        print("\n请输入市场ID列表（逗号分隔，如: 123,456,789）")
        market_ids_input = input("市场IDs: ").strip()
        if not market_ids_input:
            return

        try:
            market_ids = [int(x.strip()) for x in market_ids_input.split(',')]
            market_ids = list(set(market_ids))  # 去重
        except ValueError:
            print("✗ 请输入有效的数字列表")
            return

        print(f"\n将配置 {len(market_ids)} 个市场: {market_ids}")

        # 2. 获取每个市场的信息
        client = self.clients[0]
        market_configs = []  # 存储每个市场的配置信息

        for market_id in market_ids:
            print(f"\n{'─'*40}")
            print(f"配置市场 {market_id}")
            print(f"{'─'*40}")

            try:
                # 获取市场信息
                categorical_response = client.get_categorical_market(
                    market_id=market_id)

                if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                    market_data = categorical_response.result.data
                    if hasattr(market_data, 'child_markets') and market_data.child_markets:
                        child_markets = market_data.child_markets
                        print(f"✓ 分类市场: {market_data.market_title}")
                        print(f"子市场列表:")
                        for i, child in enumerate(child_markets, 1):
                            child_title = child.market_title if hasattr(
                                child, 'market_title') else f"子市场{i}"
                            print(f"  {i}. {child_title}")

                        child_choice = input(
                            f"选择子市场 (1-{len(child_markets)}): ").strip()
                        try:
                            child_idx = int(child_choice) - 1
                            if 0 <= child_idx < len(child_markets):
                                selected_child = child_markets[child_idx]
                                market_id = selected_child.market_id
                                # 获取子市场详细信息（包含token_id）
                                child_response = client.get_market(
                                    market_id=market_id)
                                if child_response.errno != 0 or not child_response.result or not child_response.result.data:
                                    print(f"✗ 无法获取子市场详细信息")
                                    continue
                                market_data = child_response.result.data
                            else:
                                print("✗ 跳过此市场")
                                continue
                        except ValueError:
                            print("✗ 跳过此市场")
                            continue
                else:
                    market_response = client.get_market(market_id=market_id)
                    if market_response.errno != 0:
                        print(f"✗ 无法获取市场: {market_response.errmsg}")
                        continue
                    market_data = market_response.result.data
                    print(f"✓ 市场: {market_data.market_title}")

                # 选择YES/NO
                print("交易方向: 1=YES, 2=NO")
                side_choice = input("选择 (1/2): ").strip()
                if side_choice == '1':
                    token_id = market_data.yes_token_id if hasattr(
                        market_data, 'yes_token_id') else None
                    token_name = "YES"
                elif side_choice == '2':
                    token_id = market_data.no_token_id if hasattr(
                        market_data, 'no_token_id') else None
                    token_name = "NO"
                else:
                    print("✗ 跳过此市场")
                    continue

                if not token_id:
                    print("✗ 无法获取Token ID")
                    continue

                # 选择要分配的账户
                print(f"\n可用账户: {selected_account_indices}")
                acc_input = input("分配账户 (逗号分隔，如 1,2,3，或 'all'): ").strip()
                if acc_input.lower() == 'all':
                    assigned_accounts = selected_account_indices.copy()
                else:
                    try:
                        assigned_accounts = [int(x.strip())
                                             for x in acc_input.split(',')]
                        assigned_accounts = [
                            a for a in assigned_accounts if a in selected_account_indices]
                    except ValueError:
                        print("✗ 跳过此市场")
                        continue

                if not assigned_accounts:
                    print("✗ 没有有效账户")
                    continue

                market_configs.append({
                    'market_id': market_id,
                    'market_title': f"{market_data.market_title} - {token_name}",
                    'token_id': token_id,
                    'accounts': assigned_accounts
                })
                print(f"✓ 已配置: {len(assigned_accounts)}个账户")

            except Exception as e:
                print(f"✗ 异常: {e}")
                continue

        if not market_configs:
            print("\n✗ 没有有效的市场配置")
            return

        # 3. 配置统一的做市参数
        print(f"\n{'='*60}")
        print(f"{'配置统一的做市参数（将应用于所有市场）':^60}")
        print(f"{'='*60}")

        # 使用第一个市场的盘口作为价格参考
        first_config = market_configs[0]
        current_bid1, current_ask1 = self._mm_show_orderbook(
            client, first_config['token_id'])

        # 配置做市参数
        base_config = self._configure_market_maker(
            first_config['market_id'],
            first_config['token_id'],
            first_config['market_title'],
            current_bid1, current_ask1
        )
        if not base_config:
            return

        # 4. 显示所有配置
        print(f"\n{'='*60}")
        print(f"{'批量做市配置确认':^60}")
        print(f"{'='*60}")
        print(f"共 {len(market_configs)} 个市场:")
        for mc in market_configs:
            print(f"  • {mc['market_title']}")
            print(f"    账户: {mc['accounts']}")

        # 显示公共配置
        print(f"\n[统一参数]")
        print(f"  仓位限制: ", end="")
        if base_config.max_position_shares > 0:
            print(f"{base_config.max_position_shares}份")
        elif base_config.max_position_amount > 0:
            print(f"${base_config.max_position_amount}")
        elif base_config.max_position_percent > 0:
            print(f"{base_config.max_position_percent}%净资产")
        print(f"  最小价差: {base_config.min_spread}¢")
        print(f"  价格步长: {base_config.price_step}¢")
        print(
            f"  单笔金额: ${base_config.order_amount_min}-${base_config.order_amount_max}")

        confirm = input("\n确认开始批量做市？输入 'start' 启动: ").strip().lower()
        if confirm != 'start':
            print("✗ 已取消")
            return

        # 5. 选择运行模式
        print("\n[运行模式]")
        print("  1. 前台运行（关闭终端后停止）")
        print("  2. 后台运行（守护进程，关闭终端后继续运行）")
        mode_choice = input("请选择 (1/2, 默认1): ").strip()

        if mode_choice == '2':
            # 检查是否已有守护进程
            running, pid = DaemonProcess.is_running()
            if running:
                print(f"\n✗ 已有守护进程在运行 (PID: {pid})")
                print(f"  使用 'python trade.py stop' 停止")
                return

            print("\n正在启动后台守护进程...")
            # 转为守护进程
            DaemonProcess.daemonize()
            # 以下代码在守护进程中执行
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 守护进程启动")

        # 6. 启动批量做市
        self._run_batch_market_maker(market_configs, base_config)

    def _run_batch_market_maker(self, market_configs: list, base_config: MarketMakerConfig):
        """运行批量多市场做市"""
        import threading
        import copy

        print(f"\n{'='*60}")
        print(f"批量做市商已启动 ({len(market_configs)}个市场)")
        print("按 Ctrl+C 停止")
        print(f"{'='*60}")

        all_states = {}  # {(market_id, acc_idx): state}
        threads = []
        stop_event = threading.Event()

        for mc in market_configs:
            # 为每个市场创建独立配置
            config = copy.deepcopy(base_config)
            config.market_id = mc['market_id']
            config.token_id = mc['token_id']
            config.market_title = mc['market_title']

            for acc_idx in mc['accounts']:
                state = MarketMakerState(is_running=True)
                all_states[(mc['market_id'], acc_idx)] = state

                t = threading.Thread(
                    target=self._run_single_account_market_maker,
                    args=(acc_idx, config, state, stop_event),
                    daemon=True
                )
                threads.append(t)

        # 启动所有线程
        for t in threads:
            t.start()
            time.sleep(0.2)  # 错开启动时间

        # 等待用户中断
        try:
            while True:
                time.sleep(1)
                all_stopped = all(
                    not s.is_running for s in all_states.values())
                if all_stopped:
                    break
        except KeyboardInterrupt:
            print(f"\n\n正在停止所有做市商...")
            stop_event.set()
            for state in all_states.values():
                state.is_running = False

        # 等待所有线程结束
        for t in threads:
            t.join(timeout=5)

        # 显示汇总
        self._mm_show_batch_summary(market_configs, all_states)

    def _mm_show_batch_summary(self, market_configs: list, all_states: dict):
        """显示批量做市汇总（增强版）"""
        print(f"\n{'='*60}")
        print(f"{'批量做市汇总':^60}")
        print(f"{'='*60}")

        # 总统计
        grand_total_pnl = 0
        grand_total_buy_shares = 0
        grand_total_sell_shares = 0
        grand_total_buy_cost = 0
        grand_total_sell_revenue = 0
        grand_total_trades = 0

        for mc in market_configs:
            print(f"\n┌{'─'*56}┐")
            print(f"│ [市场] {mc['market_title'][:48]}")
            print(f"├{'─'*56}┤")

            market_pnl = 0
            market_buy_shares = 0
            market_sell_shares = 0
            market_buy_cost = 0
            market_sell_revenue = 0
            market_trades = 0

            for acc_idx in mc['accounts']:
                state = all_states.get((mc['market_id'], acc_idx))
                if state:
                    cfg = self.configs[acc_idx - 1]

                    # 记录结束时间
                    state.end_time = time.time()

                    trades = state.buy_trade_count + state.sell_trade_count
                    pnl_str = f"+${state.realized_pnl:.4f}" if state.realized_pnl >= 0 else f"-${abs(state.realized_pnl):.4f}"

                    # 计算运行时长
                    duration = state.end_time - state.start_time if state.start_time > 0 else 0
                    minutes = int(duration // 60)
                    duration_str = f"{minutes}分" if minutes > 0 else f"{int(duration)}秒"

                    print(
                        f"│   {cfg.remark}: 买{state.total_buy_shares}份 卖{state.total_sell_shares}份 | {trades}笔 | {pnl_str} | {duration_str}")

                    market_pnl += state.realized_pnl
                    market_buy_shares += state.total_buy_shares
                    market_sell_shares += state.total_sell_shares
                    market_buy_cost += state.total_buy_cost
                    market_sell_revenue += state.total_sell_revenue
                    market_trades += trades

            # 市场小计
            net_pos = market_buy_shares - market_sell_shares
            net_str = f"+{net_pos}" if net_pos > 0 else str(net_pos)
            market_pnl_str = f"+${market_pnl:.4f}" if market_pnl >= 0 else f"-${abs(market_pnl):.4f}"

            print(f"├{'─'*56}┤")
            print(
                f"│ 小计: 买{market_buy_shares}份 卖{market_sell_shares}份 净{net_str}份 | {market_trades}笔")
            print(f"│ 盈亏: {market_pnl_str}")
            print(f"└{'─'*56}┘")

            grand_total_pnl += market_pnl
            grand_total_buy_shares += market_buy_shares
            grand_total_sell_shares += market_sell_shares
            grand_total_buy_cost += market_buy_cost
            grand_total_sell_revenue += market_sell_revenue
            grand_total_trades += market_trades

        # 总汇总
        print(f"\n{'='*60}")
        print(f"{'全部市场汇总':^60}")
        print(f"{'='*60}")
        print(f"  总交易: {grand_total_trades}笔")
        print(
            f"  总买入: {grand_total_buy_shares}份, 成本${grand_total_buy_cost:.2f}")
        print(
            f"  总卖出: {grand_total_sell_shares}份, 收入${grand_total_sell_revenue:.2f}")

        net_pos = grand_total_buy_shares - grand_total_sell_shares
        if net_pos != 0:
            net_str = f"+{net_pos}" if net_pos > 0 else str(net_pos)
            print(f"  净持仓变化: {net_str}份")

        # 总盈亏
        pnl_str = f"+${grand_total_pnl:.4f}" if grand_total_pnl >= 0 else f"-${abs(grand_total_pnl):.4f}"
        print(f"\n  总盈亏: {pnl_str}")

        if grand_total_buy_cost > 0:
            pnl_rate = (grand_total_pnl / grand_total_buy_cost) * 100
            rate_str = f"+{pnl_rate:.2f}%" if pnl_rate >= 0 else f"{pnl_rate:.2f}%"
            print(f"    盈亏率: {rate_str}")

        print(f"{'='*60}")

    def _run_market_maker(self, config: MarketMakerConfig, account_indices: list):
        """运行做市商 - 多账户并行"""
        # 注意：持仓检查和初始卖单配置已在 market_maker_menu 中完成
        # config.initial_sell_orders 已经设置好

        # 根据配置选择运行模式
        if config.use_websocket:
            self._run_market_maker_websocket(config, account_indices)
        else:
            self._run_market_maker_polling(config, account_indices)

    def _run_market_maker_polling(self, config: MarketMakerConfig, account_indices: list):
        """运行做市商 - 轮询模式（原有逻辑）"""
        import threading
        import copy

        print(f"\n{'='*60}")
        print(f"{'做市商已启动 [轮询模式]':^60}")
        print("按 Ctrl+C 停止")
        print(f"{'='*60}")

        # 为每个账户创建独立的状态
        states = {}
        threads = []
        stop_event = threading.Event()

        for acc_idx in account_indices:
            state = MarketMakerState(is_running=True)
            states[acc_idx] = state

            # 创建线程
            t = threading.Thread(
                target=self._run_single_account_market_maker,
                args=(acc_idx, config, state, stop_event),
                daemon=True
            )
            threads.append(t)

        # 启动所有线程
        for t in threads:
            t.start()

        # 等待用户中断
        try:
            while True:
                time.sleep(1)
                # 检查是否所有账户都已停止
                all_stopped = all(not s.is_running for s in states.values())
                if all_stopped:
                    break
        except KeyboardInterrupt:
            print(f"\n\n正在停止做市商...")
            stop_event.set()
            for acc_idx in account_indices:
                states[acc_idx].is_running = False

            # 主动撤销所有挂单
            print(f"正在撤销所有挂单...")
            for acc_idx in account_indices:
                try:
                    client = self.clients[acc_idx - 1]
                    cfg = self.configs[acc_idx - 1]
                    state = states[acc_idx]
                    cancelled = 0
                    if state.buy_order_id:
                        if self._mm_cancel_order_safe(client, state.buy_order_id):
                            cancelled += 1
                        state.buy_order_id = None
                    if state.sell_order_id:
                        if self._mm_cancel_order_safe(client, state.sell_order_id):
                            cancelled += 1
                        state.sell_order_id = None
                    if cancelled > 0:
                        print(f"  [{cfg.remark}] ✓ 已撤销 {cancelled} 个挂单")
                except Exception as e:
                    print(f"  [{cfg.remark}] ✗ 撤单异常: {e}")
            print(f"✓ 撤单完成")

        # 等待所有线程结束
        for t in threads:
            t.join(timeout=5)

        # 显示汇总
        self._mm_show_summary(states)

    def _run_market_maker_websocket(self, config: MarketMakerConfig, account_indices: list):
        """运行做市商 - WebSocket 实时模式"""
        import threading

        print(f"\n{'='*60}")
        print(f"{'做市商已启动 [WebSocket 实时模式]':^60}")
        print("按 Ctrl+C 停止")
        print(f"{'='*60}")

        # 使用第一个账户的 API Key 连接 WebSocket
        api_key = self.configs[account_indices[0] - 1].api_key

        # 共享的盘口数据
        shared_orderbook = {
            'bids': {},  # price -> size
            'asks': {},  # price -> size
            'last_update': None,
            'lock': threading.Lock()
        }

        # 为每个账户创建独立的状态
        states = {}
        threads = []
        stop_event = threading.Event()

        for acc_idx in account_indices:
            state = MarketMakerState(is_running=True)
            states[acc_idx] = state

            # 创建做市线程
            t = threading.Thread(
                target=self._run_single_account_market_maker_ws,
                args=(acc_idx, config, state, stop_event, shared_orderbook),
                daemon=True
            )
            threads.append(t)

        # WebSocket 数据更新回调
        def on_orderbook_update(data):
            """处理 market.depth.diff 消息
            数据格式: {
                "channel": "market.depth.diff",
                "marketId": 123,
                "data": {
                    "bids": [{"price": "0.45", "size": "100"}, ...],
                    "asks": [{"price": "0.55", "size": "50"}, ...]
                }
            }
            """
            with shared_orderbook['lock']:
                depth_data = data.get('data', data)  # 兼容不同格式

                # 处理 bids
                bids = depth_data.get('bids', [])
                for bid in bids:
                    price = bid.get('price')
                    size = float(bid.get('size', 0))
                    if price:
                        if size == 0:
                            shared_orderbook['bids'].pop(price, None)
                        else:
                            shared_orderbook['bids'][price] = size

                # 处理 asks
                asks = depth_data.get('asks', [])
                for ask in asks:
                    price = ask.get('price')
                    size = float(ask.get('size', 0))
                    if price:
                        if size == 0:
                            shared_orderbook['asks'].pop(price, None)
                        else:
                            shared_orderbook['asks'][price] = size

                # 只要有数据就更新时间戳
                if bids or asks:
                    shared_orderbook['last_update'] = time.time()

        def on_trade_update(data):
            # 记录成交信息
            side = data.get('side', '')
            price = float(data.get('price', 0))
            shares = int(data.get('shares', 0))
            outcome = 'Yes' if data.get('outcomeSide') == 1 else 'No'
            cost = shares * price / 100  # 成本（美元）

            if side.upper() == 'BUY':
                print(
                    f"[{config.remark}] 买入成交 {shares}份 @ {price:.2f}¢, 成本${cost:.2f}")
            else:
                print(f"[{config.remark}] 卖出成交 {shares}份 @ {price:.2f}¢")

        # 创建 WebSocket 服务
        ws_service = OpinionWebSocket(
            api_key=api_key,
            on_orderbook=on_orderbook_update,
            on_trade=on_trade_update
        )

        async def ws_main():
            # 连接 WebSocket
            if not await ws_service.connect():
                print("✗ WebSocket 连接失败，回退到轮询模式")
                return False

            # 订阅订单簿和成交
            await ws_service.subscribe_orderbook(config.market_id)
            await ws_service.subscribe_trade(config.market_id)

            # 启动接收消息循环
            await ws_service.receive_loop()
            return True

        # 在后台线程运行 WebSocket
        ws_thread = None
        ws_loop = None

        def run_ws():
            nonlocal ws_loop
            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            try:
                ws_loop.run_until_complete(ws_main())
            except Exception as e:
                print(f"WebSocket 错误: {e}")
            finally:
                # 取消所有未完成的任务，避免 "Task was destroyed" 警告
                try:
                    pending = asyncio.all_tasks(ws_loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        ws_loop.run_until_complete(asyncio.gather(
                            *pending, return_exceptions=True))
                except Exception:
                    pass
                ws_loop.close()

        ws_thread = threading.Thread(target=run_ws, daemon=True)
        ws_thread.start()

        # 等待 WebSocket 连接建立
        time.sleep(1)

        # 获取初始订单簿快照（因为 market.depth.diff 只发送增量更新）
        print(f"  正在获取初始盘口快照 (token_id={config.token_id})...")
        client = self.clients[account_indices[0] - 1]
        ob = OrderbookService.fetch(client, config.token_id)
        if ob['success'] and ob.get('raw'):
            orderbook = ob['raw']
            with shared_orderbook['lock']:
                # 初始化买盘
                if orderbook.bids:
                    for bid in orderbook.bids:
                        shared_orderbook['bids'][bid.price] = float(bid.size)
                # 初始化卖盘
                if orderbook.asks:
                    for ask in orderbook.asks:
                        shared_orderbook['asks'][ask.price] = float(ask.size)
                if orderbook.bids or orderbook.asks:
                    shared_orderbook['last_update'] = time.time()
                    print(
                        f"  ✓ 已获取初始盘口快照 (买{len(orderbook.bids or [])}档, 卖{len(orderbook.asks or [])}档)")
                else:
                    print(f"  [!] 盘口为空 (买0档, 卖0档)")
        else:
            error_msg = ob.get('error', '未知错误')
            print(f"  [!] 获取初始盘口失败: {error_msg}")

        # 启动所有做市线程
        for t in threads:
            t.start()

        # 等待用户中断
        try:
            while True:
                time.sleep(1)
                all_stopped = all(not s.is_running for s in states.values())
                if all_stopped:
                    break
        except KeyboardInterrupt:
            print(f"\n\n正在停止做市商...")
            stop_event.set()
            for acc_idx in account_indices:
                states[acc_idx].is_running = False

            # 主动撤销所有挂单
            print(f"正在撤销所有挂单...")
            for acc_idx in account_indices:
                try:
                    client = self.clients[acc_idx - 1]
                    cfg = self.configs[acc_idx - 1]
                    state = states[acc_idx]
                    cancelled = 0
                    if state.buy_order_id:
                        if self._mm_cancel_order_safe(client, state.buy_order_id):
                            cancelled += 1
                        state.buy_order_id = None
                    if state.sell_order_id:
                        if self._mm_cancel_order_safe(client, state.sell_order_id):
                            cancelled += 1
                        state.sell_order_id = None
                    if cancelled > 0:
                        print(f"  [{cfg.remark}] ✓ 已撤销 {cancelled} 个挂单")
                except Exception as e:
                    print(f"  [{cfg.remark}] ✗ 撤单异常: {e}")
            print(f"✓ 撤单完成")

            # 停止 WebSocket（使用安全方式避免错误）
            if ws_loop:
                try:
                    if not ws_loop.is_closed() and ws_loop.is_running():
                        ws_loop.call_soon_threadsafe(ws_loop.stop)
                except Exception:
                    pass  # 忽略事件循环已关闭的错误

        # 等待所有线程结束
        for t in threads:
            t.join(timeout=5)

        # 显示汇总
        self._mm_show_summary(states)

    def _run_single_account_market_maker_ws(self, acc_idx: int, config: MarketMakerConfig,
                                            state: MarketMakerState, stop_event: threading.Event,
                                            shared_orderbook: dict):
        """单账户做市循环 - WebSocket 版本"""
        client = self.clients[acc_idx - 1]
        cfg = self.configs[acc_idx - 1]

        # 记录做市开始时间
        state.start_time = time.time()
        print(f"[{cfg.remark}] 做市开始 (WebSocket)")

        # 等待首次盘口数据
        wait_count = 0
        while not shared_orderbook['last_update'] and wait_count < 10:
            time.sleep(0.5)
            wait_count += 1

        if not shared_orderbook['last_update']:
            print(f"[{cfg.remark}] ✗ 未收到盘口数据，退出")
            state.is_running = False
            return

        # 记录启动时的参考价
        with shared_orderbook['lock']:
            if shared_orderbook['bids'] and shared_orderbook['asks']:
                bid_prices = sorted(
                    [float(p) for p in shared_orderbook['bids'].keys()], reverse=True)
                ask_prices = sorted([float(p)
                                    for p in shared_orderbook['asks'].keys()])
                if bid_prices and ask_prices:
                    state.reference_bid1 = bid_prices[0]
                    state.reference_ask1 = ask_prices[0]
                    state.reference_mid_price = (
                        state.reference_bid1 + state.reference_ask1) / 2
                    print(f"[{cfg.remark}] 参考价: 买1={self.format_price(state.reference_bid1)}¢, "
                          f"卖1={self.format_price(state.reference_ask1)}¢")

        # 处理初始卖单（现有持仓挂卖）
        initial_sell_orders = getattr(config, 'initial_sell_orders', {})
        if acc_idx in initial_sell_orders:
            sell_info = initial_sell_orders[acc_idx]
            try:
                order = PlaceOrderDataInput(
                    marketId=config.market_id,
                    tokenId=config.token_id,
                    side=OrderSide.SELL,
                    orderType=LIMIT_ORDER,
                    price=f"{sell_info['price']:.6f}",
                    shares=sell_info['shares']
                )
                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    state.sell_order_id = result.result.order_id
                    state.sell_order_price = sell_info['price']
                    state.position_shares = sell_info['shares']
                    state.position_cost = sell_info['price'] * \
                        sell_info['shares']
                    print(
                        f"[{cfg.remark}] ✓ 现有持仓已挂卖单: {sell_info['shares']}份 @ {self.format_price(sell_info['price'])}¢")
                else:
                    print(f"[{cfg.remark}] ✗ 挂卖单失败: {result.errmsg}")
            except Exception as e:
                print(f"[{cfg.remark}] ✗ 挂卖单异常: {e}")

        # 同时挂初始买单（如果未达持仓上限）
        position_ok = self._mm_check_position_limit(client, cfg, config, state)
        if position_ok:
            # 获取当前买1价
            with shared_orderbook['lock']:
                if shared_orderbook['bids']:
                    bid_prices = sorted(
                        [float(p) for p in shared_orderbook['bids'].keys()], reverse=True)
                    if bid_prices:
                        bid1_price = bid_prices[0]
                        initial_buy_price = bid1_price
                        # 检查边界
                        if config.max_buy_price > 0 and initial_buy_price > config.max_buy_price:
                            initial_buy_price = config.max_buy_price
                        try:
                            initial_amount = random.uniform(
                                config.order_amount_min, config.order_amount_max)
                            buy_order = PlaceOrderDataInput(
                                marketId=config.market_id,
                                tokenId=config.token_id,
                                side=OrderSide.BUY,
                                orderType=LIMIT_ORDER,
                                price=f"{initial_buy_price:.6f}",
                                makerAmountInQuoteToken=round(
                                    initial_amount, 2)
                            )
                            result = client.place_order(
                                buy_order, check_approval=True)
                            if result.errno == 0:
                                state.buy_order_id = result.result.order_id
                                state.buy_order_price = initial_buy_price
                                print(
                                    f"[{cfg.remark}] ✓ 初始买单: ${initial_amount:.2f} @ {self.format_price(initial_buy_price)}¢")
                            else:
                                print(
                                    f"[{cfg.remark}] ✗ 初始买单失败: {result.errmsg}")
                        except Exception as e:
                            print(f"[{cfg.remark}] ✗ 初始买单异常: {e}")

        try:
            while state.is_running and not stop_event.is_set():
                # 从共享盘口获取数据
                with shared_orderbook['lock']:
                    bids_dict = dict(shared_orderbook['bids'])
                    asks_dict = dict(shared_orderbook['asks'])

                if not bids_dict or not asks_dict:
                    time.sleep(0.5)
                    continue

                # 转换为排序列表
                bids = sorted([(float(p), float(s)) for p, s in bids_dict.items(
                )], key=lambda x: x[0], reverse=True)
                asks = sorted([(float(p), float(s))
                              for p, s in asks_dict.items()], key=lambda x: x[0])

                bid1_price = bids[0][0] if bids else 0
                ask1_price = asks[0][0] if asks else 0
                spread = ask1_price - bid1_price

                # 创建兼容的订单簿对象
                class OrderItem:
                    def __init__(self, price, size):
                        self.price = str(price)
                        self.size = str(size)

                bids_obj = [OrderItem(p, s) for p, s in bids]
                asks_obj = [OrderItem(p, s) for p, s in asks]

                # ============ 保护检查（复用原有逻辑）============

                # 检查盘口深度
                if config.min_orderbook_depth > 0:
                    bid_depth = sum(p * s for p, s in bids[:5])
                    ask_depth = sum(p * s for p, s in asks[:5])

                    if bid_depth < config.min_orderbook_depth or ask_depth < config.min_orderbook_depth:
                        if not state.depth_insufficient:
                            print(
                                f"[{cfg.remark}] [!] 盘口深度不足: 买${bid_depth:.0f}, 卖${ask_depth:.0f}")
                            state.depth_insufficient = True
                            self._mm_cancel_all_orders(client, cfg, state)
                        time.sleep(config.check_interval)
                        continue
                    else:
                        if state.depth_insufficient:
                            print(f"[{cfg.remark}] ✓ 盘口深度恢复")
                            state.depth_insufficient = False

                # 检测深度骤降
                if config.auto_cancel_on_depth_drop:
                    is_drop, drop_side, drop_percent = self._mm_check_depth_drop(
                        config, state, bids_obj, asks_obj)
                    if is_drop:
                        side_name = {'bid': '买盘', 'ask': '卖盘',
                                     'both': '买卖盘'}.get(drop_side, drop_side)
                        self._mm_emergency_cancel_all(
                            client, cfg, config, state, f"{side_name}深度骤降{drop_percent:.0f}%")
                        state.depth_drop_triggered = True
                        state.bid_depth_history = []
                        state.ask_depth_history = []
                        time.sleep(config.check_interval * 2)
                        continue
                    elif state.depth_drop_triggered:
                        print(f"[{cfg.remark}] ✓ 盘口深度恢复正常")
                        state.depth_drop_triggered = False

                # 检查价差
                if spread < config.min_spread:
                    time.sleep(config.check_interval)
                    continue

                # 检查仓位限制
                position_ok = self._mm_check_position_limit(
                    client, cfg, config, state)
                state.position_limit_reached = not position_ok

                # 检查止损
                if self._mm_check_stop_loss(client, cfg, config, state, bid1_price):
                    print(f"[{cfg.remark}] 触发止损!")
                    self._mm_execute_stop_loss(
                        client, cfg, config, state, bids_obj)
                    state.is_running = False
                    break

                # 管理双边挂单
                self._mm_manage_dual_orders(
                    client, cfg, config, state, bids_obj, asks_obj)

                # WebSocket 模式下可以减少等待时间，因为数据是实时的
                time.sleep(max(0.5, config.check_interval / 2))

        except Exception as e:
            print(f"[{cfg.remark}] 做市异常: {e}")
        finally:
            self._mm_cancel_all_orders(client, cfg, state)
            print(f"[{cfg.remark}] 做市结束")

    def _run_single_account_market_maker(self, acc_idx: int, config: MarketMakerConfig,
                                         state: MarketMakerState, stop_event: threading.Event):
        """单账户做市循环"""
        client = self.clients[acc_idx - 1]
        cfg = self.configs[acc_idx - 1]

        # 记录做市开始时间
        state.start_time = time.time()
        print(f"[{cfg.remark}] 做市开始")

        # 记录启动时的参考价（用于偏离度保护）
        initial_orderbook = self._mm_get_orderbook(client, config.token_id)
        if initial_orderbook and initial_orderbook.bids and initial_orderbook.asks:
            bids_init = sorted(initial_orderbook.bids,
                               key=lambda x: float(x.price), reverse=True)
            asks_init = sorted(initial_orderbook.asks,
                               key=lambda x: float(x.price))
            state.reference_bid1 = float(bids_init[0].price)
            state.reference_ask1 = float(asks_init[0].price)
            state.reference_mid_price = (
                state.reference_bid1 + state.reference_ask1) / 2
            print(f"[{cfg.remark}] 参考价: 买1={self.format_price(state.reference_bid1)}¢, "
                  f"卖1={self.format_price(state.reference_ask1)}¢, "
                  f"中间价={self.format_price(state.reference_mid_price)}¢")

        # 处理初始卖单（现有持仓挂卖）
        initial_sell_orders = getattr(config, 'initial_sell_orders', {})
        if acc_idx in initial_sell_orders:
            sell_info = initial_sell_orders[acc_idx]
            try:
                order = PlaceOrderDataInput(
                    marketId=config.market_id,
                    tokenId=config.token_id,
                    side=OrderSide.SELL,
                    orderType=LIMIT_ORDER,
                    price=f"{sell_info['price']:.6f}",
                    shares=sell_info['shares']
                )
                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    state.sell_order_id = result.result.order_id
                    state.sell_order_price = sell_info['price']
                    state.position_shares = sell_info['shares']
                    state.position_cost = sell_info['price'] * \
                        sell_info['shares']
                    print(
                        f"[{cfg.remark}] ✓ 现有持仓已挂卖单: {sell_info['shares']}份 @ {self.format_price(sell_info['price'])}¢")
                else:
                    print(f"[{cfg.remark}] ✗ 挂卖单失败: {result.errmsg}")
            except Exception as e:
                print(f"[{cfg.remark}] ✗ 挂卖单异常: {e}")

        # 同时挂初始买单（如果未达持仓上限）
        position_ok = self._mm_check_position_limit(client, cfg, config, state)
        if position_ok and initial_orderbook and initial_orderbook.bids:
            bids_sorted = sorted(initial_orderbook.bids,
                                 key=lambda x: float(x.price), reverse=True)
            if bids_sorted:
                bid1_price = float(bids_sorted[0].price)
                initial_buy_price = bid1_price
                # 检查边界
                if config.max_buy_price > 0 and initial_buy_price > config.max_buy_price:
                    initial_buy_price = config.max_buy_price
                try:
                    initial_amount = random.uniform(
                        config.order_amount_min, config.order_amount_max)
                    buy_order = PlaceOrderDataInput(
                        marketId=config.market_id,
                        tokenId=config.token_id,
                        side=OrderSide.BUY,
                        orderType=LIMIT_ORDER,
                        price=f"{initial_buy_price:.6f}",
                        makerAmountInQuoteToken=round(initial_amount, 2)
                    )
                    result = client.place_order(buy_order, check_approval=True)
                    if result.errno == 0:
                        state.buy_order_id = result.result.order_id
                        state.buy_order_price = initial_buy_price
                        print(
                            f"[{cfg.remark}] ✓ 初始买单: ${initial_amount:.2f} @ {self.format_price(initial_buy_price)}¢")
                    else:
                        print(f"[{cfg.remark}] ✗ 初始买单失败: {result.errmsg}")
                except Exception as e:
                    print(f"[{cfg.remark}] ✗ 初始买单异常: {e}")

        try:
            while state.is_running and not stop_event.is_set():
                # 1. 获取盘口
                orderbook = self._mm_get_orderbook(client, config.token_id)
                if not orderbook:
                    time.sleep(config.check_interval)
                    continue

                bids = sorted(orderbook.bids, key=lambda x: float(
                    x.price), reverse=True) if orderbook.bids else []
                asks = sorted(orderbook.asks, key=lambda x: float(
                    x.price)) if orderbook.asks else []

                if not bids or not asks:
                    time.sleep(config.check_interval)
                    continue

                bid1_price = float(bids[0].price)
                ask1_price = float(asks[0].price)
                spread = ask1_price - bid1_price

                # ============ 保护检查 ============

                # 2. 检查盘口深度（防止薄盘操控）
                if config.min_orderbook_depth > 0:
                    bid_depth = sum(float(b.price) * float(b.size)
                                    for b in bids[:5])
                    ask_depth = sum(float(a.price) * float(a.size)
                                    for a in asks[:5])

                    if bid_depth < config.min_orderbook_depth or ask_depth < config.min_orderbook_depth:
                        if not state.depth_insufficient:
                            print(
                                f"[{cfg.remark}] [!] 盘口深度不足: 买${bid_depth:.0f}, 卖${ask_depth:.0f} < ${config.min_orderbook_depth}")
                            state.depth_insufficient = True
                            # 撤销所有挂单等待
                            self._mm_cancel_all_orders(client, cfg, state)
                        time.sleep(config.check_interval)
                        continue
                    else:
                        if state.depth_insufficient:
                            print(
                                f"[{cfg.remark}] ✓ 盘口深度恢复: 买${bid_depth:.0f}, 卖${ask_depth:.0f}")
                            state.depth_insufficient = False

                # 2.5 检测盘口深度骤降（大量撤单警报）
                if config.auto_cancel_on_depth_drop:
                    is_drop, drop_side, drop_percent = self._mm_check_depth_drop(
                        config, state, bids, asks)
                    if is_drop:
                        side_name = {'bid': '买盘', 'ask': '卖盘',
                                     'both': '买卖盘'}.get(drop_side, drop_side)
                        self._mm_emergency_cancel_all(
                            client, cfg, config, state,
                            f"{side_name}深度骤降{drop_percent:.0f}%"
                        )
                        state.depth_drop_triggered = True
                        # 清空深度历史，重新开始记录
                        state.bid_depth_history = []
                        state.ask_depth_history = []
                        # 等待一段时间再恢复
                        time.sleep(config.check_interval * 2)
                        continue
                    elif state.depth_drop_triggered:
                        # 深度恢复正常
                        print(f"[{cfg.remark}] ✓ 盘口深度恢复正常")
                        state.depth_drop_triggered = False

                # 3. 检查价差是否满足条件
                if spread < config.min_spread:
                    time.sleep(config.check_interval)
                    continue

                # 4. 检查仓位限制
                position_ok = self._mm_check_position_limit(
                    client, cfg, config, state)
                state.position_limit_reached = not position_ok

                # 5. 检查止损条件
                if self._mm_check_stop_loss(client, cfg, config, state, bid1_price):
                    print(f"[{cfg.remark}] 触发止损!")
                    self._mm_execute_stop_loss(
                        client, cfg, config, state, bids)
                    state.is_running = False
                    break

                # 6. 根据模式管理挂单
                if config.grid_enabled:
                    # 网格策略模式
                    # 6.1 检查买单成交情况
                    self._grid_check_buy_filled(client, cfg, config, state)
                    # 6.2 检查卖单成交情况
                    self._grid_check_sell_filled(
                        client, cfg, config, state, bids)
                    # 6.3 补充网格买单（如果不足）
                    if len(state.grid_buy_orders) < config.grid_levels and not state.position_limit_reached:
                        self._grid_place_buy_orders(
                            client, cfg, config, state, bids)
                else:
                    # 传统双边挂单模式（带价格边界保护）
                    self._mm_manage_dual_orders(
                        client, cfg, config, state, bids, asks)

                time.sleep(config.check_interval)

        except Exception as e:
            print(f"[{cfg.remark}] 做市异常: {e}")
        finally:
            # 清理：撤销所有挂单
            if config.grid_enabled:
                self._grid_cancel_all_orders(client, cfg, config, state)
                self._grid_show_status(cfg, state)
            else:
                self._mm_cancel_all_orders(client, cfg, state)
            print(f"[{cfg.remark}] 做市结束")

    def _mm_get_top_holders(self, market_id: int, token_type: str = "yes",
                            chain_id: int = 56, page: int = 1, limit: int = 50) -> dict:
        """获取市场持仓榜
        Args:
            market_id: 子市场ID
            token_type: yes 或 no
            chain_id: 链ID，默认56(BSC)
            page: 页码
            limit: 每页数量
        Returns:
            {
                'list': [{'userName', 'walletAddress', 'sharesAmount', 'profit', 'avatar'}, ...],
                'total': 总持仓人数
            }
        """
        try:
            url = f"https://proxy.opinion.trade:8443/api/bsc/api/v2/topic/{market_id}/holder"
            params = {
                'type': token_type.lower(),
                'chainId': chain_id,
                'page': page,
                'limit': limit
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('errno') == 0:
                    return data.get('result', {})
        except Exception as e:
            print(f"获取持仓榜异常: {e}")
        return {'list': [], 'total': 0}

    def _mm_calculate_depth(self, orders: list, levels: int = 10) -> float:
        """计算盘口深度（前N档总金额）"""
        if not orders:
            return 0
        total = 0
        for i, order in enumerate(orders[:levels]):
            price = float(order.price)
            size = float(order.size)
            total += price * size / 100  # 转换为美元
        return total

    def _mm_check_depth_drop(self, config: MarketMakerConfig, state: MarketMakerState,
                             bids: list, asks: list) -> tuple:
        """检测盘口深度是否骤降
        Returns:
            (is_drop: bool, drop_side: str, drop_percent: float)
            is_drop: 是否检测到深度骤降
            drop_side: 'bid'/'ask'/'both'
            drop_percent: 下降百分比
        """
        if not config.auto_cancel_on_depth_drop:
            return (False, '', 0)

        # 初始化深度历史
        if state.bid_depth_history is None:
            state.bid_depth_history = []
        if state.ask_depth_history is None:
            state.ask_depth_history = []

        # 计算当前深度
        current_bid_depth = self._mm_calculate_depth(bids)
        current_ask_depth = self._mm_calculate_depth(asks)

        # 记录深度历史
        state.bid_depth_history.append(current_bid_depth)
        state.ask_depth_history.append(current_ask_depth)

        # 保持窗口大小
        window = config.depth_drop_window + 1  # +1 因为需要比较
        if len(state.bid_depth_history) > window:
            state.bid_depth_history = state.bid_depth_history[-window:]
        if len(state.ask_depth_history) > window:
            state.ask_depth_history = state.ask_depth_history[-window:]

        # 需要足够的历史数据才能检测
        if len(state.bid_depth_history) < 2:
            return (False, '', 0)

        # 获取窗口起点的深度
        start_bid_depth = state.bid_depth_history[0]
        start_ask_depth = state.ask_depth_history[0]

        # 计算下降百分比
        bid_drop = 0
        ask_drop = 0

        if start_bid_depth > 0:
            bid_drop = (start_bid_depth - current_bid_depth) / \
                start_bid_depth * 100

        if start_ask_depth > 0:
            ask_drop = (start_ask_depth - current_ask_depth) / \
                start_ask_depth * 100

        # 检测是否超过阈值
        threshold = config.depth_drop_threshold
        is_bid_drop = bid_drop >= threshold
        is_ask_drop = ask_drop >= threshold

        if is_bid_drop and is_ask_drop:
            return (True, 'both', max(bid_drop, ask_drop))
        elif is_bid_drop:
            return (True, 'bid', bid_drop)
        elif is_ask_drop:
            return (True, 'ask', ask_drop)

        return (False, '', 0)

    def _mm_emergency_cancel_all(self, client, cfg, config: MarketMakerConfig,
                                 state: MarketMakerState, reason: str):
        """紧急撤销所有挂单，并根据配置处理持仓"""
        print(f"[{cfg.remark}] ⚠️ {reason}，紧急撤单")

        cancelled = 0
        if state.buy_order_id:
            if self._mm_cancel_order_safe(client, state.buy_order_id):
                cancelled += 1
            state.buy_order_id = None
            state.buy_order_price = 0

        if state.sell_order_id:
            if self._mm_cancel_order_safe(client, state.sell_order_id):
                cancelled += 1
            state.sell_order_id = None
            state.sell_order_price = 0

        if cancelled > 0:
            print(f"[{cfg.remark}] ✓ 已撤销 {cancelled} 个订单")

        # 根据配置处理持仓
        if config.emergency_position_action != 'hold':
            shares, _, _ = self._mm_get_current_position(
                client, config.token_id)
            if shares > 0:
                if config.emergency_position_action == 'sell_all':
                    # 市价卖出全部
                    print(f"[{cfg.remark}] 紧急卖出全部持仓 {shares}份...")
                    self._mm_emergency_market_sell(
                        client, cfg, config, state, shares)
                elif config.emergency_position_action == 'sell_partial':
                    # 卖出部分
                    sell_shares = int(
                        shares * config.emergency_sell_percent / 100)
                    keep_shares = shares - sell_shares
                    if sell_shares > 0:
                        print(
                            f"[{cfg.remark}] 紧急卖出 {sell_shares}份，保留 {keep_shares}份...")
                        self._mm_emergency_market_sell(
                            client, cfg, config, state, sell_shares)

    def _mm_emergency_market_sell(self, client, cfg, config: MarketMakerConfig,
                                  state: MarketMakerState, shares: int):
        """紧急市价卖出"""
        from opinion_sdk import PlaceOrderDataInput, OrderSide, MARKET_ORDER

        try:
            order = PlaceOrderDataInput(
                marketId=config.market_id,
                tokenId=config.token_id,
                side=OrderSide.SELL,
                orderType=MARKET_ORDER,
                sharesAmount=shares
            )
            result = client.place_order(order, check_approval=True)
            if result.errno == 0:
                print(f"[{cfg.remark}] ✓ 紧急卖出 {shares}份 成功")
                # 记录卖出
                self._mm_record_sell_fill(cfg, state, shares, 0)  # 价格未知，记0
            else:
                print(
                    f"[{cfg.remark}] ✗ 紧急卖出失败: {self.translate_error(result.errmsg)}")
        except Exception as e:
            print(f"[{cfg.remark}] ✗ 紧急卖出异常: {e}")

    def _mm_get_orderbook(self, client, token_id: str):
        """获取盘口数据"""
        ob = OrderbookService.fetch(client, token_id)
        return ob.get('raw') if ob['success'] else None

    def _mm_get_order_status(self, client, order_id: str):
        """获取订单状态"""
        if not order_id:
            return None
        try:
            orders_resp = client.get_my_orders()
            if orders_resp.errno == 0:
                for order in orders_resp.result.list or []:
                    if str(order.order_id) == str(order_id):
                        return order
        except Exception:
            pass
        return None

    def _mm_cancel_order_safe(self, client, order_id: str) -> bool:
        """安全撤单（忽略错误）"""
        if not order_id:
            return True
        try:
            result = client.cancel_order(order_id)
            return result.errno == 0
        except Exception:
            return False

    def _mm_get_current_position(self, client, token_id: str) -> tuple:
        """获取当前持仓信息
        返回: (shares, avg_cost, current_value)
        """
        pos = PositionService.get_position_by_token(client, token_id)
        if pos:
            return (pos['shares'], pos.get('current_price', 0), pos.get('current_value', 0))
        return (0, 0, 0)

    def _mm_manage_dual_orders(self, client, cfg, config: MarketMakerConfig,
                               state: MarketMakerState, bids: list, asks: list):
        """管理双边挂单"""
        bid1_price = float(bids[0].price)
        ask1_price = float(asks[0].price)

        # ========== 管理买单 ==========
        if not state.position_limit_reached:
            if state.buy_order_id:
                # 检查买单状态
                buy_order = self._mm_get_order_status(
                    client, state.buy_order_id)
                if buy_order:
                    filled = float(buy_order.filled_shares or 0)
                    if filled > 0:
                        # 有成交，记录
                        self._mm_record_buy_fill(
                            cfg, state, int(filled), state.buy_order_price)

                    if buy_order.status != 1:  # 非Pending
                        state.buy_order_id = None
                        state.buy_order_price = 0
                    else:
                        # 检查是否需要调价
                        need_adjust, new_price, boundary_hit = self._mm_check_buy_price_adjustment(
                            config, state, bids, asks
                        )
                        if boundary_hit and not state.price_boundary_hit:
                            state.price_boundary_hit = True
                            print(f"[{cfg.remark}] ⚠️ 买价触及边界保护，暂停跟随")
                        elif not boundary_hit and state.price_boundary_hit:
                            state.price_boundary_hit = False
                            print(f"[{cfg.remark}] ✓ 买价回到安全区间，恢复跟随")

                        if need_adjust:
                            print(
                                f"[{cfg.remark}] 买单调价: {self.format_price(state.buy_order_price)}¢ → {self.format_price(new_price)}¢")
                            self._mm_cancel_order_safe(
                                client, state.buy_order_id)
                            state.buy_order_id = None
                            # 立即重新挂单（传递盘口数据以支持分层）
                            self._mm_place_buy_order(
                                client, cfg, config, state, new_price, bids)
                else:
                    state.buy_order_id = None
                    state.buy_order_price = 0

            if not state.buy_order_id:
                # 没有买单，创建新买单
                # 计算初始价格：如果买1+0.1 < 卖1，挂买1+0.1；否则挂买1
                if bid1_price + config.price_step < ask1_price:
                    initial_price = bid1_price + config.price_step
                else:
                    initial_price = bid1_price
                # 检查初始价格是否超过边界
                if config.max_buy_price > 0 and initial_price > config.max_buy_price:
                    initial_price = config.max_buy_price
                if config.max_price_deviation > 0 and state.reference_mid_price > 0:
                    max_allowed = state.reference_mid_price * \
                        (1 + config.max_price_deviation / 100)
                    if initial_price > max_allowed:
                        initial_price = max_allowed
                self._mm_place_buy_order(
                    client, cfg, config, state, initial_price, bids)

        # ========== 管理卖单 ==========
        # 获取当前持仓
        shares, _, _ = self._mm_get_current_position(client, config.token_id)

        if shares > 0:
            if state.sell_order_id:
                # 检查卖单状态
                sell_order = self._mm_get_order_status(
                    client, state.sell_order_id)
                if sell_order:
                    filled = float(sell_order.filled_shares or 0)
                    if filled > 0:
                        # 有成交，记录
                        self._mm_record_sell_fill(
                            cfg, state, int(filled), state.sell_order_price)

                    if sell_order.status != 1:  # 非Pending
                        state.sell_order_id = None
                        state.sell_order_price = 0
                    else:
                        # 检查是否需要调价
                        need_adjust, new_price, boundary_hit = self._mm_check_sell_price_adjustment(
                            config, state, bids, asks
                        )
                        if boundary_hit and not state.price_boundary_hit:
                            state.price_boundary_hit = True
                            print(f"[{cfg.remark}] ⚠️ 卖价触及边界保护，暂停跟随")
                        elif not boundary_hit and state.price_boundary_hit:
                            state.price_boundary_hit = False
                            print(f"[{cfg.remark}] ✓ 卖价回到安全区间，恢复跟随")

                        if need_adjust:
                            print(
                                f"[{cfg.remark}] 卖单调价: {self.format_price(state.sell_order_price)}¢ → {self.format_price(new_price)}¢")
                            self._mm_cancel_order_safe(
                                client, state.sell_order_id)
                            state.sell_order_id = None
                            # 立即重新挂单（传递盘口数据以支持分层）
                            self._mm_place_sell_order(
                                client, cfg, config, state, new_price, shares, asks)
                else:
                    state.sell_order_id = None
                    state.sell_order_price = 0

            if not state.sell_order_id and shares > 0:
                # 没有卖单，创建新卖单
                initial_price = ask1_price  # 默认使用卖1价

                # ============ 成本加成定价模式 ============
                if config.cost_based_sell_enabled and state.total_buy_shares > 0:
                    # 计算平均买入成本
                    avg_cost = state.total_buy_cost / state.total_buy_shares * 100  # 转为分
                    cost_sell_price = avg_cost + config.sell_profit_spread

                    # 检查利润空间是否足够
                    if cost_sell_price - avg_cost >= config.min_cost_profit_spread:
                        initial_price = cost_sell_price
                        print(
                            f"[{cfg.remark}] 成本定价: 均价{self.format_price(avg_cost)}¢ + {config.sell_profit_spread}¢ = {self.format_price(initial_price)}¢")
                    else:
                        print(
                            f"[{cfg.remark}] 利润不足，使用市价: {self.format_price(ask1_price)}¢ (成本{self.format_price(avg_cost)}¢)")
                        # 使用市场价
                        if ask1_price - config.price_step > bid1_price:
                            initial_price = ask1_price - config.price_step
                        else:
                            initial_price = ask1_price
                else:
                    # 原逻辑：跟随市场卖1价
                    if ask1_price - config.price_step > bid1_price:
                        initial_price = ask1_price - config.price_step
                    else:
                        initial_price = ask1_price

                # 检查初始价格是否低于边界
                if config.min_sell_price > 0 and initial_price < config.min_sell_price:
                    initial_price = config.min_sell_price
                if config.max_price_deviation > 0 and state.reference_mid_price > 0:
                    min_allowed = state.reference_mid_price * \
                        (1 - config.max_price_deviation / 100)
                    if initial_price < min_allowed:
                        initial_price = min_allowed
                self._mm_place_sell_order(
                    client, cfg, config, state, initial_price, shares, asks)

    def _mm_place_buy_order(self, client, cfg, config: MarketMakerConfig,
                            state: MarketMakerState, price: float, bids: list = None):
        """挂买单 - 支持分层挂单"""
        # 如果启用分层买入且有盘口数据
        if config.layered_buy_enabled and bids and len(config.buy_price_levels or []) > 1:
            self._mm_place_layered_buy_orders(client, cfg, config, state, bids)
        else:
            # 普通单笔挂单
            amount = random.uniform(
                config.order_amount_min, config.order_amount_max)

            order = PlaceOrderDataInput(
                marketId=config.market_id,
                tokenId=config.token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=f"{price:.6f}",
                makerAmountInQuoteToken=round(amount, 2)
            )

            try:
                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    state.buy_order_id = result.result.order_id
                    state.buy_order_price = price
                    print(
                        f"[{cfg.remark}] ✓ 挂买: ${amount:.2f} @ {self.format_price(price)}¢")
                else:
                    print(
                        f"[{cfg.remark}] ✗ 挂买失败: {self.translate_error(result.errmsg)}")
            except Exception as e:
                print(f"[{cfg.remark}] ✗ 挂买异常: {e}")

    def _mm_place_layered_buy_orders(self, client, cfg, config: MarketMakerConfig,
                                     state: MarketMakerState, bids: list):
        """分层挂买单"""
        price_levels = config.buy_price_levels or [1]
        ratios = self._calculate_distribution_ratios(
            price_levels, config.buy_distribution_mode, config.buy_custom_ratios or []
        )

        # 计算总金额并分配
        total_amount = random.uniform(
            config.order_amount_min, config.order_amount_max) * len(price_levels)

        success_count = 0
        first_order_id = None
        first_order_price = 0

        for level_idx, level in enumerate(price_levels):
            ratio = ratios[level_idx]
            level_amount = total_amount * ratio
            if level_amount < 1:  # 最低$1
                continue

            # 获取买N的价格
            if level <= len(bids):
                buy_price = float(bids[level - 1].price)
            else:
                # 盘口深度不够，使用最后一档价格减偏移
                buy_price = float(bids[-1].price) - \
                    (level - len(bids)) * 0.1 if bids else 0

            if buy_price <= 0:
                continue

            # 检查价格边界
            if config.max_buy_price > 0 and buy_price > config.max_buy_price:
                buy_price = config.max_buy_price

            try:
                order = PlaceOrderDataInput(
                    marketId=config.market_id,
                    tokenId=config.token_id,
                    side=OrderSide.BUY,
                    orderType=LIMIT_ORDER,
                    price=f"{buy_price:.6f}",
                    makerAmountInQuoteToken=round(level_amount, 2)
                )

                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    success_count += 1
                    # 记录第一个订单ID用于状态跟踪
                    if first_order_id is None:
                        first_order_id = result.result.order_id
                        first_order_price = buy_price
                    print(
                        f"[{cfg.remark}] ✓ 买{level}: ${level_amount:.2f} @ {self.format_price(buy_price)}¢")
                else:
                    print(
                        f"[{cfg.remark}] ✗ 买{level}: {self.translate_error(result.errmsg)}")

                time.sleep(0.3)  # 避免请求过快

            except Exception as e:
                print(f"[{cfg.remark}] ✗ 买{level}异常: {e}")

        # 更新状态（使用第一个订单作为参考）
        if first_order_id:
            state.buy_order_id = first_order_id
            state.buy_order_price = first_order_price

        if success_count > 0:
            print(f"[{cfg.remark}] 分层买入完成: {success_count}/{len(price_levels)}笔")

    def _mm_place_sell_order(self, client, cfg, config: MarketMakerConfig,
                             state: MarketMakerState, price: float, shares: int,
                             asks: list = None):
        """挂卖单 - 支持分层挂单"""
        # 如果启用分层卖出且有盘口数据
        if config.layered_sell_enabled and asks and len(config.sell_price_levels or []) > 1:
            self._mm_place_layered_sell_orders(
                client, cfg, config, state, shares, asks)
        else:
            # 普通单笔挂单
            order = PlaceOrderDataInput(
                marketId=config.market_id,
                tokenId=config.token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=f"{price:.6f}",
                makerAmountInBaseToken=shares
            )

            try:
                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    state.sell_order_id = result.result.order_id
                    state.sell_order_price = price
                    print(
                        f"[{cfg.remark}] ✓ 挂卖: {shares}份 @ {self.format_price(price)}¢")
                else:
                    print(
                        f"[{cfg.remark}] ✗ 挂卖失败: {self.translate_error(result.errmsg)}")
            except Exception as e:
                print(f"[{cfg.remark}] ✗ 挂卖异常: {e}")

    def _configure_layered_order(self, side: str, bid_details: list, ask_details: list,
                                 format_price) -> Optional[dict]:
        """配置分层挂单参数

        Args:
            side: 'buy' 或 'sell'
            bid_details: 买盘数据 [(档位, 价格, 数量, 累计), ...]
            ask_details: 卖盘数据 [(档位, 价格, 数量, 累计), ...]
            format_price: 价格格式化函数

        Returns:
            配置字典 {'price_mode': str, 'prices': list, 'distribution': str, 'custom_ratios': list}
            返回 None 表示取消
        """
        side_name = '买入' if side == 'buy' else '卖出'
        order_book = bid_details if side == 'buy' else ask_details

        print(f"\n{'='*50}")
        print(f"分层{side_name}挂单配置")
        print(f"{'='*50}")

        # 1. 价格模式选择
        print(f"\n[1] 价格选择方式:")
        print(f"  1. 按盘口档位 (如 买1-买3-买5 或 卖1-卖3-卖5)")
        print(f"  2. 自定义价格区间 (指定起始价、结束价、层数)")
        print(f"  3. 自定义价格列表 (如: 60 62 65 70)")
        price_mode_choice = input("请选择 (1/2/3): ").strip()

        prices = []
        price_mode = 'levels'

        if price_mode_choice == '3':
            # 自定义价格列表
            price_mode = 'custom_list'
            print(f"\n当前盘口参考:")
            if bid_details:
                print(f"  买1: {format_price(bid_details[0][1])}¢")
            if ask_details:
                print(f"  卖1: {format_price(ask_details[0][1])}¢")

            print(f"\n输入价格列表，用空格分隔 (单位: 分)")
            print(f"示例: 60 62 65 70 表示在 60¢、62¢、65¢、70¢ 四个价格挂单")
            prices_input = input("请输入价格: ").strip()

            try:
                price_cents_list = [float(x) for x in prices_input.split()]
                if not price_cents_list:
                    print("[!] 未输入价格")
                    return None

                # 将"分"转换为小数格式 (60分 -> 0.60)，并四舍五入到0.1分
                prices = [round(p / 100.0, 3) for p in price_cents_list]
                # 验证价格范围
                for p in prices:
                    if p < 0.01 or p > 0.99:
                        print(f"[!] 价格 {p*100:.1f}¢ 超出有效范围 (1-99分)")
                        return None
                print(
                    f"\n✓ 价格层级 ({len(prices)}层): {', '.join([f'{format_price(p)}¢' for p in prices])}")
            except ValueError:
                print("[!] 输入格式错误，请输入数字")
                return None
        elif price_mode_choice == '2':
            # 自定义价格区间
            price_mode = 'custom_range'
            print(f"\n当前盘口参考:")
            if bid_details:
                print(f"  买1: {format_price(bid_details[0][1])}¢")
            if ask_details:
                print(f"  卖1: {format_price(ask_details[0][1])}¢")

            try:
                start_price_cents = float(input(f"起始价格 (分): ").strip())
                end_price_cents = float(input(f"结束价格 (分): ").strip())

                # 计算最大可用层数（最小价差0.1分）
                price_range = abs(end_price_cents - start_price_cents)
                max_levels = int(price_range / 0.1) + \
                    1 if price_range > 0 else 1

                if max_levels < 2:
                    print(f"[!] 价格区间太小，无法分层")
                    return None

                num_levels = int(input(
                    f"分层数量 (2-{max_levels}, 默认{min(5, max_levels)}): ").strip() or str(min(5, max_levels)))
                num_levels = max(2, min(max_levels, num_levels))

                # 将"分"转换为小数格式 (60分 -> 0.60)
                start_price = start_price_cents / 100.0
                end_price = end_price_cents / 100.0

                if start_price == end_price:
                    prices = [start_price]
                else:
                    step = (end_price - start_price) / (num_levels - 1)
                    # 价格四舍五入到0.1分（0.001小数）
                    prices = [round(start_price + step * i, 3)
                              for i in range(num_levels)]
                print(
                    f"\n✓ 价格层级: {', '.join([f'{format_price(p)}¢' for p in prices])}")
            except ValueError:
                print("[!] 输入格式错误")
                return None
        else:
            # 按盘口档位
            price_mode = 'levels'
            print(f"\n当前{side_name}盘口:")
            book_name = '买' if side == 'buy' else '卖'
            for i, (num, price, size, depth) in enumerate(order_book[:10], 1):
                print(
                    f"  {i:2d}. {book_name}{num} {format_price(price)}¢  (深度: {size})")
            if len(order_book) < 10:
                for i in range(len(order_book) + 1, 11):
                    print(f"  {i:2d}. {book_name}{i} (无)")

            print(
                f"\n输入档位，用空格分隔 (如: 1 3 5 表示{book_name}1、{book_name}3、{book_name}5)")
            levels_input = input(f"请输入档位 (默认: 1 3 5): ").strip()
            if not levels_input:
                levels_input = "1 3 5"

            try:
                levels = [int(x) for x in levels_input.split()]
                levels = sorted(set([l for l in levels if 1 <= l <= 10]))
                if not levels:
                    levels = [1, 3, 5]

                # 获取每个档位的实际价格
                for level in levels:
                    if level <= len(order_book):
                        prices.append(order_book[level - 1][1])
                    else:
                        # 档位不存在，根据已有价格推算
                        if order_book:
                            last_price = order_book[-1][1]
                            # 根据方向调整价格（0.01 = 1分）
                            if side == 'buy':
                                prices.append(last_price - 0.01 *
                                              (level - len(order_book)))
                            else:
                                prices.append(last_price + 0.01 *
                                              (level - len(order_book)))

                if prices:
                    print(
                        f"\n✓ 选择档位: {', '.join([f'{book_name}{l}' for l in levels])}")
                    print(
                        f"  对应价格: {', '.join([f'{format_price(p)}¢' for p in prices])}")
                else:
                    print("[!] 无法获取价格")
                    return None
            except ValueError:
                print("[!] 输入格式错误")
                return None

        if not prices:
            return None

        # 2. 分布模式选择
        # 根据买卖方向调整描述：
        # - 买入时：第一层是买1（高价，靠近盘口），金字塔=靠近少远离多，倒金字塔=靠近多远离少
        # - 卖出时：第一层是卖1（低价，靠近盘口），金字塔=靠近多远离少，倒金字塔=靠近少远离多
        print(f"\n[2] 金额分布模式:")
        print(f"  1. 均匀分布 (每层金额相等)")
        if side == 'buy':
            print(f"  2. 金字塔 (高价少买，低价多买)")
            print(f"  3. 倒金字塔 (高价多买，低价少买)")
        else:
            print(f"  2. 金字塔 (低价多卖，高价少卖)")
            print(f"  3. 倒金字塔 (低价少卖，高价多卖)")
        print(f"  4. 自定义比例")
        dist_choice = input("请选择 (1/2/3/4, 默认1): ").strip() or '1'

        distribution = 'uniform'
        custom_ratios = []

        if dist_choice == '2':
            distribution = 'pyramid'
        elif dist_choice == '3':
            distribution = 'inverse_pyramid'
        elif dist_choice == '4':
            distribution = 'custom'
            print(f"\n输入各层比例，用空格分隔 (需要{len(prices)}个数字)")
            print(f"  示例: 1 2 3 表示第一层占1份，第二层占2份，第三层占3份")
            ratios_input = input(f"请输入比例: ").strip()
            try:
                custom_ratios = [float(x) for x in ratios_input.split()]
                if len(custom_ratios) != len(prices):
                    print(
                        f"[!] 比例数量({len(custom_ratios)})与层数({len(prices)})不匹配，使用均匀分布")
                    distribution = 'uniform'
                    custom_ratios = []
            except ValueError:
                print("[!] 输入格式错误，使用均匀分布")
                distribution = 'uniform'

        dist_names = {
            'uniform': '均匀分布',
            'pyramid': '金字塔',
            'inverse_pyramid': '倒金字塔',
            'custom': '自定义'
        }
        print(f"\n✓ 分布模式: {dist_names[distribution]}")

        # 显示预览
        ratios = self._calculate_distribution_ratios(
            list(range(len(prices))), distribution, custom_ratios
        )
        print(f"\n分层预览:")
        for i, (price, ratio) in enumerate(zip(prices, ratios), 1):
            print(f"  第{i}层: {format_price(price)}¢ - 占比 {ratio*100:.1f}%")

        confirm = input(f"\n确认配置? (y/n, 默认y): ").strip().lower()
        if confirm == 'n':
            return None

        return {
            'price_mode': price_mode,
            'prices': prices,
            'distribution': distribution,
            'custom_ratios': custom_ratios
        }

    def _execute_layered_order(self, client, market_id: int, token_id: str, side: str,
                               layered_config: dict, total_amount: float = None,
                               total_shares: int = None) -> dict:
        """执行分层挂单

        Args:
            client: SDK客户端
            market_id: 市场ID
            token_id: Token ID
            side: 'buy' 或 'sell'
            layered_config: 分层配置 {'prices': list, 'distribution': str, 'custom_ratios': list}
            total_amount: 买入时的总金额(美元)
            total_shares: 卖出时的总份额

        Returns:
            {'success': int, 'failed': int, 'orders': list}
        """
        prices = layered_config['prices']
        distribution = layered_config['distribution']
        custom_ratios = layered_config.get('custom_ratios', [])

        # 计算分配比例
        ratios = self._calculate_distribution_ratios(
            list(range(len(prices))), distribution, custom_ratios
        )

        results = {'success': 0, 'failed': 0, 'orders': []}

        for i, (price, ratio) in enumerate(zip(prices, ratios), 1):
            try:
                if side == 'buy':
                    # 买入：按金额分配
                    amount = round(total_amount * ratio, 2)
                    if amount < 1:  # 最小1美元
                        continue

                    order = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.BUY,
                        orderType=LIMIT_ORDER,
                        price=f"{price:.6f}",
                        makerAmountInQuoteToken=amount
                    )

                    result = client.place_order(order, check_approval=True)
                    price_display = self.format_price(price)

                    if result.errno == 0:
                        print(f"    ✓ 第{i}层: ${amount:.2f} @ {price_display}¢")
                        results['success'] += 1
                        results['orders'].append({
                            'level': i,
                            'price': price,
                            'amount': amount,
                            'order_id': result.result.order_id if hasattr(result.result, 'order_id') else None
                        })
                    else:
                        print(
                            f"    ✗ 第{i}层失败: {self.translate_error(result.errmsg)}")
                        results['failed'] += 1

                else:
                    # 卖出：按份额分配
                    shares = int(total_shares * ratio)
                    if shares < 1:
                        continue

                    order = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.SELL,
                        orderType=LIMIT_ORDER,
                        price=f"{price:.6f}",
                        makerAmountInBaseToken=shares
                    )

                    result = client.place_order(order, check_approval=True)
                    price_display = self.format_price(price)

                    if result.errno == 0:
                        print(f"    ✓ 第{i}层: {shares}份 @ {price_display}¢")
                        results['success'] += 1
                        results['orders'].append({
                            'level': i,
                            'price': price,
                            'shares': shares,
                            'order_id': result.result.order_id if hasattr(result.result, 'order_id') else None
                        })
                    else:
                        print(
                            f"    ✗ 第{i}层失败: {self.translate_error(result.errmsg)}")
                        results['failed'] += 1

                # 层间延迟
                time.sleep(0.5)

            except Exception as e:
                print(f"    ✗ 第{i}层异常: {e}")
                results['failed'] += 1

        return results

    def _calculate_distribution_ratios(self, price_levels: list, distribution_mode: str,
                                       custom_ratios: list) -> list:
        """计算各层分配比例，返回归一化后的比例列表"""
        n = len(price_levels)

        if distribution_mode == 'uniform':
            # 垂直分布：每层相等
            ratios = [1.0 / n] * n

        elif distribution_mode == 'pyramid':
            # 金字塔：第一层少，最后一层多
            # 权重: 1, 2, 3, ..., n
            # 买入时：高价少买，低价多买
            # 卖出时：低价少卖，高价多卖（实际效果：低价多卖，因为卖盘第一层是低价）
            weights = list(range(1, n + 1))
            total_weight = sum(weights)
            ratios = [w / total_weight for w in weights]

        elif distribution_mode == 'inverse_pyramid':
            # 倒金字塔：第一层多，最后一层少
            # 权重: n, n-1, ..., 1
            # 买入时：高价多买，低价少买
            # 卖出时：低价多卖，高价少卖
            weights = list(range(n, 0, -1))
            total_weight = sum(weights)
            ratios = [w / total_weight for w in weights]

        elif distribution_mode == 'custom':
            # 自定义比例
            total_weight = sum(custom_ratios)
            ratios = [w / total_weight for w in custom_ratios]

        else:
            # 默认均分
            ratios = [1.0 / n] * n

        return ratios

    def _mm_place_layered_sell_orders(self, client, cfg, config: MarketMakerConfig,
                                      state: MarketMakerState, total_shares: int, asks: list):
        """分层挂卖单"""
        price_levels = config.sell_price_levels or [1]
        ratios = self._calculate_distribution_ratios(
            price_levels, config.sell_distribution_mode, config.sell_custom_ratios or []
        )

        success_count = 0
        first_order_id = None
        first_order_price = 0

        for level_idx, level in enumerate(price_levels):
            ratio = ratios[level_idx]
            level_shares = int(total_shares * ratio)
            if level_shares <= 0:
                continue

            # 获取卖N的价格
            if level <= len(asks):
                sell_price = float(asks[level - 1].price)
            else:
                # 盘口深度不够，使用最后一档价格加偏移
                sell_price = float(asks[-1].price) + \
                    (level - len(asks)) * 0.1 if asks else 0

            if sell_price <= 0:
                continue

            # 检查价格边界
            if config.min_sell_price > 0 and sell_price < config.min_sell_price:
                sell_price = config.min_sell_price

            try:
                order = PlaceOrderDataInput(
                    marketId=config.market_id,
                    tokenId=config.token_id,
                    side=OrderSide.SELL,
                    orderType=LIMIT_ORDER,
                    price=f"{sell_price:.6f}",
                    makerAmountInBaseToken=level_shares
                )

                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    success_count += 1
                    # 记录第一个订单ID用于状态跟踪
                    if first_order_id is None:
                        first_order_id = result.result.order_id
                        first_order_price = sell_price
                    print(
                        f"[{cfg.remark}] ✓ 卖{level}: {level_shares}份 @ {self.format_price(sell_price)}¢")
                else:
                    print(
                        f"[{cfg.remark}] ✗ 卖{level}: {self.translate_error(result.errmsg)}")

                time.sleep(0.3)  # 避免请求过快

            except Exception as e:
                print(f"[{cfg.remark}] ✗ 卖{level}异常: {e}")

        # 更新状态（使用第一个订单作为参考）
        if first_order_id:
            state.sell_order_id = first_order_id
            state.sell_order_price = first_order_price

        if success_count > 0:
            print(f"[{cfg.remark}] 分层卖出完成: {success_count}/{len(price_levels)}笔")

    def _mm_check_buy_price_adjustment(self, config: MarketMakerConfig,
                                       state: MarketMakerState,
                                       bids: list, asks: list) -> tuple:
        """检查买单是否需要调价
        返回: (need_adjust: bool, new_price: float, boundary_hit: bool)
        """
        if not bids or not asks:
            return (False, state.buy_order_price, False)

        my_price = state.buy_order_price
        bid1_price = float(bids[0].price)
        ask1_price = float(asks[0].price)

        # 检查价差
        current_spread = ask1_price - bid1_price
        if current_spread < config.min_spread:
            # 价差过小，暂停跟随
            return (False, my_price, False)

        # 如果买1不是我的价格（允许0.001误差），说明被人抢占了
        if abs(bid1_price - my_price) > 0.001:
            if bid1_price > my_price:
                # 有人出价更高，需要调价
                new_price = bid1_price + config.price_step

                # 确保不会让价差低于最小值
                spread_limit = ask1_price - config.min_spread
                new_price = min(new_price, spread_limit)

                # ===== 价格边界保护 =====
                # 1. 绝对价格上限保护
                if config.max_buy_price > 0 and new_price > config.max_buy_price:
                    new_price = config.max_buy_price
                    if new_price <= my_price:
                        # 已达上限，不再跟随
                        return (False, my_price, True)

                # 2. 偏离度保护（相对于启动时的中间价）
                if config.max_price_deviation > 0 and state.reference_mid_price > 0:
                    max_allowed = state.reference_mid_price * \
                        (1 + config.max_price_deviation / 100)
                    if new_price > max_allowed:
                        new_price = max_allowed
                        if new_price <= my_price:
                            # 偏离度已达上限，不再跟随
                            return (False, my_price, True)

                if new_price > my_price:
                    return (True, new_price, False)

        return (False, my_price, False)

    def _mm_check_sell_price_adjustment(self, config: MarketMakerConfig,
                                        state: MarketMakerState,
                                        bids: list, asks: list) -> tuple:
        """检查卖单是否需要调价
        返回: (need_adjust: bool, new_price: float, boundary_hit: bool)
        """
        if not bids or not asks:
            return (False, state.sell_order_price, False)

        my_price = state.sell_order_price
        bid1_price = float(bids[0].price)
        ask1_price = float(asks[0].price)

        # ============ 成本加成模式：不跟随市场下跌 ============
        if config.cost_based_sell_enabled and state.total_buy_shares > 0:
            # 计算成本基准卖价
            avg_cost = state.total_buy_cost / state.total_buy_shares * 100  # 转为分
            cost_sell_price = avg_cost + config.sell_profit_spread

            # 如果当前挂单价已是成本价，不再调低
            if abs(my_price - cost_sell_price) < 0.01:
                return (False, my_price, False)

            # 只有当市场卖1价高于成本卖价时，才考虑跟随上调
            if ask1_price > my_price and ask1_price > cost_sell_price:
                # 可以上调到更好的价格（但不低于成本卖价）
                new_price = max(ask1_price - config.price_step,
                                cost_sell_price)
                if new_price > my_price:
                    return (True, new_price, False)

            return (False, my_price, False)

        # ============ 原逻辑：跟随市场价格 ============
        # 检查价差
        current_spread = ask1_price - bid1_price
        if current_spread < config.min_spread:
            # 价差过小，暂停跟随
            return (False, my_price, False)

        # 如果卖1不是我的价格，说明被人抢占了
        if abs(ask1_price - my_price) > 0.001:
            if ask1_price < my_price:
                # 有人出价更低，需要调价
                new_price = ask1_price - config.price_step

                # 确保不会让价差低于最小值
                spread_limit = bid1_price + config.min_spread
                new_price = max(new_price, spread_limit)

                # ===== 价格边界保护 =====
                # 1. 绝对价格下限保护
                if config.min_sell_price > 0 and new_price < config.min_sell_price:
                    new_price = config.min_sell_price
                    if new_price >= my_price:
                        # 已达下限，不再跟随
                        return (False, my_price, True)

                # 2. 偏离度保护（相对于启动时的中间价）
                if config.max_price_deviation > 0 and state.reference_mid_price > 0:
                    min_allowed = state.reference_mid_price * \
                        (1 - config.max_price_deviation / 100)
                    if new_price < min_allowed:
                        new_price = min_allowed
                        if new_price >= my_price:
                            # 偏离度已达下限，不再跟随
                            return (False, my_price, True)

                if new_price < my_price:
                    return (True, new_price, False)

        return (False, my_price, False)

    def _mm_record_buy_fill(self, cfg, state: MarketMakerState, filled_shares: int, price: float, fee: float = 0):
        """记录买入成交"""
        state.total_buy_shares += filled_shares
        state.total_buy_cost += filled_shares * price
        state.buy_trade_count += 1
        state.total_fees += fee

        # 更新价格统计
        if price < state.min_buy_price:
            state.min_buy_price = price
        if price > state.max_buy_price:
            state.max_buy_price = price

        # 记录交易历史
        state.trade_history.append({
            'time': time.time(),
            'side': 'buy',
            'shares': filled_shares,
            'price': price,
            'amount': filled_shares * price,
            'fee': fee
        })

        # 更新价差收益统计
        self._mm_update_spread_profit(state)

        print(
            f"[{cfg.remark}] 买入成交 {filled_shares}份 @ {price:.2f}¢, 成本${filled_shares * price:.2f}")

    def _mm_record_sell_fill(self, cfg, state: MarketMakerState, filled_shares: int, price: float, fee: float = 0):
        """记录卖出成交"""
        state.total_sell_shares += filled_shares
        state.total_sell_revenue += filled_shares * price
        state.sell_trade_count += 1
        state.total_fees += fee

        # 更新价格统计
        if price < state.min_sell_price:
            state.min_sell_price = price
        if price > state.max_sell_price:
            state.max_sell_price = price

        # 记录交易历史
        state.trade_history.append({
            'time': time.time(),
            'side': 'sell',
            'shares': filled_shares,
            'price': price,
            'amount': filled_shares * price,
            'fee': fee
        })

        # 计算已实现盈亏
        if state.total_buy_shares > 0:
            avg_cost = state.total_buy_cost / state.total_buy_shares
            profit = (price - avg_cost) * filled_shares - fee
            state.realized_pnl += profit

            # 更新价差收益统计
            self._mm_update_spread_profit(state)

            # 更新最大回撤
            self._mm_update_drawdown(state)

            pnl_str = f"+${profit:.4f}" if profit >= 0 else f"-${abs(profit):.4f}"
            print(
                f"[{cfg.remark}] 卖出成交 {filled_shares}份 @ {price:.2f}¢, 本笔盈亏: {pnl_str}")

    def _mm_update_spread_profit(self, state: MarketMakerState):
        """更新价差收益统计"""
        # 已配对的份额 = min(买入, 卖出)
        new_matched = min(state.total_buy_shares, state.total_sell_shares)

        if new_matched > state.matched_shares and state.total_buy_shares > 0 and state.total_sell_shares > 0:
            # 计算平均买入价和平均卖出价
            avg_buy = state.total_buy_cost / state.total_buy_shares
            avg_sell = state.total_sell_revenue / state.total_sell_shares

            # 价差收益 = 配对份额 * (平均卖价 - 平均买价)
            state.spread_profit = new_matched * (avg_sell - avg_buy)
            state.matched_shares = new_matched

    def _mm_update_drawdown(self, state: MarketMakerState):
        """更新最大回撤"""
        # 更新峰值
        if state.realized_pnl > state.peak_pnl:
            state.peak_pnl = state.realized_pnl

        # 计算当前回撤
        if state.peak_pnl > 0:
            current_drawdown = state.peak_pnl - state.realized_pnl
            if current_drawdown > state.max_drawdown:
                state.max_drawdown = current_drawdown
                state.max_drawdown_percent = (
                    current_drawdown / state.peak_pnl) * 100

    def _mm_check_position_limit(self, client, cfg, config: MarketMakerConfig,
                                 state: MarketMakerState) -> bool:
        """检查是否超出仓位限制
        返回: True 表示可以继续买入, False 表示已达上限
        """
        shares, _, current_value = self._mm_get_current_position(
            client, config.token_id)

        # 按份额限制
        if config.max_position_shares > 0:
            if shares >= config.max_position_shares:
                return False

        # 按金额限制
        if config.max_position_amount > 0:
            if current_value >= config.max_position_amount:
                return False

        # 按净资产百分比限制
        if config.max_position_percent > 0:
            balance = self.get_usdt_balance(cfg)
            net_worth = balance + current_value
            if net_worth > 0:
                position_percent = (current_value / net_worth) * 100
                if position_percent >= config.max_position_percent:
                    return False

        return True

    def _mm_check_stop_loss(self, client, cfg, config: MarketMakerConfig,
                            state: MarketMakerState, current_bid1: float) -> bool:
        """检查是否触发止损条件"""
        # 价格止损
        if config.stop_loss_price > 0:
            if current_bid1 <= config.stop_loss_price:
                return True

        # 获取持仓信息
        shares, avg_cost, current_value = self._mm_get_current_position(
            client, config.token_id)

        if shares <= 0:
            return False

        # 计算浮动盈亏
        cost_basis = shares * avg_cost
        unrealized_pnl = current_value - cost_basis

        # 亏损金额止损
        if config.stop_loss_amount > 0:
            if unrealized_pnl <= -config.stop_loss_amount:
                return True

        # 亏损百分比止损
        if config.stop_loss_percent > 0 and cost_basis > 0:
            loss_percent = (unrealized_pnl / cost_basis) * 100
            if loss_percent <= -config.stop_loss_percent:
                return True

        return False

    def _mm_execute_stop_loss(self, client, cfg, config: MarketMakerConfig,
                              state: MarketMakerState, bids: list):
        """执行止损操作"""
        print(f"\n[{cfg.remark}] ========== 执行止损 ==========")

        # 1. 撤销所有买单
        print(f"[{cfg.remark}] 步骤1: 撤销买单...")
        self._mm_cancel_order_safe(client, state.buy_order_id)
        state.buy_order_id = None

        # 同时撤销卖单
        self._mm_cancel_order_safe(client, state.sell_order_id)
        state.sell_order_id = None

        # 2. 获取当前持仓
        shares, avg_cost, _ = self._mm_get_current_position(
            client, config.token_id)
        if shares <= 0:
            print(f"[{cfg.remark}] 无持仓需要止损")
            state.stop_loss_triggered = True
            return

        print(f"[{cfg.remark}] 需止损: {shares}份, 成本: {self.format_price(avg_cost)}¢")

        # 3. 检查买盘深度
        print(f"[{cfg.remark}] 步骤2: 检查买盘深度...")
        depth_sufficient, total_depth = self._mm_check_bid_depth(bids, config)

        if depth_sufficient:
            # 4a. 深度足够，以买1价格卖出（接近市价）
            print(f"[{cfg.remark}] 买盘深度充足: ${total_depth:.2f}, 执行止损卖出")
            bid1_price = float(bids[0].price)
            self._mm_market_sell_stop_loss(
                client, cfg, config, shares, bid1_price)
        else:
            # 4b. 深度不足，挂卖1止损
            print(f"[{cfg.remark}] 买盘深度不足: ${total_depth:.2f}, 挂卖1止损")
            self._mm_limit_sell_stop_loss(client, cfg, config, state, shares)

        state.stop_loss_triggered = True

    def _mm_check_bid_depth(self, bids: list, config: MarketMakerConfig) -> tuple:
        """检查买盘深度
        返回: (is_sufficient: bool, total_amount: float)
        """
        if len(bids) < config.min_depth_levels:
            return (False, 0)

        total_amount = 0
        for bid in bids[:config.min_depth_levels]:
            price = float(bid.price)
            size = float(bid.size)
            total_amount += price * size

        return (total_amount >= config.min_depth_amount, total_amount)

    def _mm_market_sell_stop_loss(self, client, cfg, config: MarketMakerConfig,
                                  shares: int, price: float):
        """市价止损卖出"""
        order = PlaceOrderDataInput(
            marketId=config.market_id,
            tokenId=config.token_id,
            side=OrderSide.SELL,
            orderType=LIMIT_ORDER,  # 以买1价格挂单，接近市价成交
            price=f"{price:.6f}",
            makerAmountInBaseToken=shares
        )

        try:
            result = client.place_order(order, check_approval=True)
            if result.errno == 0:
                print(
                    f"[{cfg.remark}] ✓ 止损卖出: {shares}份 @ {self.format_price(price)}¢")
            else:
                print(
                    f"[{cfg.remark}] ✗ 止损卖出失败: {self.translate_error(result.errmsg)}")
        except Exception as e:
            print(f"[{cfg.remark}] ✗ 止损卖出异常: {e}")

    def _mm_limit_sell_stop_loss(self, client, cfg, config: MarketMakerConfig,
                                 state: MarketMakerState, shares: int):
        """挂卖1止损 - 持续抢卖1位置直到清仓"""
        remaining = shares
        max_attempts = 30  # 最多尝试30次

        for attempt in range(max_attempts):
            if remaining <= 0:
                break

            # 获取最新盘口
            orderbook = self._mm_get_orderbook(client, config.token_id)
            if not orderbook or not orderbook.bids:
                time.sleep(2)
                continue

            bids = sorted(orderbook.bids, key=lambda x: float(
                x.price), reverse=True)
            sell_price = float(bids[0].price)

            # 挂卖单
            order = PlaceOrderDataInput(
                marketId=config.market_id,
                tokenId=config.token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=f"{sell_price:.6f}",
                makerAmountInBaseToken=remaining
            )

            try:
                result = client.place_order(order, check_approval=True)
                if result.errno != 0:
                    print(
                        f"[{cfg.remark}] ✗ 止损挂单失败: {self.translate_error(result.errmsg)}")
                    time.sleep(2)
                    continue

                order_id = result.result.order_id
                print(
                    f"[{cfg.remark}] 止损挂卖: {remaining}份 @ {self.format_price(sell_price)}¢")

                # 等待成交
                for _ in range(10):  # 等待20秒
                    time.sleep(2)
                    order_info = self._mm_get_order_status(client, order_id)
                    if order_info:
                        filled = int(float(order_info.filled_shares or 0))
                        if filled > 0:
                            remaining -= filled
                            print(
                                f"[{cfg.remark}] 止损成交: {filled}份, 剩余{remaining}份")

                        if order_info.status != 1:  # 非Pending
                            break

                        # 检查是否被抢位
                        new_ob = self._mm_get_orderbook(
                            client, config.token_id)
                        if new_ob and new_ob.bids:
                            new_bids = sorted(
                                new_ob.bids, key=lambda x: float(x.price), reverse=True)
                            new_bid1 = float(new_bids[0].price)
                            if new_bid1 < sell_price - 0.001:
                                # 买1下移，撤单重挂
                                self._mm_cancel_order_safe(client, order_id)
                                break
                    else:
                        break

                # 撤销未成交订单
                self._mm_cancel_order_safe(client, order_id)

            except Exception as e:
                print(f"[{cfg.remark}] ✗ 止损异常: {e}")
                time.sleep(2)

        if remaining > 0:
            print(f"[{cfg.remark}] [!] 止损未完成，剩余{remaining}份")

    def _mm_cancel_all_orders(self, client, cfg, state: MarketMakerState):
        """撤销所有挂单"""
        if state.buy_order_id:
            self._mm_cancel_order_safe(client, state.buy_order_id)
            state.buy_order_id = None
        if state.sell_order_id:
            self._mm_cancel_order_safe(client, state.sell_order_id)
            state.sell_order_id = None

    def _mm_show_summary(self, states: dict):
        """显示做市商运行汇总（增强版）"""
        print(f"\n{'='*60}")
        print(f"{'做市商运行汇总':^60}")
        print(f"{'='*60}")

        # 汇总统计
        total_buy_shares = 0
        total_buy_cost = 0
        total_sell_shares = 0
        total_sell_revenue = 0
        total_realized_pnl = 0
        total_spread_profit = 0
        total_fees = 0
        total_buy_trades = 0
        total_sell_trades = 0
        total_max_drawdown = 0
        earliest_start = float('inf')
        latest_end = 0

        for acc_idx, state in states.items():
            cfg = self.configs[acc_idx - 1]

            # 记录结束时间
            state.end_time = time.time()

            # 计算运行时长
            duration = state.end_time - state.start_time if state.start_time > 0 else 0
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            seconds = int(duration % 60)

            print(f"\n┌{'─'*56}┐")
            print(f"│ [{cfg.remark}]")
            print(f"├{'─'*56}┤")

            # 运行时长
            if hours > 0:
                duration_str = f"{hours}小时{minutes}分{seconds}秒"
            elif minutes > 0:
                duration_str = f"{minutes}分{seconds}秒"
            else:
                duration_str = f"{seconds}秒"
            print(f"│ 运行时长: {duration_str}")

            # 交易统计
            total_trades = state.buy_trade_count + state.sell_trade_count
            print(
                f"│ 交易次数: {total_trades}笔 (买{state.buy_trade_count}笔 / 卖{state.sell_trade_count}笔)")

            # 买入统计
            if state.total_buy_shares > 0:
                avg_buy = state.total_buy_cost / state.total_buy_shares
                buy_price_range = ""
                if state.max_buy_price > 0:
                    buy_price_range = f" ({self.format_price(state.min_buy_price)}~{self.format_price(state.max_buy_price)}c)"
                print(
                    f"│ 买入: {state.total_buy_shares}份, 成本${state.total_buy_cost:.2f}, 均价{self.format_price(avg_buy)}c{buy_price_range}")
            else:
                print(f"│ 买入: 0份")

            # 卖出统计
            if state.total_sell_shares > 0:
                avg_sell = state.total_sell_revenue / state.total_sell_shares
                sell_price_range = ""
                if state.max_sell_price > 0:
                    sell_price_range = f" ({self.format_price(state.min_sell_price)}~{self.format_price(state.max_sell_price)}c)"
                print(
                    f"│ 卖出: {state.total_sell_shares}份, 收入${state.total_sell_revenue:.2f}, 均价{self.format_price(avg_sell)}c{sell_price_range}")
            else:
                print(f"│ 卖出: 0份")

            # 净持仓
            net_position = state.total_buy_shares - state.total_sell_shares
            if net_position != 0:
                net_str = f"+{net_position}" if net_position > 0 else str(
                    net_position)
                print(f"│ 净持仓变化: {net_str}份")

            # 价差收益
            if state.matched_shares > 0:
                spread_str = f"+${state.spread_profit:.4f}" if state.spread_profit >= 0 else f"-${abs(state.spread_profit):.4f}"
                print(f"│ 价差收益: {spread_str} (配对{state.matched_shares}份)")

            # 手续费
            if state.total_fees > 0:
                print(f"│ 手续费: ${state.total_fees:.4f}")

            # 已实现盈亏
            pnl_str = f"+${state.realized_pnl:.4f}" if state.realized_pnl >= 0 else f"-${abs(state.realized_pnl):.4f}"
            print(f"│ 已实现盈亏: {pnl_str}")

            # 盈亏率
            if state.total_buy_cost > 0:
                pnl_rate = (state.realized_pnl / state.total_buy_cost) * 100
                rate_str = f"+{pnl_rate:.2f}%" if pnl_rate >= 0 else f"{pnl_rate:.2f}%"
                print(f"│   盈亏率: {rate_str}")

            # 每小时盈亏
            if duration > 60:  # 超过1分钟才显示
                hourly_pnl = (state.realized_pnl / duration) * 3600
                hourly_str = f"+${hourly_pnl:.4f}" if hourly_pnl >= 0 else f"-${abs(hourly_pnl):.4f}"
                print(f"│   时均盈亏: {hourly_str}/小时")

            # 最大回撤
            if state.max_drawdown > 0:
                print(
                    f"│ 最大回撤: ${state.max_drawdown:.4f} ({state.max_drawdown_percent:.1f}%)")

            # 状态标记
            status_flags = []
            if state.stop_loss_triggered:
                status_flags.append("已止损")
            if state.position_limit_reached:
                status_flags.append("达仓位上限")
            if state.depth_drop_triggered:
                status_flags.append("深度异常")
            if status_flags:
                print(f"│ [!] 状态: {', '.join(status_flags)}")

            print(f"└{'─'*56}┘")

            # 累加汇总
            total_buy_shares += state.total_buy_shares
            total_buy_cost += state.total_buy_cost
            total_sell_shares += state.total_sell_shares
            total_sell_revenue += state.total_sell_revenue
            total_realized_pnl += state.realized_pnl
            total_spread_profit += state.spread_profit
            total_fees += state.total_fees
            total_buy_trades += state.buy_trade_count
            total_sell_trades += state.sell_trade_count
            total_max_drawdown = max(total_max_drawdown, state.max_drawdown)
            if state.start_time > 0:
                earliest_start = min(earliest_start, state.start_time)
            if state.end_time > 0:
                latest_end = max(latest_end, state.end_time)

        # 多账户汇总
        if len(states) > 1:
            print(f"\n{'='*60}")
            print(f"{'总计汇总':^60}")
            print(f"{'='*60}")

            # 总运行时长
            total_duration = latest_end - \
                earliest_start if earliest_start < float('inf') else 0
            hours = int(total_duration // 3600)
            minutes = int((total_duration % 3600) // 60)
            if hours > 0:
                print(f"  总时长: {hours}小时{minutes}分")
            else:
                print(f"  总时长: {minutes}分")

            total_trades = total_buy_trades + total_sell_trades
            print(
                f"  总交易: {total_trades}笔 (买{total_buy_trades}笔 / 卖{total_sell_trades}笔)")
            print(f"  总买入: {total_buy_shares}份, 成本${total_buy_cost:.2f}")
            print(f"  总卖出: {total_sell_shares}份, 收入${total_sell_revenue:.2f}")

            net_pos = total_buy_shares - total_sell_shares
            if net_pos != 0:
                net_str = f"+{net_pos}" if net_pos > 0 else str(net_pos)
                print(f"  净持仓变化: {net_str}份")

            if total_spread_profit != 0:
                spread_str = f"+${total_spread_profit:.4f}" if total_spread_profit >= 0 else f"-${abs(total_spread_profit):.4f}"
                print(f"  总价差收益: {spread_str}")

            if total_fees > 0:
                print(f"  总手续费: ${total_fees:.4f}")

            # 总盈亏
            pnl_str = f"+${total_realized_pnl:.4f}" if total_realized_pnl >= 0 else f"-${abs(total_realized_pnl):.4f}"
            print(f"\n  总已实现盈亏: {pnl_str}")

            if total_buy_cost > 0:
                pnl_rate = (total_realized_pnl / total_buy_cost) * 100
                rate_str = f"+{pnl_rate:.2f}%" if pnl_rate >= 0 else f"{pnl_rate:.2f}%"
                print(f"    盈亏率: {rate_str}")

            if total_duration > 60:
                hourly_pnl = (total_realized_pnl / total_duration) * 3600
                hourly_str = f"+${hourly_pnl:.4f}" if hourly_pnl >= 0 else f"-${abs(hourly_pnl):.4f}"
                print(f"    时均盈亏: {hourly_str}/小时")

        print(f"\n{'='*60}")

    # ============ 网格策略方法 ============

    def _grid_place_buy_orders(self, client, cfg, config: MarketMakerConfig,
                               state: MarketMakerState, bids: list):
        """网格策略：挂多层买单

        根据当前买1价格，在多个价格层级挂买单
        例如：买1=75¢，网格层数=5，层间距=1¢
        则在 75¢、74¢、73¢、72¢、71¢ 各挂一单
        """
        if not bids:
            return

        bid1_price = float(bids[0].price)

        # 检查已有的网格买单
        existing_prices = {order['price'] for order in state.grid_buy_orders}

        orders_placed = 0
        for level in range(config.grid_levels):
            # 计算该层价格
            level_price = bid1_price - level * config.grid_level_spread / 100  # 转换为小数
            level_price = round(level_price, 6)

            if level_price <= 0:
                continue

            # 检查价格边界
            if config.max_buy_price > 0 and level_price > config.max_buy_price / 100:
                continue

            # 检查是否已有该价格的买单
            if level_price in existing_prices:
                continue

            # 挂买单
            try:
                order = PlaceOrderDataInput(
                    marketId=config.market_id,
                    tokenId=config.token_id,
                    side=OrderSide.BUY,
                    orderType=LIMIT_ORDER,
                    price=f"{level_price:.6f}",
                    makerAmountInQuoteToken=round(
                        config.grid_amount_per_level, 2)
                )

                result = client.place_order(order, check_approval=True)
                if result.errno == 0:
                    order_info = {
                        'order_id': result.result.order_id,
                        'price': level_price,
                        'amount': config.grid_amount_per_level,
                        'level': level
                    }
                    state.grid_buy_orders.append(order_info)
                    orders_placed += 1
                    print(
                        f"[{cfg.remark}] ✓ 网格买{level+1}: ${config.grid_amount_per_level:.2f} @ {self.format_price(level_price)}¢")
                else:
                    print(
                        f"[{cfg.remark}] ✗ 网格买{level+1}失败: {self.translate_error(result.errmsg)}")
            except Exception as e:
                print(f"[{cfg.remark}] ✗ 网格买{level+1}异常: {e}")

        if orders_placed > 0:
            print(f"[{cfg.remark}] 网格买单已挂出 {orders_placed} 层")

    def _grid_check_buy_filled(self, client, cfg, config: MarketMakerConfig,
                               state: MarketMakerState):
        """网格策略：检查买单成交情况

        检查网格买单是否成交，成交后：
        1. 记录买入成本到 grid_positions
        2. 按买入价+利润价差挂出卖单
        """
        if not state.grid_buy_orders:
            return

        filled_orders = []
        remaining_orders = []

        for order_info in state.grid_buy_orders:
            try:
                # 查询订单状态
                order_result = client.get_order(order_info['order_id'])
                if order_result.errno == 0:
                    order = order_result.result
                    status = order.status if hasattr(order, 'status') else None

                    # 检查是否成交
                    if status in ['FILLED', 'filled', 2]:  # 完全成交
                        filled_orders.append(order_info)

                        # 计算成交份额
                        buy_price = order_info['price']
                        amount = order_info['amount']
                        shares = int(
                            amount / buy_price) if buy_price > 0 else 0

                        # 记录到持仓追踪
                        position_info = {
                            'buy_price': buy_price,
                            'shares': shares,
                            'buy_time': time.time(),
                            'sell_order_id': None,
                            'sell_price': 0
                        }
                        state.grid_positions.append(position_info)

                        # 更新统计
                        state.total_buy_shares += shares
                        state.total_buy_cost += amount
                        state.buy_trade_count += 1

                        print(
                            f"[{cfg.remark}] ✓ 网格买单成交: {shares}份 @ {self.format_price(buy_price)}¢ (${amount:.2f})")

                        # 计算卖出价并挂卖单
                        sell_price = buy_price + config.grid_profit_spread / 100  # 转换为小数

                        # 检查卖出价是否满足最小利润
                        if (sell_price - buy_price) * 100 >= config.grid_min_profit_spread:
                            self._grid_place_sell_order(client, cfg, config, state,
                                                        position_info, sell_price, shares)
                    elif status in ['PENDING', 'pending', 'OPEN', 'open', 0, 1]:
                        remaining_orders.append(order_info)
                    # 其他状态（取消等）则移除
                else:
                    remaining_orders.append(order_info)
            except Exception as e:
                print(f"[{cfg.remark}] 查询买单状态异常: {e}")
                remaining_orders.append(order_info)

        state.grid_buy_orders = remaining_orders

    def _grid_place_sell_order(self, client, cfg, config: MarketMakerConfig,
                               state: MarketMakerState, position_info: dict,
                               sell_price: float, shares: int):
        """网格策略：为成交的买单挂对应的卖单

        卖出价 = 买入价 + 利润价差
        """
        try:
            order = PlaceOrderDataInput(
                marketId=config.market_id,
                tokenId=config.token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=f"{sell_price:.6f}",
                makerAmountInBaseToken=shares
            )

            result = client.place_order(order, check_approval=True)
            if result.errno == 0:
                sell_order_info = {
                    'order_id': result.result.order_id,
                    'price': sell_price,
                    'shares': shares,
                    'buy_price': position_info['buy_price']
                }
                state.grid_sell_orders.append(sell_order_info)

                # 更新持仓记录
                position_info['sell_order_id'] = result.result.order_id
                position_info['sell_price'] = sell_price

                profit_spread = (sell_price - position_info['buy_price']) * 100
                print(
                    f"[{cfg.remark}] ✓ 网格卖单: {shares}份 @ {self.format_price(sell_price)}¢ (利润{profit_spread:.1f}¢)")
            else:
                print(
                    f"[{cfg.remark}] ✗ 网格卖单失败: {self.translate_error(result.errmsg)}")
        except Exception as e:
            print(f"[{cfg.remark}] ✗ 网格卖单异常: {e}")

    def _grid_check_sell_filled(self, client, cfg, config: MarketMakerConfig,
                                state: MarketMakerState, bids: list):
        """网格策略：检查卖单成交情况

        卖单成交后：
        1. 计算并记录利润
        2. 从持仓中移除
        3. 如果启用自动再平衡，在原买入价位重新挂买单
        """
        if not state.grid_sell_orders:
            return

        filled_orders = []
        remaining_orders = []

        for order_info in state.grid_sell_orders:
            try:
                order_result = client.get_order(order_info['order_id'])
                if order_result.errno == 0:
                    order = order_result.result
                    status = order.status if hasattr(order, 'status') else None

                    if status in ['FILLED', 'filled', 2]:
                        filled_orders.append(order_info)

                        # 计算收益
                        sell_price = order_info['price']
                        buy_price = order_info['buy_price']
                        shares = order_info['shares']
                        revenue = sell_price * shares
                        cost = buy_price * shares
                        profit = revenue - cost

                        # 更新统计
                        state.total_sell_shares += shares
                        state.total_sell_revenue += revenue
                        state.sell_trade_count += 1
                        state.realized_pnl += profit
                        state.spread_profit += profit
                        state.matched_shares += shares

                        profit_spread = (sell_price - buy_price) * 100
                        print(f"[{cfg.remark}] ✓ 网格卖单成交: {shares}份 @ {self.format_price(sell_price)}¢ "
                              f"(买入{self.format_price(buy_price)}¢, 利润{profit_spread:.1f}¢, +${profit:.2f})")

                        # 从持仓中移除对应记录
                        state.grid_positions = [p for p in state.grid_positions
                                                if p.get('sell_order_id') != order_info['order_id']]

                        # 自动再平衡：在买1价重新挂买单
                        if config.grid_auto_rebalance and bids:
                            bid1_price = float(bids[0]['price'])
                            self._grid_rebalance_buy(
                                client, cfg, config, state, bid1_price)
                    elif status in ['PENDING', 'pending', 'OPEN', 'open', 0, 1]:
                        remaining_orders.append(order_info)
                else:
                    remaining_orders.append(order_info)
            except Exception as e:
                print(f"[{cfg.remark}] 查询卖单状态异常: {e}")
                remaining_orders.append(order_info)

        state.grid_sell_orders = remaining_orders

    def _grid_rebalance_buy(self, client, cfg, config: MarketMakerConfig,
                            state: MarketMakerState, target_price: float):
        """网格策略：再平衡 - 在指定价格重新挂买单"""
        try:
            order = PlaceOrderDataInput(
                marketId=config.market_id,
                tokenId=config.token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=f"{target_price:.6f}",
                makerAmountInQuoteToken=round(config.grid_amount_per_level, 2)
            )

            result = client.place_order(order, check_approval=True)
            if result.errno == 0:
                order_info = {
                    'order_id': result.result.order_id,
                    'price': target_price,
                    'amount': config.grid_amount_per_level,
                    'level': -1  # 再平衡订单
                }
                state.grid_buy_orders.append(order_info)
                print(
                    f"[{cfg.remark}] ✓ 网格再平衡: ${config.grid_amount_per_level:.2f} @ {self.format_price(target_price)}¢")
        except Exception as e:
            print(f"[{cfg.remark}] ✗ 网格再平衡失败: {e}")

    def _grid_cancel_all_orders(self, client, cfg, config: MarketMakerConfig,
                                state: MarketMakerState):
        """网格策略：撤销所有网格订单"""
        cancelled = 0

        # 撤销买单
        for order_info in state.grid_buy_orders:
            try:
                result = client.cancel_order(order_info['order_id'])
                if result.errno == 0:
                    cancelled += 1
            except Exception:
                pass

        # 撤销卖单
        for order_info in state.grid_sell_orders:
            try:
                result = client.cancel_order(order_info['order_id'])
                if result.errno == 0:
                    cancelled += 1
            except Exception:
                pass

        state.grid_buy_orders = []
        state.grid_sell_orders = []

        if cancelled > 0:
            print(f"[{cfg.remark}] 已撤销 {cancelled} 个网格订单")

    def _grid_show_status(self, cfg, state: MarketMakerState):
        """显示网格策略状态"""
        print(f"\n[{cfg.remark}] 网格状态:")
        print(f"  买单挂出: {len(state.grid_buy_orders)} 层")
        print(f"  卖单挂出: {len(state.grid_sell_orders)} 层")
        print(f"  持仓追踪: {len(state.grid_positions)} 笔")

        if state.grid_positions:
            total_shares = sum(p['shares'] for p in state.grid_positions)
            avg_cost = sum(p['buy_price'] * p['shares']
                           for p in state.grid_positions) / total_shares if total_shares > 0 else 0
            print(f"  持仓份额: {total_shares}")
            print(f"  平均成本: {self.format_price(avg_cost)}¢")

        if state.spread_profit != 0:
            print(f"  网格利润: ${state.spread_profit:.2f}")

    # ============ 做市商策略相关方法结束 ============

    def execute_resume_sell(self, selected_account_indices, market_id, token_id, sell_price, split_count, available_to_sell):
        """执行恢复挂卖（挂出之前买入成交的份额）"""
        import threading

        print(f"\n{'='*60}")
        print(f"开始挂出之前买入成交的份额")
        print(f"{'='*60}")

        price_str = f"{sell_price:.6f}"
        price_display = self.format_price(sell_price) + '¢'

        print_lock = threading.Lock()

        def execute_for_account(acc_idx):
            client = self.clients[acc_idx - 1]
            config = self.configs[acc_idx - 1]

            total_shares = available_to_sell.get(acc_idx, 0)
            if total_shares <= 0:
                with print_lock:
                    print(f"  [{config.remark}] 无可挂出份额，跳过")
                return

            with print_lock:
                print(
                    f"\n[{config.remark}] 开始挂卖 {total_shares}份，分{split_count}笔...")

            success_count = 0
            fail_count = 0
            remaining_shares = total_shares

            for i in range(1, split_count + 1):
                if remaining_shares <= 0:
                    break

                try:
                    # 计算本笔份额
                    if i == split_count:
                        # 最后一笔：挂出剩余全部
                        shares = remaining_shares
                    else:
                        # 平均分配，带随机波动
                        avg_shares = total_shares / split_count
                        shares = int(avg_shares * random.uniform(0.8, 1.2))
                        # 确保不超过剩余份额，且留够后续笔数
                        remaining_orders = split_count - i
                        min_for_remaining = remaining_orders * 1  # 每笔至少1份
                        max_allowed = remaining_shares - min_for_remaining
                        shares = min(shares, max_allowed)
                        shares = max(shares, 1)

                    order = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.SELL,
                        orderType=LIMIT_ORDER,
                        price=price_str,
                        makerAmountInBaseToken=shares
                    )

                    result = client.place_order(order, check_approval=True)

                    with print_lock:
                        if result.errno == 0:
                            print(
                                f"  [{config.remark}] ✓ 挂卖#{i}: {shares}份 @ {price_display}")
                            success_count += 1
                            remaining_shares -= shares
                        else:
                            print(
                                f"  [{config.remark}] ✗ 挂卖#{i}: {self.translate_error(result.errmsg)}")
                            fail_count += 1

                    # 随机延迟
                    time.sleep(random.uniform(0.5, 1.5))

                except Exception as e:
                    with print_lock:
                        print(f"  [{config.remark}] ✗ 挂卖#{i}异常: {e}")
                    fail_count += 1

            with print_lock:
                print(
                    f"  [{config.remark}] 完成: 成功{success_count}, 失败{fail_count}")

        # 串行执行所有账户（稳定模式，避免触发限流）
        for i, acc_idx in enumerate(selected_account_indices):
            execute_for_account(acc_idx)
            # 账户之间短暂延迟
            if i < len(selected_account_indices) - 1:
                time.sleep(random.uniform(1, 2))

        print(f"\n{'='*60}")
        print(f"{'挂卖执行完成':^60}")
        print(f"{'='*60}")

    def custom_strategy_menu(self):
        """自定义策略菜单"""
        print(f"\n{'='*60}")
        print(f"{'自定义交易策略':^60}")
        print(f"{'='*60}")
        print("第1步: 输入交易序列")
        print("  格式: 买买买卖卖 或 卖卖买买卖")
        print("  规则: 连续相同操作=并发执行，不同操作=顺序执行")
        print(f"{'='*60}")

        strategy_input = input("\n交易序列 (留空返回): ").strip()
        if not strategy_input:
            return

        # 简化解析：只识别买/卖
        strategy_input = strategy_input.replace('买', 'B').replace('卖', 'S')
        operations = []
        for char in strategy_input.upper():
            if char == 'B':
                operations.append('buy')
            elif char == 'S':
                operations.append('sell')

        if not operations:
            print("✗ 无法解析，请只输入'买'或'卖'")
            return

        # 分组操作
        groups = []
        current_type = operations[0]
        current_count = 1
        for op in operations[1:]:
            if op == current_type:
                current_count += 1
            else:
                groups.append({'type': current_type, 'count': current_count})
                current_type = op
                current_count = 1
        groups.append({'type': current_type, 'count': current_count})

        # 统计
        total_buys = sum(g['count'] for g in groups if g['type'] == 'buy')
        total_sells = sum(g['count'] for g in groups if g['type'] == 'sell')

        # 显示解析结果
        print(f"\n解析结果:")
        for i, group in enumerate(groups, 1):
            op_name = "买入" if group['type'] == 'buy' else "卖出"
            concurrent = "并发" if group['count'] > 1 else ""
            print(f"  第{i}步: {concurrent}{op_name} x{group['count']}")
        print(f"\n总计: 买入{total_buys}次, 卖出{total_sells}次")

        # 询问市场ID
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 获取市场信息
        client = self.clients[0]

        try:
            print(f"\n正在获取市场 {market_id} 的信息...")

            categorical_response = client.get_categorical_market(
                market_id=market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                market_data = categorical_response.result.data
                if not hasattr(market_data, 'market_title') or not market_data.market_title:
                    print(f"✗ 市场 {market_id} 数据不完整")
                    return

                parent_market_title = market_data.market_title
                print(f"\n✓ 找到分类市场: {parent_market_title}")

                if hasattr(market_data, 'child_markets') and market_data.child_markets and len(market_data.child_markets) > 0:
                    child_markets = market_data.child_markets

                    print(f"\n找到 {len(child_markets)} 个子市场:")
                    for idx, child in enumerate(child_markets, 1):
                        title = child.market_title if hasattr(
                            child, 'market_title') else 'N/A'
                        child_id = child.market_id if hasattr(
                            child, 'market_id') else 'N/A'
                        print(f"  {idx}. [{child_id}] {title}")
                    print(f"  0. 返回")

                    choice_input = input(
                        f"\n请选择子市场 (0-{len(child_markets)}): ").strip()
                    if not choice_input or choice_input == '0':
                        return

                    try:
                        choice = int(choice_input)
                    except ValueError:
                        print("✗ 请输入有效的数字")
                        return

                    if choice < 1 or choice > len(child_markets):
                        print("✗ 无效的选择")
                        return

                    selected_child = child_markets[choice - 1]
                    market_id = selected_child.market_id

                    detail_response = client.get_market(market_id=market_id)
                    if detail_response.errno != 0 or not detail_response.result or not detail_response.result.data:
                        print(f"✗ 获取子市场详细信息失败")
                        return

                    market_data = detail_response.result.data
                else:
                    print(f"  (无子市场，直接交易此市场)")
            else:
                market_response = client.get_market(market_id=market_id)

                if market_response.errno != 0 or not market_response.result or not market_response.result.data:
                    print(f"✗ 市场 {market_id} 不存在")
                    return

                market_data = market_response.result.data
                print(f"\n✓ 找到二元市场: {market_data.market_title}")

        except Exception as e:
            print(f"✗ 获取市场信息失败: {e}")
            return

        # 选择交易方向
        print(f"\n请选择交易方向:")
        print(f"  1. YES")
        print(f"  2. NO")
        print(f"  0. 返回")
        side_choice = input("请输入选项 (0-2): ").strip()

        if side_choice == '0' or not side_choice:
            return
        elif side_choice == '1':
            token_id = market_data.yes_token_id
            selected_token_name = "YES"
        elif side_choice == '2':
            token_id = market_data.no_token_id
            selected_token_name = "NO"
        else:
            print("✗ 无效选择")
            return

        print(f"\n✓ 已选择: {selected_token_name}")

        # 先查询所有账户余额
        print(f"\n{'='*60}")
        print(f"{'查询账户余额':^60}")
        print(f"{'='*60}")
        # display_account_balances 使用 1-based 索引
        all_indices = list(range(1, len(self.clients) + 1))
        all_balances = self.display_account_balances(all_indices)

        # 选择账户
        print(f"\n  输入格式示例: 留空=全部, 1,2,3 或 1-3")
        account_input = input(f"\n请选择账户 (留空=全部): ").strip()
        selected_indices = self.parse_account_selection(
            account_input, len(self.clients))

        if not selected_indices:
            print("✗ 未选择任何账户")
            return

        print(f"✓ 已选择 {len(selected_indices)} 个账户")

        # 查询当前盘口价格
        print(f"\n正在获取当前盘口...")
        ob = OrderbookService.fetch(client, token_id)
        if ob['success']:
            ask1_price = ob['ask1_price']
            bid1_price = ob['bid1_price']
            print(f"  卖1价(买入用): {self.format_price(ask1_price)}¢")
            print(f"  买1价(卖出用): {self.format_price(bid1_price)}¢")
        else:
            ask1_price = 0
            bid1_price = 0
            print("  [!] 获取盘口失败，将使用实时价格")

        # 从之前查询的余额中提取选中账户的余额
        account_balances = {}
        if total_buys > 0:
            for acc_idx in selected_indices:
                account_balances[acc_idx] = all_balances.get(acc_idx, 0)

        # 查询持仓（如果有卖出操作）
        account_positions = {}
        if total_sells > 0:
            print(f"\n查询各账户持仓...")
            for acc_idx in selected_indices:
                acc_client = self.clients[acc_idx - 1]
                config = self.configs[acc_idx - 1]
                shares = PositionService.get_token_balance(
                    acc_client, token_id)
                account_positions[acc_idx] = shares
                print(f"  [{config.remark}] 持仓: {shares}份")

        # 计算最小可用余额
        min_balance = min(account_balances.values()) if account_balances else 0

        # ===== 设置买入参数 =====
        buy_config = None
        if total_buys > 0:
            print(f"\n{'='*60}")
            print(f"设置买入参数 (共{total_buys}次买入)")
            print(f"{'='*60}")

            # 金额设置
            print("\n金额设置:")
            print("  1. 总金额 (随机分配到各次)")
            print("  2. 单次金额 (每次相同，×1.01-1.10随机)")
            buy_amount_mode = input("请选择 (1/2): ").strip()

            if buy_amount_mode == '1':
                while True:
                    try:
                        total_amount = float(
                            input(f"请输入总金额 (最大可用: ${min_balance:.2f}): ").strip())
                        if total_amount <= 0:
                            print("✗ 金额必须大于0")
                            continue
                        if total_amount > min_balance:
                            print(
                                f"✗ 总金额 ${total_amount:.2f} 超过可用余额 ${min_balance:.2f}")
                            print("  请减少买入金额或确保有足够余额")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的数字")
                buy_config = {'mode': 'total',
                              'total_amount': total_amount, 'count': total_buys}
            else:
                while True:
                    try:
                        single_amount = float(input("请输入单次金额 ($): ").strip())
                        if single_amount <= 0:
                            print("✗ 金额必须大于0")
                            continue
                        # 检查总金额是否超过余额
                        estimated_total = single_amount * total_buys * 1.10  # 最大可能
                        if estimated_total > min_balance:
                            print(
                                f"✗ 单次${single_amount:.2f}×{total_buys}次×1.10 ≈ ${estimated_total:.2f} 可能超过余额${min_balance:.2f}")
                            print("  请减少单次金额或确保有足够余额")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的数字")
                buy_config = {'mode': 'single',
                              'single_amount': single_amount, 'count': total_buys}

            # 价格设置
            print("\n价格设置:")
            print(f"  1. 卖1价 (当前约 {self.format_price(ask1_price)}¢，立即成交)")
            print("  2. 固定价格")
            print("  3. 价格区间 (随机)")
            buy_price_mode = input("请选择 (1/2/3): ").strip()

            if buy_price_mode == '2':
                while True:
                    try:
                        fixed_price = float(
                            input("请输入固定价格 (0-1，如0.995): ").strip())
                        if not 0 < fixed_price < 1:
                            print("✗ 价格必须在0-1之间")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的数字")
                buy_config['price_mode'] = 'fixed'
                buy_config['price'] = fixed_price
            elif buy_price_mode == '3':
                while True:
                    try:
                        price_range = input("请输入价格区间 (如 0.99-0.995): ").strip()
                        parts = price_range.split('-')
                        min_price = float(parts[0])
                        max_price = float(parts[1])
                        if not (0 < min_price < max_price < 1):
                            print("✗ 价格必须在0-1之间且最小值<最大值")
                            continue
                        break
                    except Exception:
                        print("✗ 格式错误，请输入如 0.99-0.995")
                buy_config['price_mode'] = 'range'
                buy_config['price_min'] = min_price
                buy_config['price_max'] = max_price
            else:
                buy_config['price_mode'] = 'market'

        # ===== 设置卖出参数 =====
        sell_config = None
        if total_sells > 0:
            print(f"\n{'='*60}")
            print(f"设置卖出参数 (共{total_sells}次卖出)")
            print(f"{'='*60}")

            # 份额设置
            print("\n份额设置:")
            print("  1. 全部持仓 (随机分配，最后一次卖剩余)")
            print("  2. 总份额 (随机分配，最后一次卖剩余)")
            print("  3. 单次份额 (每次相同，×1.01-1.10随机)")
            sell_amount_mode = input("请选择 (1/2/3): ").strip()

            if sell_amount_mode == '2':
                # 检查持仓
                min_position = min(account_positions.values()
                                   ) if account_positions else 0
                while True:
                    try:
                        total_shares = int(
                            input(f"请输入总份额 (最大可用: {min_position}): ").strip())
                        if total_shares <= 0:
                            print("✗ 份额必须大于0")
                            continue
                        if total_shares > min_position:
                            print(f"✗ 超过可用持仓 {min_position}，请重新输入")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的整数")
                sell_config = {'mode': 'total',
                               'total_shares': total_shares, 'count': total_sells}
            elif sell_amount_mode == '3':
                min_position = min(account_positions.values()
                                   ) if account_positions else 0
                while True:
                    try:
                        single_shares = int(input("请输入单次份额: ").strip())
                        if single_shares <= 0:
                            print("✗ 份额必须大于0")
                            continue
                        # 检查总份额是否超过持仓
                        estimated_total = int(
                            single_shares * total_sells * 1.1)  # 最大可能
                        if estimated_total > min_position:
                            print(
                                f"✗ 单次{single_shares}×{total_sells}次×1.1 ≈ {estimated_total} 可能超过持仓{min_position}")
                            print("  请减少单次份额或确保有足够持仓")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的整数")
                sell_config = {
                    'mode': 'single', 'single_shares': single_shares, 'count': total_sells}
            else:
                sell_config = {'mode': 'all', 'count': total_sells}

            # 价格设置
            print("\n价格设置:")
            print(f"  1. 买1价 (当前约 {self.format_price(bid1_price)}¢，立即成交)")
            print("  2. 固定价格")
            print("  3. 价格区间 (随机)")
            sell_price_mode = input("请选择 (1/2/3): ").strip()

            if sell_price_mode == '2':
                while True:
                    try:
                        fixed_price = float(
                            input("请输入固定价格 (0-1，如0.99): ").strip())
                        if not 0 < fixed_price < 1:
                            print("✗ 价格必须在0-1之间")
                            continue
                        break
                    except ValueError:
                        print("✗ 请输入有效的数字")
                sell_config['price_mode'] = 'fixed'
                sell_config['price'] = fixed_price
            elif sell_price_mode == '3':
                while True:
                    try:
                        price_range = input("请输入价格区间 (如 0.985-0.99): ").strip()
                        parts = price_range.split('-')
                        min_price = float(parts[0])
                        max_price = float(parts[1])
                        if not (0 < min_price < max_price < 1):
                            print("✗ 价格必须在0-1之间且最小值<最大值")
                            continue
                        break
                    except Exception:
                        print("✗ 格式错误，请输入如 0.985-0.99")
                sell_config['price_mode'] = 'range'
                sell_config['price_min'] = min_price
                sell_config['price_max'] = max_price
            else:
                sell_config['price_mode'] = 'market'

        # ===== 确认信息 =====
        print(f"\n{'='*60}")
        print(f"{'【自定义策略确认】':^60}")
        print(f"{'='*60}")
        print(f"  市场: {market_data.market_title}")
        print(f"  方向: {selected_token_name}")
        print(f"  账户: {len(selected_indices)}个")
        print(f"\n  交易序列:")
        for i, group in enumerate(groups, 1):
            op_name = "买入" if group['type'] == 'buy' else "卖出"
            concurrent = "并发" if group['count'] > 1 else ""
            print(f"    第{i}步: {concurrent}{op_name} x{group['count']}")

        if buy_config:
            print(f"\n  买入设置:")
            if buy_config['mode'] == 'total':
                print(f"    金额: 总${buy_config['total_amount']:.2f} (随机分配)")
            else:
                print(
                    f"    金额: 每次${buy_config['single_amount']:.2f} (×1.01-1.10)")
            if buy_config['price_mode'] == 'market':
                print(f"    价格: 卖1价(立即成交)")
            elif buy_config['price_mode'] == 'fixed':
                print(f"    价格: 固定 {self.format_price(buy_config['price'])}¢")
            else:
                print(
                    f"    价格: {self.format_price(buy_config['price_min'])}¢ - {self.format_price(buy_config['price_max'])}¢")

        if sell_config:
            print(f"\n  卖出设置:")
            if sell_config['mode'] == 'all':
                print(f"    份额: 全部持仓 (随机分配)")
            elif sell_config['mode'] == 'total':
                print(f"    份额: 总{sell_config['total_shares']}份 (随机分配)")
            else:
                print(
                    f"    份额: 每次{sell_config['single_shares']}份 (×1.01-1.10)")
            if sell_config['price_mode'] == 'market':
                print(f"    价格: 买1价(立即成交)")
            elif sell_config['price_mode'] == 'fixed':
                print(f"    价格: 固定 {self.format_price(sell_config['price'])}¢")
            else:
                print(
                    f"    价格: {self.format_price(sell_config['price_min'])}¢ - {self.format_price(sell_config['price_max'])}¢")

        print(f"{'='*60}")

        confirm = input("\n确认无误请输入 'done': ").strip().lower()
        if confirm != 'done':
            print("✗ 已取消")
            return

        # 执行自定义策略
        self.execute_custom_strategy_v2(
            groups=groups,
            market_id=market_id,
            token_id=token_id,
            selected_token_name=selected_token_name,
            selected_indices=selected_indices,
            buy_config=buy_config,
            sell_config=sell_config,
            account_positions=account_positions
        )

    def execute_custom_strategy_v2(self, groups, market_id, token_id, selected_token_name, selected_indices, buy_config, sell_config, account_positions):
        """执行自定义策略V2"""
        import threading
        import random

        print(f"\n{'='*60}")
        print(f"{'执行自定义策略':^60}")
        print(f"{'='*60}")

        # 计算买入金额计划
        buy_amounts = []
        if buy_config:
            total_buys = buy_config['count']
            if buy_config['mode'] == 'total':
                # 总金额随机分配
                total = buy_config['total_amount']
                if total_buys <= 0:
                    print("✗ 买入次数必须大于0")
                    return False, {}
                avg = total / total_buys
                remaining = total
                for i in range(total_buys):
                    if i == total_buys - 1:
                        buy_amounts.append(round(remaining, 2))
                    else:
                        min_amt = max(1.5, avg * 0.8)  # 最低$1.5
                        max_amt = min(
                            remaining - (total_buys - i - 1) * 1.5, avg * 1.2)
                        amt = round(random.uniform(min_amt, max_amt), 2)
                        buy_amounts.append(amt)
                        remaining -= amt
            else:
                # 单次金额，乘以1.01-1.10随机
                single = buy_config['single_amount']
                for _ in range(total_buys):
                    buy_amounts.append(
                        round(single * random.uniform(1.01, 1.10), 2))

            print(
                f"\n买入金额计划: {' + '.join([f'${a:.2f}' for a in buy_amounts])} = ${sum(buy_amounts):.2f}")

        # 计算卖出份额计划（每个账户）
        account_sell_plans = {}
        if sell_config:
            total_sells = sell_config['count']
            for acc_idx in selected_indices:
                position = account_positions.get(acc_idx, 0)
                config = self.configs[acc_idx - 1]

                if sell_config['mode'] == 'all':
                    # 全部持仓
                    total_shares = position
                elif sell_config['mode'] == 'total':
                    # 指定总份额
                    total_shares = min(sell_config['total_shares'], position)
                else:
                    # 单次份额
                    total_shares = 0  # 稍后处理

                if sell_config['mode'] == 'single':
                    # 单次份额×随机
                    sell_plan = []
                    single = sell_config['single_shares']
                    remaining = position
                    for i in range(total_sells):
                        if i == total_sells - 1:
                            # 最后一次卖剩余
                            sell_plan.append(max(0, remaining))
                        else:
                            amt = int(single * random.uniform(1.01, 1.10))
                            # 保留足够给剩余轮次，每轮至少1份
                            min_for_remaining = total_sells - i - 1
                            amt = min(
                                amt, max(0, remaining - min_for_remaining))
                            if amt <= 0:
                                continue  # 跳过无效的卖出
                            sell_plan.append(amt)
                            remaining -= amt
                else:
                    # 总份额随机分配
                    sell_plan = []
                    remaining = total_shares
                    avg = total_shares // total_sells if total_sells > 0 else 0

                    for i in range(total_sells):
                        if i == total_sells - 1:
                            sell_plan.append(remaining)
                        else:
                            min_sell = max(1, int(avg * 0.8))
                            max_sell = min(
                                remaining - (total_sells - i - 1), int(avg * 1.2))
                            if max_sell <= min_sell:
                                amt = min_sell
                            else:
                                amt = random.randint(min_sell, max_sell)
                            sell_plan.append(amt)
                            remaining -= amt

                account_sell_plans[acc_idx] = sell_plan
                plan_str = ' + '.join([str(s) for s in sell_plan])
                print(
                    f"  [{config.remark}] 卖出计划: {plan_str} = {sum(sell_plan)}份")

        # 执行计划索引
        buy_idx = 0
        sell_idx = {acc_idx: 0 for acc_idx in selected_indices}

        for step_idx, group in enumerate(groups, 1):
            op_type = group['type']
            count = group['count']

            op_name = "买入" if op_type == 'buy' else "卖出"

            print(f"\n--- 第{step_idx}步: {op_name} x{count} ---")

            if op_type == 'buy':
                # 获取本步骤的买入金额
                step_amounts = buy_amounts[buy_idx:buy_idx + count]
                buy_idx += count

                # 确定价格
                if buy_config['price_mode'] == 'fixed':
                    prices = [buy_config['price']] * count
                elif buy_config['price_mode'] == 'range':
                    prices = [random.uniform(
                        buy_config['price_min'], buy_config['price_max']) for _ in range(count)]
                else:
                    prices = [None] * count  # 使用市价

                # 串行执行所有账户
                for j, acc_idx in enumerate(selected_indices):
                    config = self.configs[acc_idx - 1]
                    client = self.clients[acc_idx - 1]
                    for i, (amt, price) in enumerate(zip(step_amounts, prices)):
                        self._execute_buy_v2(
                            client, config, market_id, token_id, amt, price, i + 1)
                    # 账户之间短暂延迟
                    if j < len(selected_indices) - 1:
                        time.sleep(random.uniform(1, 2))

            else:  # 卖出
                # 确定价格
                if sell_config['price_mode'] == 'fixed':
                    prices = [sell_config['price']] * count
                elif sell_config['price_mode'] == 'range':
                    prices = [random.uniform(
                        sell_config['price_min'], sell_config['price_max']) for _ in range(count)]
                else:
                    prices = [None] * count  # 使用市价

                # 串行执行所有账户
                for j, acc_idx in enumerate(selected_indices):
                    config = self.configs[acc_idx - 1]
                    client = self.clients[acc_idx - 1]
                    plan = account_sell_plans.get(acc_idx, [])

                    for i in range(count):
                        idx = sell_idx[acc_idx]
                        shares = plan[idx] if idx < len(plan) else 0
                        sell_idx[acc_idx] += 1
                        price = prices[i]

                        self._execute_sell_v2(
                            client, config, market_id, token_id, shares, price, i + 1)
                    # 账户之间短暂延迟
                    if j < len(selected_indices) - 1:
                        time.sleep(random.uniform(1, 2))

            # 步骤之间等待
            if step_idx < len(groups):
                print(f"\n等待2秒后执行下一步...")
                time.sleep(2)

        print(f"\n{'='*60}")
        print(f"{'自定义策略执行完成':^60}")
        print(f"{'='*60}")

    def _execute_buy_v2(self, client, config, market_id, token_id, amount, price, op_num):
        """执行买入V2"""
        try:
            if price is None:
                # 获取卖1价
                ob = OrderbookService.fetch(client, token_id)
                if ob['success'] and ob['ask1_price'] > 0:
                    price = ob['ask1_price']
                else:
                    print(f"[{config.remark}] ✗ 买入#{op_num}: 无卖单")
                    return

            price_str = f"{price:.6f}"
            price_display = self.format_price(price) + '¢'

            order = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=price_str,
                makerAmountInQuoteToken=round(amount, 2)
            )

            result = client.place_order(order, check_approval=True)

            if result.errno == 0:
                print(
                    f"[{config.remark}] ✓ 买入#{op_num}: ${amount:.2f} @ {price_display}")
            elif result.errno == 10403:
                print(f"[{config.remark}] ✗ 买入#{op_num}: 地区限制")
            else:
                print(
                    f"[{config.remark}] ✗ 买入#{op_num}: {self.translate_error(result.errmsg)}")
        except Exception as e:
            print(f"[{config.remark}] ✗ 买入#{op_num}: {self.translate_error(str(e))}")

    def _execute_sell_v2(self, client, config, market_id, token_id, shares, price, op_num):
        """执行卖出V2"""
        try:
            if shares <= 0:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 份额为0，跳过")
                return

            if price is None:
                # 获取买1价
                ob = OrderbookService.fetch(client, token_id)
                if ob['success'] and ob['bid1_price'] > 0:
                    price = ob['bid1_price']
                else:
                    print(f"[{config.remark}] ✗ 卖出#{op_num}: 无买单")
                    return

            price_str = f"{price:.6f}"
            price_display = self.format_price(price) + '¢'

            order = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=price_str,
                makerAmountInBaseToken=int(shares)
            )

            result = client.place_order(order, check_approval=True)

            if result.errno == 0:
                print(
                    f"[{config.remark}] ✓ 卖出#{op_num}: {shares}份 @ {price_display}")
            elif result.errno == 10403:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 地区限制")
            else:
                error_msg = self.translate_error(result.errmsg)
                print(f"[{config.remark}] ✗ 卖出#{op_num}: {error_msg}")
                if error_msg == "余额不足":
                    print(f"[{config.remark}]    [*] 提示: 可能有挂单锁定了部分份额，建议先撤销挂单")
        except Exception as e:
            print(f"[{config.remark}] ✗ 卖出#{op_num}: {self.translate_error(str(e))}")

    def _execute_single_buy(self, client, config, market_id, token_id, amount, op_num):
        """执行单次买入"""
        try:
            # 获取盘口
            ob = OrderbookService.fetch(client, token_id)
            if not ob['success'] or ob['ask1_price'] <= 0:
                print(f"[{config.remark}] ✗ 买入#{op_num}: 无卖单")
                return

            price = ob['ask1_price']
            price_str = f"{price:.6f}"
            price_display = self.format_price(price) + '¢'

            order = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=price_str,
                makerAmountInQuoteToken=round(amount, 2)
            )

            result = client.place_order(order, check_approval=True)

            if result.errno == 0:
                print(
                    f"[{config.remark}] ✓ 买入#{op_num}: ${amount:.2f} @ {price_display}")
            elif result.errno == 10403:
                print(f"[{config.remark}] ✗ 买入#{op_num}: 地区限制")
            else:
                print(
                    f"[{config.remark}] ✗ 买入#{op_num}: {self.translate_error(result.errmsg)}")
        except Exception as e:
            print(f"[{config.remark}] ✗ 买入#{op_num}: {self.translate_error(str(e))}")

    def _execute_single_sell(self, client, config, market_id, token_id, amount, op_num):
        """执行单次卖出"""
        try:
            # 获取持仓
            available_shares = PositionService.get_token_balance(
                client, token_id)
            if available_shares <= 0:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 无持仓")
                return

            # 获取盘口
            ob = OrderbookService.fetch(client, token_id)
            if not ob['success'] or ob['bid1_price'] <= 0:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 无买单")
                return

            price = ob['bid1_price']
            price_str = f"{price:.6f}"
            price_display = self.format_price(price) + '¢'

            # 计算卖出数量
            if amount == 'x':
                sell_shares = available_shares
            else:
                # 按金额计算数量
                sell_shares = min(int(amount / price), available_shares)

            if sell_shares <= 0:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 数量为0")
                return

            order = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=price_str,
                makerAmountInBaseToken=sell_shares
            )

            result = client.place_order(order, check_approval=True)

            if result.errno == 0:
                print(
                    f"[{config.remark}] ✓ 卖出#{op_num}: {sell_shares}份 @ {price_display}")
            elif result.errno == 10403:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 地区限制")
            else:
                error_msg = self.translate_error(result.errmsg)
                print(f"[{config.remark}] ✗ 卖出#{op_num}: {error_msg}")
                if error_msg == "余额不足":
                    print(f"[{config.remark}]    [*] 提示: 可能有挂单锁定了部分份额，建议先撤销挂单")
        except Exception as e:
            print(f"[{config.remark}] ✗ 卖出#{op_num}: {self.translate_error(str(e))}")

    def _execute_single_sell_shares(self, client, config, market_id, token_id, sell_shares, is_x_mode, op_num):
        """执行单次卖出（按份额）"""
        try:
            if sell_shares <= 0:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 份额为0，跳过")
                return

            # 获取盘口
            ob = OrderbookService.fetch(client, token_id)

            if ob['success']:
                if ob['bid1_price'] > 0:
                    price = ob['bid1_price']
                    price_str = f"{price:.6f}"
                    price_display = self.format_price(price) + '¢'

                    order = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.SELL,
                        orderType=LIMIT_ORDER,
                        price=price_str,
                        makerAmountInBaseToken=int(sell_shares)
                    )

                    result = client.place_order(order, check_approval=True)

                    if result.errno == 0:
                        print(
                            f"[{config.remark}] ✓ 卖出#{op_num}: {sell_shares}份 @ {price_display}")
                    elif result.errno == 10403:
                        print(f"[{config.remark}] ✗ 卖出#{op_num}: 地区限制")
                    else:
                        error_msg = self.translate_error(result.errmsg)
                        print(f"[{config.remark}] ✗ 卖出#{op_num}: {error_msg}")
                        # 如果是余额不足，提示可能有挂单
                        if error_msg == "余额不足":
                            print(
                                f"[{config.remark}]    [*] 提示: 可能有挂单锁定了部分份额，建议先撤销挂单")
                else:
                    print(f"[{config.remark}] ✗ 卖出#{op_num}: 无买单")
            else:
                print(f"[{config.remark}] ✗ 卖出#{op_num}: 获取盘口失败")
        except Exception as e:
            print(f"[{config.remark}] ✗ 卖出#{op_num}: {self.translate_error(str(e))}")

    def merge_split_menu(self):
        """合并/拆分菜单"""
        print(f"\n{'='*60}")
        print(f"{'合并/拆分':^60}")
        print(f"{'='*60}")
        print("说明:")
        print("  合并(Merge): YES + NO → USDT")
        print("  拆分(Split): USDT → YES + NO")
        print(f"{'─'*60}")
        print("  1. 拆分 (USDT → YES + NO)")
        print("  2. 合并 (YES + NO → USDT)")
        print("  0. 返回主菜单")

        choice = input("\n请选择 (0-2): ").strip()

        if choice == '0' or not choice:
            return
        elif choice == '1':
            self.split_menu()
        elif choice == '2':
            self.merge_menu()
        else:
            print("✗ 无效选择")

    def split_menu(self):
        """拆分操作菜单"""
        print(f"\n{'='*60}")
        print(f"{'拆分 (USDT → YES + NO)':^60}")
        print(f"{'='*60}")

        # 1. 选择账户（支持多选，默认全部）
        print("\n请选择账户:")
        for idx, config in enumerate(self.configs, 1):
            print(f"  {idx}. {config.remark}")
        print("  0. 返回")

        account_choice = input(f"\n请选择账户 (留空=全部, 支持多选如 1 3 5 或 1-5): ").strip()
        if account_choice == '0':
            return

        # 解析账户选择
        selected_indices = self.parse_account_selection(
            account_choice, len(self.configs))
        if not selected_indices:
            print("✗ 未选择任何账户")
            return

        print(f"\n✓ 已选择 {len(selected_indices)} 个账户")

        # 2. 输入市场ID（使用新的提示方法）
        market_id = self.prompt_market_id("请输入市场ID")
        if market_id == 0:
            return

        # 3. 获取市场信息（使用第一个账户）
        client = self.clients[selected_indices[0] - 1]
        try:
            market_response = client.get_market(market_id=market_id)
            if market_response.errno != 0 or not market_response.result or not market_response.result.data:
                print(f"✗ 市场 {market_id} 不存在")
                return

            market_data = market_response.result.data
            print(f"\n✓ 市场: {market_data.market_title}")
            print(f"  YES Token: {market_data.yes_token_id}")
            print(f"  NO Token: {market_data.no_token_id}")

        except Exception as e:
            print(f"✗ 获取市场信息失败: {e}")
            return

        # 4. 输入拆分金额
        while True:
            amount_input = input("\n请输入每个账户的拆分金额 ($，留空返回): ").strip()
            if not amount_input:
                return
            try:
                split_amount = float(amount_input)
                if split_amount <= 0:
                    print("✗ 金额必须大于0")
                    continue
                break
            except ValueError:
                print("✗ 请输入有效的数字")

        # 5. 确认
        print(f"\n{'─'*40}")
        print(f"确认拆分:")
        print(f"  账户数: {len(selected_indices)} 个")
        print(f"  市场: {market_data.market_title}")
        print(f"  每账户金额: ${split_amount:.2f}")
        print(f"  总金额: ${split_amount * len(selected_indices):.2f}")
        print(f"  每账户将获得: {int(split_amount)} YES + {int(split_amount)} NO")
        print(f"{'─'*40}")

        confirm = input("确认请输入 'yes': ").strip().lower()
        if confirm != 'yes':
            print("✗ 已取消")
            return

        # 6. 批量执行拆分
        success_count = 0
        fail_count = 0

        for idx in selected_indices:
            client = self.clients[idx - 1]
            config = self.configs[idx - 1]

            print(f"\n[{config.remark}] 正在执行拆分...")
            result = MergeSplitService.split(client, market_id, split_amount)

            if result['success']:
                print(f"  ✓ 拆分成功!")
                success_count += 1
            else:
                print(f"  ✗ 拆分失败: {result.get('error', '未知错误')}")
                fail_count += 1

        print(f"\n{'─'*40}")
        print(f"拆分完成: 成功 {success_count}, 失败 {fail_count}")
        print(f"{'─'*40}")

        # 7. 拆分完成后询问是否卖出
        if success_count > 0:
            shares = int(split_amount)

            print(f"\n请选择要卖出的方向:")
            print(f"  1. 卖出 YES")
            print(f"  2. 卖出 NO")
            print(f"  3. 不卖出")

            sell_side_choice = input("请选择 (1-3): ").strip()

            if sell_side_choice == '1':
                token_id = market_data.yes_token_id
                token_name = "YES"
            elif sell_side_choice == '2':
                token_id = market_data.no_token_id
                token_name = "NO"
            else:
                print("✓ 拆分完成，未执行卖出")
                return

            # 获取订单簿（使用第一个账户）
            client = self.clients[selected_indices[0] - 1]
            ob = OrderbookService.fetch(client, token_id)
            if not ob['success']:
                print(f"✗ 获取订单簿失败，无法卖出")
                return

            bid1_price = ob['bid1_price']
            ask1_price = ob['ask1_price']

            # 使用交互助手获取卖出选项
            action, sell_price = OrderInputHelper.prompt_sell_after_split(
                bid1_price, ask1_price, self.format_price
            )

            if action == 'skip' or sell_price is None:
                print("✓ 拆分完成，未执行卖出")
                return

            # 批量执行卖出
            print(
                f"\n正在以 {self.format_price(sell_price)}¢ 卖出 {shares} {token_name}...")

            sell_success = 0
            sell_fail = 0

            for idx in selected_indices:
                client = self.clients[idx - 1]
                config = self.configs[idx - 1]

                order_service = EnhancedOrderService(
                    client, config, self.format_price)
                sell_result = order_service.submit_sell_order(
                    market_id=market_id,
                    token_id=token_id,
                    price=sell_price,
                    shares=shares,
                    skip_balance_check=True
                )

                if sell_result['success']:
                    print(
                        f"  [{config.remark}] ✓ 卖出成功! 金额: ${sell_result['amount']:.2f}")
                    sell_success += 1
                else:
                    print(
                        f"  [{config.remark}] ✗ 卖出失败: {sell_result.get('error', '未知错误')}")
                    sell_fail += 1

            print(f"\n卖出完成: 成功 {sell_success}, 失败 {sell_fail}")

    def merge_menu(self):
        """合并操作菜单"""
        print(f"\n{'='*60}")
        print(f"{'合并 (YES + NO → USDT)':^60}")
        print(f"{'='*60}")

        # 1. 选择账户
        print("\n请选择账户:")
        for idx, config in enumerate(self.configs, 1):
            print(f"  {idx}. {config.remark}")
        print("  0. 返回")

        account_choice = input(f"\n请选择账户 (1-{len(self.configs)}): ").strip()
        if account_choice == '0' or not account_choice:
            return

        try:
            account_idx = int(account_choice)
            if account_idx < 1 or account_idx > len(self.clients):
                print("✗ 无效的账户选择")
                return
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        client = self.clients[account_idx - 1]
        config = self.configs[account_idx - 1]
        print(f"\n✓ 已选择: {config.remark}")

        # 2. 输入市场ID
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 3. 获取市场信息和持仓
        try:
            market_response = client.get_market(market_id=market_id)
            if market_response.errno != 0 or not market_response.result or not market_response.result.data:
                print(f"✗ 市场 {market_id} 不存在")
                return

            market_data = market_response.result.data
            print(f"\n✓ 市场: {market_data.market_title}")

            # 查询YES和NO的持仓
            positions_response = client.get_my_positions()
            yes_shares = 0
            no_shares = 0

            if positions_response.errno == 0:
                positions = positions_response.result.list if hasattr(
                    positions_response.result, 'list') else []
                for pos in positions:
                    if str(pos.token_id) == str(market_data.yes_token_id):
                        yes_shares = int(float(pos.shares_owned)) if hasattr(
                            pos, 'shares_owned') else 0
                    elif str(pos.token_id) == str(market_data.no_token_id):
                        no_shares = int(float(pos.shares_owned)) if hasattr(
                            pos, 'shares_owned') else 0

            print(f"  YES 持仓: {yes_shares}")
            print(f"  NO 持仓: {no_shares}")

            # 可合并数量 = min(YES, NO)
            max_merge = min(yes_shares, no_shares)
            if max_merge <= 0:
                print(f"\n✗ 无法合并: 需要同时持有 YES 和 NO")
                return

            print(f"  可合并: {max_merge} 份 (将获得 ${max_merge:.2f} USDT)")

        except Exception as e:
            print(f"✗ 获取信息失败: {e}")
            return

        # 4. 输入合并数量
        while True:
            shares_input = input(f"\n请输入合并数量 (最多{max_merge}，留空=全部): ").strip()
            if not shares_input:
                merge_shares = max_merge
                break
            try:
                merge_shares = int(shares_input)
                if merge_shares <= 0:
                    print("✗ 数量必须大于0")
                    continue
                if merge_shares > max_merge:
                    print(f"✗ 超过可合并数量 ({max_merge})")
                    continue
                break
            except ValueError:
                print("✗ 请输入有效的整数")

        # 5. 确认
        print(f"\n{'─'*40}")
        print(f"确认合并:")
        print(f"  账户: {config.remark}")
        print(f"  市场: {market_data.market_title}")
        print(f"  合并数量: {merge_shares} 份")
        print(f"  将获得: ${merge_shares:.2f} USDT")
        print(f"{'─'*40}")

        confirm = input("确认请输入 'yes': ").strip().lower()
        if confirm != 'yes':
            print("✗ 已取消")
            return

        # 6. 执行合并
        print(f"\n正在执行合并...")
        result = MergeSplitService.merge(client, market_id, merge_shares)

        if result['success']:
            print(f"✓ 合并成功! 获得 ${merge_shares:.2f} USDT")
            if result.get('tx_hash'):
                print(f"  交易哈希: {result['tx_hash'][:20]}...")
        else:
            print(f"✗ 合并失败: {result.get('error', '未知错误')}")

    def enhanced_trading_menu(self, selected_account_indices: list):
        """增强买卖菜单

        支持：
        - 按金额下单
        - 按仓位下单（1/4、1/3、1/2、全仓）
        - 交易汇总统计
        - 使用 OrderbookManager 管理订单簿
        """
        print(f"\n{'='*60}")
        print(f"{'增强买卖模式':^60}")
        print(f"{'='*60}")
        print("说明:")
        print("  - 支持按金额/仓位下单")
        print("  - 卖出时跳过余额检查")
        print("  - 自动输出交易汇总统计")
        print(f"{'─'*60}")

        # 1. 输入市场ID
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 2. 获取市场信息
        client = self.clients[0]

        try:
            print(f"\n正在获取市场 {market_id} 的信息...")

            # 先尝试分类市场
            categorical_response = client.get_categorical_market(
                market_id=market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                market_data = categorical_response.result.data
                if hasattr(market_data, 'child_markets') and market_data.child_markets and len(market_data.child_markets) > 0:
                    child_markets = market_data.child_markets
                    print(f"\n✓ 找到分类市场: {market_data.market_title}")
                    print(f"\n子市场列表:")
                    for idx, child in enumerate(child_markets, 1):
                        print(f"  {idx}. {child.market_title}")
                    print("  0. 返回")

                    choice_input = input(
                        f"\n请选择子市场 (0-{len(child_markets)}): ").strip()
                    if not choice_input or choice_input == '0':
                        return

                    try:
                        choice = int(choice_input)
                        if choice < 1 or choice > len(child_markets):
                            print("✗ 无效选择")
                            return
                    except ValueError:
                        print("✗ 请输入有效的数字")
                        return

                    selected_child = child_markets[choice - 1]
                    market_id = selected_child.market_id
                    detail_response = client.get_market(market_id=market_id)
                    if detail_response.errno != 0:
                        print(f"✗ 获取子市场信息失败")
                        return
                    market_data = detail_response.result.data
                else:
                    print(f"\n✓ 市场: {market_data.market_title}")
            else:
                market_response = client.get_market(market_id=market_id)
                if market_response.errno != 0 or not market_response.result or not market_response.result.data:
                    print(f"✗ 市场 {market_id} 不存在")
                    return
                market_data = market_response.result.data
                print(f"\n✓ 市场: {market_data.market_title}")

        except Exception as e:
            print(f"✗ 获取市场信息失败: {e}")
            return

        # 3. 选择交易方向
        print(f"\n选择交易方向:")
        print("  1. YES")
        print("  2. NO")
        print("  0. 返回")

        side_choice = input("请选择 (0-2): ").strip()
        if side_choice == '0' or not side_choice:
            return
        elif side_choice == '1':
            token_id = market_data.yes_token_id
            token_name = "YES"
        elif side_choice == '2':
            token_id = market_data.no_token_id
            token_name = "NO"
        else:
            print("✗ 无效选择")
            return

        print(f"\n✓ 已选择: {token_name} (Token: {token_id})")

        # 4. 初始化订单簿管理器（主动查询 + WS 兜底）
        print(f"\n正在初始化订单簿...")
        ob_manager = OrderbookManager(client, token_id, ws_timeout=10)
        if not ob_manager.start():
            print("✗ 订单簿初始化失败")
            return

        # 5. 显示当前盘口
        ob_state = ob_manager.get_state()
        print(f"\n当前盘口:")
        print(
            f"  买1: {self.format_price(ob_state.bid1_price)}¢ x {ob_state.bid1_size:.0f}")
        print(
            f"  卖1: {self.format_price(ob_state.ask1_price)}¢ x {ob_state.ask1_size:.0f}")
        print(f"  价差: {ob_state.spread * 100:.2f}¢")

        # 6. 增强买卖循环
        summary = TradeSummary()  # 交易汇总

        while True:
            print(f"\n{'─'*40}")
            print("操作选择:")
            print("  1. 买入")
            print("  2. 卖出")
            print("  3. 刷新盘口")
            print("  4. 查看交易汇总")
            print("  0. 结束并返回")

            action_choice = input("请选择 (0-4): ").strip()

            if action_choice == '0':
                break
            elif action_choice == '3':
                # 刷新盘口
                ob_manager.refresh()
                ob_state = ob_manager.get_state()
                print(f"\n盘口已刷新:")
                print(
                    f"  买1: {self.format_price(ob_state.bid1_price)}¢ x {ob_state.bid1_size:.0f}")
                print(
                    f"  卖1: {self.format_price(ob_state.ask1_price)}¢ x {ob_state.ask1_size:.0f}")
                continue
            elif action_choice == '4':
                summary.print_summary("当前交易汇总")
                continue
            elif action_choice not in ['1', '2']:
                print("✗ 无效选择")
                continue

            is_buy = (action_choice == '1')
            action_name = "买入" if is_buy else "卖出"

            # 选择下单方式
            order_method = OrderInputHelper.prompt_order_method()
            if not order_method:
                continue

            # 获取最新盘口
            ob_manager.refresh()
            ob_state = ob_manager.get_state()

            # 确定价格
            if is_buy:
                # 买入用卖1价
                price = ob_state.ask1_price
                if price <= 0:
                    print("✗ 卖盘为空，无法买入")
                    continue
                print(f"\n将以卖1价 {self.format_price(price)}¢ 买入")
            else:
                # 卖出用买1价
                price = ob_state.bid1_price
                if price <= 0:
                    print("✗ 买盘为空，无法卖出")
                    continue
                print(f"\n将以买1价 {self.format_price(price)}¢ 卖出")

            # 计算下单参数
            order_amount = None
            order_shares = None

            if order_method == 'amount':
                order_amount = OrderInputHelper.prompt_amount()
                if order_amount is None:
                    continue
                order_shares = OrderCalculator.calculate_shares_by_amount(
                    order_amount, price)
                print(f"  金额: ${order_amount:.2f} → 约 {order_shares} 份")

            elif order_method == 'position':
                # 需要查询余额
                if is_buy:
                    balance = self.get_usdt_balance(
                        self.configs[selected_account_indices[0] - 1])
                    print(f"  当前余额: ${balance:.2f}")
                else:
                    # 查询持仓
                    balance = 0
                    try:
                        pos_resp = client.get_my_positions()
                        if pos_resp.errno == 0:
                            for pos in pos_resp.result.list:
                                if str(pos.token_id) == str(token_id):
                                    balance = int(float(pos.shares_owned))
                                    break
                    except:
                        pass
                    print(f"  当前持仓: {balance} 份")

                ratio = OrderInputHelper.prompt_position_ratio()
                if ratio is None:
                    continue

                if is_buy:
                    order_amount = balance * ratio
                    order_shares = OrderCalculator.calculate_shares_by_amount(
                        order_amount, price)
                    print(
                        f"  {ratio*100:.0f}% 仓位 = ${order_amount:.2f} → 约 {order_shares} 份")
                else:
                    order_shares = int(balance * ratio)
                    order_amount = OrderCalculator.calculate_amount_by_shares(
                        order_shares, price)
                    print(
                        f"  {ratio*100:.0f}% 仓位 = {order_shares} 份 → 约 ${order_amount:.2f}")

            elif order_method == 'shares':
                order_shares = OrderInputHelper.prompt_shares()
                if order_shares is None:
                    continue
                order_amount = OrderCalculator.calculate_amount_by_shares(
                    order_shares, price)
                print(f"  {order_shares} 份 → 约 ${order_amount:.2f}")

            if order_shares <= 0:
                print("✗ 计算份额为0，无法下单")
                continue

            # 确认
            print(f"\n确认{action_name}:")
            print(f"  价格: {self.format_price(price)}¢")
            print(f"  数量: {order_shares} 份")
            print(f"  金额: ${order_amount:.2f}")

            confirm = input("确认请输入 'y': ").strip().lower()
            if confirm != 'y':
                print("✗ 已取消")
                continue

            # 执行下单
            print(f"\n正在执行{action_name}...")

            for acc_idx in selected_account_indices:
                acc_client = self.clients[acc_idx - 1]
                acc_config = self.configs[acc_idx - 1]

                order_service = EnhancedOrderService(
                    acc_client, acc_config, self.format_price)

                if is_buy:
                    result = order_service.submit_buy_order(
                        market_id=market_id,
                        token_id=token_id,
                        price=price,
                        amount=order_amount
                    )
                else:
                    result = order_service.submit_sell_order(
                        market_id=market_id,
                        token_id=token_id,
                        price=price,
                        shares=order_shares,
                        skip_balance_check=True  # 卖出跳过余额检查
                    )

                if result['success']:
                    print(
                        f"  [{acc_config.remark}] ✓ {action_name}成功: {result['shares']}份 @ {self.format_price(price)}¢ = ${result['amount']:.2f}")

                    # 记录到汇总
                    trade = TradeRecord(
                        timestamp=time.time(),
                        side='buy' if is_buy else 'sell',
                        price=price,
                        shares=result['shares'],
                        amount=result['amount'],
                        account_remark=acc_config.remark
                    )
                    summary.add_trade(trade)
                else:
                    print(
                        f"  [{acc_config.remark}] ✗ {action_name}失败: {result.get('error', '未知错误')}")

        # 停止订单簿管理器
        ob_manager.stop()

        # 显示最终汇总
        if summary.total_trades > 0:
            summary.print_summary("本轮交易汇总")

        print("\n✓ 增强买卖模式结束")

    def trading_menu(self):
        """交易菜单"""
        # 1. 先选择交易模式
        print(f"\n{'='*60}")
        print(f"{'交易模式选择':^60}")
        print(f"{'='*60}")
        print("  1. 仅买入")
        print("  2. 仅卖出")
        print("  3. 先买后卖")
        print("  4. 先卖后买")
        print("  5. 自定义策略")
        print("  6. 快速模式（买卖交替）")
        print("  7. 低损耗模式（先买后挂单）")
        print("  8. 挂单模式（自定义价格）")
        print("  9. 做市商模式（双边挂单+分层）")
        print("  10. 增强买卖（按金额/仓位+交易汇总）")
        print("  0. 返回主菜单")

        mode_choice = input("\n请选择交易模式 (0-10): ").strip()

        if mode_choice == '0':
            return
        elif mode_choice not in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']:
            print("✗ 无效选择")
            return

        # 映射模式
        mode_map = {
            '1': 'buy_only',
            '2': 'sell_only',
            '3': 'buy_then_sell',
            '4': 'sell_then_buy',
            '5': 'custom',
            '6': 'quick_mode',
            '7': 'low_loss_mode',
            '8': 'limit_order_mode',
            '9': 'market_maker_mode',
            '10': 'enhanced_mode'
        }

        trade_mode = mode_map[mode_choice]

        # 显示选择的模式
        mode_names = {
            'buy_only': '仅买入',
            'sell_only': '仅卖出',
            'buy_then_sell': '先买后卖',
            'sell_then_buy': '先卖后买',
            'custom': '自定义策略',
            'quick_mode': '快速模式',
            'low_loss_mode': '低损耗模式',
            'limit_order_mode': '挂单模式',
            'market_maker_mode': '做市商模式',
            'enhanced_mode': '增强买卖'
        }

        print(f"\n✓ 已选择: {mode_names[trade_mode]}")

        # 仅卖出模式：询问是卖出指定市场还是卖出所有持仓
        if trade_mode == 'sell_only':
            print(f"\n{'─'*40}")
            print("卖出范围选择:")
            print("  1. 卖出指定市场持仓")
            print("  2. 卖出所有持仓（一键清仓）")
            sell_scope = input("请选择 (1/2): ").strip()

            if sell_scope == '2':
                # 卖出所有持仓
                self.sell_all_positions()
                return

            # 卖出指定市场：先选择市场，再查询持仓
            # 询问市场ID
            market_id_input = input("\n请输入市场ID (留空返回): ").strip()
            if not market_id_input:
                return

            try:
                sell_market_id = int(market_id_input)
            except ValueError:
                print("✗ 请输入有效的数字")
                return

            # 获取市场信息
            client = self.clients[0]
            print(f"\n正在获取市场 {sell_market_id} 的信息...")

            # 先尝试作为分类市场获取
            categorical_response = client.get_categorical_market(
                market_id=sell_market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                # 这是一个分类市场
                market_data = categorical_response.result.data
                if not hasattr(market_data, 'market_title') or not market_data.market_title:
                    print(f"✗ 市场 {sell_market_id} 数据不完整")
                    return
                parent_market_title = market_data.market_title
                parent_market_id = market_data.market_id
                print(f"\n✓ 找到分类市场: {parent_market_title}")

                # 检查是否有子市场
                if hasattr(market_data, 'child_markets') and market_data.child_markets and len(market_data.child_markets) > 0:
                    child_markets = market_data.child_markets

                    print(f"\n找到 {len(child_markets)} 个子市场:")
                    for idx, child in enumerate(child_markets, 1):
                        title = child.market_title if hasattr(
                            child, 'market_title') else 'N/A'
                        child_id = child.market_id if hasattr(
                            child, 'market_id') else 'N/A'
                        print(f"  {idx}. [{child_id}] {title}")
                    print(f"  0. 返回")

                    choice_input = input(
                        f"\n请选择要卖出的子市场 (0-{len(child_markets)}): ").strip()
                    if not choice_input or choice_input == '0':
                        return

                    try:
                        choice = int(choice_input)
                    except ValueError:
                        print("✗ 请输入有效的数字")
                        return

                    if choice < 1 or choice > len(child_markets):
                        print("✗ 无效的选择")
                        return

                    selected_child = child_markets[choice - 1]
                    sell_market_id = selected_child.market_id
                    market_title = selected_child.market_title if hasattr(
                        selected_child, 'market_title') else f"市场{sell_market_id}"
                    print(f"\n✓ 已选择子市场: {market_title}")
                else:
                    # 分类市场但没有子市场，使用父市场标题
                    market_title = parent_market_title
            else:
                # 尝试作为普通市场获取
                detail_response = client.get_market(market_id=sell_market_id)
                if detail_response.errno != 0 or not detail_response.result or not detail_response.result.data:
                    error_msg = detail_response.errmsg if hasattr(
                        detail_response, 'errmsg') and detail_response.errmsg else '未知错误'
                    print(f"✗ 市场不存在或已下架，请检查市场ID ({error_msg})")
                    return
                market_data = detail_response.result.data
                market_title = market_data.market_title if hasattr(
                    market_data, 'market_title') else f"市场{sell_market_id}"
                print(f"\n✓ 找到市场: {market_title}")

            # 查询该市场所有账户的持仓（实时显示）
            print(f"\n{'='*60}")
            print(f"{'查询市场持仓':^60}")
            print(f"{'='*60}")

            accounts_with_positions = []  # 有持仓的账户

            for idx, (client, config) in enumerate(zip(self.clients, self.configs), 1):
                remark = config.remark if hasattr(
                    config, 'remark') else f"账户{idx}"
                try:
                    positions = self.get_all_positions(
                        client, market_id=sell_market_id)
                    for position in positions:
                        shares = int(float(position.shares_owned if hasattr(
                            position, 'shares_owned') else 0))
                        if shares > 0:
                            side = position.outcome_side_enum if hasattr(
                                position, 'outcome_side_enum') else 'N/A'
                            token_id = position.token_id if hasattr(
                                position, 'token_id') else None

                            # 同时查询挂单占用，避免后续重复查询
                            pending_amount = 0
                            try:
                                orders = self.get_all_orders(client)
                                for order in orders:
                                    order_market_id = order.market_id if hasattr(
                                        order, 'market_id') else None
                                    order_outcome_side = order.outcome_side if hasattr(
                                        order, 'outcome_side') else None
                                    order_side = order.side if hasattr(
                                        order, 'side') else None
                                    order_status = order.status if hasattr(
                                        order, 'status') else None

                                    pos_outcome_side = 1 if side == 'Yes' else 2
                                    if (order_market_id == sell_market_id and
                                        order_outcome_side == pos_outcome_side and
                                            order_side == 2 and order_status == 1):
                                        order_shares = float(order.order_shares if hasattr(
                                            order, 'order_shares') else 0)
                                        filled_shares = float(order.filled_shares if hasattr(
                                            order, 'filled_shares') else 0)
                                        pending_amount += int(order_shares -
                                                              filled_shares)
                            except Exception:
                                pass

                            available = shares - pending_amount
                            if available <= 0:
                                continue

                            accounts_with_positions.append({
                                'idx': idx,
                                'config': config,
                                'client': client,
                                'shares': shares,
                                'side': side,
                                'token_id': token_id,
                                'available': available,
                                'pending': pending_amount
                            })
                            # 实时显示（包含可用份额）
                            if pending_amount > 0:
                                print(
                                    f"  账户ID:{idx}  备注:{remark}  持仓:{shares}份  可用:{available}份  方向:{side}  (挂单占用{pending_amount})")
                            else:
                                print(
                                    f"  账户ID:{idx}  备注:{remark}  持仓:{shares}份  方向:{side}")
                except Exception as e:
                    print(f"  账户ID:{idx}  备注:{remark}  [!] 查询失败: {e}")

            if not accounts_with_positions:
                print(f"\n✗ 没有账户在市场 {sell_market_id} 持有仓位")
                return

            print(f"\n✓ 找到 {len(accounts_with_positions)} 个账户有持仓")

            # 让用户选择账户
            print(f"\n  输入格式示例:")
            print(f"    留空 = 全部有持仓的账户")
            print(f"    2 9 10 = 通过账户ID选择")
            print(f"    5-15 = 通过ID范围选择")

            account_input = input("\n请选择账户 (留空=全部有持仓账户): ").strip()

            if not account_input:
                # 默认选择所有有持仓的账户
                selected_account_indices = [pos['idx']
                                            for pos in accounts_with_positions]
            else:
                selected_account_indices = self.parse_account_selection(
                    account_input, len(self.clients))
                # 过滤只保留有持仓的账户
                position_indices = {pos['idx']
                                    for pos in accounts_with_positions}
                selected_account_indices = [
                    idx for idx in selected_account_indices if idx in position_indices]

            if not selected_account_indices:
                print("✗ 未选择任何有持仓的账户")
                return

            print(f"✓ 已选择 {len(selected_account_indices)} 个账户")

            # 直接跳转到卖出流程，传入市场标题和缓存的持仓信息（避免重复查询）
            self._execute_sell_for_market(
                sell_market_id,
                selected_account_indices,
                market_title=market_title,
                cached_positions=accounts_with_positions
            )
            return

        # 2. 先查询所有账户余额
        print(f"\n{'='*60}")
        print(f"{'查询账户余额':^60}")
        print(f"{'='*60}")
        all_indices = list(range(1, len(self.clients) + 1))  # 1-based 索引
        all_account_balances = self.display_account_balances(all_indices)

        # 3. 选择参与交易的账户
        print(f"\n  输入格式示例:")
        print(f"    留空 = 全部账户")
        print(f"    2 9 10 = 通过账户ID选择")
        print(f"    5-15 = 通过ID范围选择")

        account_input = input("\n请选择账户 (留空=全部): ").strip()
        selected_account_indices = self.parse_account_selection(
            account_input, len(self.clients))

        if not selected_account_indices:
            print("✗ 未选择任何有效账户")
            return

        print(f"✓ 已选择 {len(selected_account_indices)} 个账户")

        # 自定义策略模式：跳转到专门的菜单
        if trade_mode == 'custom':
            self.custom_strategy_menu()
            return

        # 挂单模式：跳转到专门的菜单
        if trade_mode == 'limit_order_mode':
            self.limit_order_menu(selected_account_indices)
            return

        # 做市商模式：跳转到专门的菜单
        if trade_mode == 'market_maker_mode':
            self.market_maker_menu(selected_account_indices)
            return

        # 增强买卖模式：跳转到专门的菜单
        if trade_mode == 'enhanced_mode':
            self.enhanced_trading_menu(selected_account_indices)
            return

        # 初始化变量
        selected_child_market = None  # 记录选中的子市场
        parent_market_title = None    # 记录父市场标题
        parent_market_id = None       # 记录父市场ID

        # 4. 询问市场ID
        market_id_input = input("\n请输入市场ID (留空返回): ").strip()
        if not market_id_input:
            return

        try:
            market_id = int(market_id_input)
        except ValueError:
            print("✗ 请输入有效的数字")
            return

        # 2. 获取市场信息
        client = self.clients[0]

        try:
            print(f"\n正在获取市场 {market_id} 的信息...")

            # 先尝试作为分类市场获取
            categorical_response = client.get_categorical_market(
                market_id=market_id)

            if categorical_response.errno == 0 and categorical_response.result and categorical_response.result.data:
                # 这是一个分类市场
                market_data = categorical_response.result.data
                if not hasattr(market_data, 'market_title') or not market_data.market_title:
                    print(f"✗ 市场 {market_id} 数据不完整")
                    return
                parent_market_title = market_data.market_title  # 保存父市场标题
                parent_market_id = market_data.market_id  # 保存父市场ID
                print(f"\n✓ 找到分类市场: {parent_market_title}")
                print(f"  市场ID: {parent_market_id}")

                # 检查是否有子市场
                if hasattr(market_data, 'child_markets') and market_data.child_markets and len(market_data.child_markets) > 0:
                    child_markets = market_data.child_markets

                    print(f"\n找到 {len(child_markets)} 个子市场:")
                    for idx, child in enumerate(child_markets, 1):
                        title = child.market_title if hasattr(
                            child, 'market_title') else 'N/A'
                        child_id = child.market_id if hasattr(
                            child, 'market_id') else 'N/A'
                        print(f"  {idx}. [{child_id}] {title}")
                    print(f"  0. 返回")

                    # 让用户选择子市场
                    choice_input = input(
                        f"\n请选择要交易的子市场 (0-{len(child_markets)}): ").strip()
                    if not choice_input or choice_input == '0':
                        return

                    try:
                        choice = int(choice_input)
                    except ValueError:
                        print("✗ 请输入有效的数字")
                        return

                    if choice < 1 or choice > len(child_markets):
                        print("✗ 无效的选择")
                        return

                    selected_child = child_markets[choice - 1]
                    selected_child_market = selected_child  # 保存到外层变量
                    market_id = selected_child.market_id

                    print(f"\n✓ 已选择子市场: {selected_child.market_title}")
                    print(f"  子市场ID: {market_id}")

                    # 现在获取子市场的详细信息
                    detail_response = client.get_market(market_id=market_id)
                    if detail_response.errno != 0 or not detail_response.result or not detail_response.result.data:
                        print(
                            f"✗ 获取子市场详细信息失败: {detail_response.errmsg if hasattr(detail_response, 'errmsg') else '未知错误'}")
                        return

                    market_data = detail_response.result.data
                else:
                    # 没有子市场，直接使用这个市场本身
                    print(f"  (无子市场，直接交易此市场)")
                    # market_data已经是正确的数据

            else:
                # 不是分类市场,尝试作为普通二元市场
                print(f"不是分类市场,尝试作为二元市场...")

                market_response = client.get_market(market_id=market_id)

                if market_response.errno != 0:
                    print(f"✗ 获取市场失败: {market_response.errmsg}")
                    print(f"  错误代码: {market_response.errno}")
                    return

                if not market_response.result or not market_response.result.data:
                    print(f"✗ 市场 {market_id} 不存在或数据为空")
                    return

                market_data = market_response.result.data

                if not hasattr(market_data, 'market_title') or not market_data.market_title:
                    print(f"✗ 市场 {market_id} 数据不完整")
                    return

                print(f"\n✓ 找到二元市场: {market_data.market_title}")
                print(f"  市场ID: {market_data.market_id}")

            # 显示市场详情
            print(f"\n市场详情:")
            print(f"  YES Token ID: {market_data.yes_token_id}")
            print(f"  NO Token ID: {market_data.no_token_id}")

        except Exception as e:
            print(f"✗ 获取市场信息失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 获取token的名称（用于显示）
        # 尝试从market_data获取token的ticker或symbol
        yes_token_name = "YES"
        no_token_name = "NO"

        if hasattr(market_data, 'tokens') and market_data.tokens:
            for token in market_data.tokens:
                if hasattr(token, 'token_id') and hasattr(token, 'ticker'):
                    if token.token_id == market_data.yes_token_id:
                        yes_token_name = token.ticker
                    elif token.token_id == market_data.no_token_id:
                        no_token_name = token.ticker

        # 3. 选择交易方向（二级菜单）
        print(f"\n请选择交易方向:")
        print(f"  1. {yes_token_name}")
        print(f"  2. {no_token_name}")
        print(f"  0. 返回")
        side_choice = input("请输入选项 (0-2): ").strip()

        if side_choice == '0' or not side_choice:
            return
        elif side_choice == '1':
            side_input = 'YES'
            token_id = market_data.yes_token_id
            selected_token_name = yes_token_name
        elif side_choice == '2':
            side_input = 'NO'
            token_id = market_data.no_token_id
            selected_token_name = no_token_name
        else:
            print("✗ 无效的选择")
            return

        # 第一次确认
        print(f"\n" + "="*60)
        print("【第一次确认】请确认交易信息:")
        if parent_market_title:
            print(f"  主市场: {parent_market_title}")
        if selected_child_market:
            print(f"  子市场: {selected_child_market.market_title}")
        else:
            print(f"  市场: {market_data.market_title}")

        # 显示交易模式
        if trade_mode == 'buy_only':
            print(f"  交易模式: 仅买入")
        elif trade_mode == 'sell_only':
            print(f"  交易模式: 仅卖出")
        elif trade_mode == 'buy_then_sell':
            print(f"  交易模式: 先买后卖")
        elif trade_mode == 'sell_then_buy':
            print(f"  交易模式: 先卖后买")
        elif trade_mode == 'quick_mode':
            print(f"  交易模式: 快速模式（买卖交替）")
        elif trade_mode == 'low_loss_mode':
            print(f"  交易模式: 低损耗模式（先买后挂单）")

        print(f"  交易方向: {selected_token_name}")
        print("="*60)

        confirm = input("\n确认无误请输入 'done': ").strip().lower()

        if confirm != 'done':
            print("✗ 已取消交易")
            return

        print(f"\n✓ 第一次确认通过")

        # 4. 快速模式和低损耗模式的独立处理
        if trade_mode in ['quick_mode', 'low_loss_mode']:
            # 询问交易次数
            while True:
                print(f"\n[*] 提示: 输入交易轮数，每轮包含买入1次+卖出1次=2笔交易")
                print(f"   例如: 输入1 → 买1次+卖1次=2笔")
                print(f"   例如: 输入2 → 买2次+卖2次=4笔")
                num_input = input(f"请输入交易轮数: ").strip()
                try:
                    total_trades = int(num_input)
                    if total_trades < 1:
                        print("✗ 次数必须大于0")
                        continue

                    print(
                        f"✓ 将执行: 买{total_trades}次 + 卖{total_trades}次 = {total_trades*2}笔交易")
                    break
                except Exception:
                    print("✗ 请输入有效数字")

            # 询问金额范围
            print(f"\n请设置单笔买入金额范围:")
            while True:
                min_input = input(f"单笔最低金额 ($): ").strip()
                try:
                    min_amount = float(min_input)
                    if min_amount < 1:
                        print("✗ 金额必须大于1")
                        continue
                    break
                except Exception:
                    print("✗ 请输入有效数字")

            while True:
                max_input = input(f"单笔最高金额 ($): ").strip()
                try:
                    max_amount = float(max_input)
                    if max_amount < min_amount:
                        print(f"✗ 最高金额必须 >= 最低金额({min_amount})")
                        continue
                    break
                except Exception:
                    print("✗ 请输入有效数字")

            # 确认信息
            # 计算预估总金额 - total_trades是交易轮数（每轮=1买+1卖）
            buy_times = total_trades
            total_min_est = min_amount * buy_times
            total_max_est = max_amount * buy_times

            # 使用之前查询的余额（不再重复查询）
            # 快速模式：买卖交替，卖出会回收资金，只需检查单笔买入金额是否足够
            account_balances = {idx: all_account_balances.get(
                idx, 0) for idx in selected_account_indices}

            # 收集余额不足的账户（只检查单笔最大金额）
            insufficient_accounts = []
            for acc_idx, balance in account_balances.items():
                if balance < max_amount:
                    config = self.configs[acc_idx - 1]
                    insufficient_accounts.append(
                        (acc_idx, config.remark, balance, max_amount))

            if insufficient_accounts:
                action, skip_remarks = handle_insufficient_balance(
                    insufficient_accounts)
                if action == 'cancel':
                    print("✗ 已取消")
                    return
                elif action == 'skip':
                    # 过滤掉余额不足的账户
                    original_count = len(selected_account_indices)
                    selected_account_indices = [
                        idx for idx in selected_account_indices if self.configs[idx - 1].remark not in skip_remarks]
                    account_balances = {idx: bal for idx, bal in account_balances.items(
                    ) if self.configs[idx - 1].remark not in skip_remarks}
                    print(
                        f"\n✓ 已跳过 {original_count - len(selected_account_indices)} 个余额不足账户，剩余 {len(selected_account_indices)} 个账户")
                    if not selected_account_indices:
                        print("✗ 没有剩余账户可执行交易")
                        return

            print(f"\n{'='*60}")
            print(f"{'【快速模式/低损耗模式确认】':^60}")
            print(
                f"  交易轮数: {total_trades}轮 (买{total_trades}次+卖{total_trades}次={total_trades*2}笔)")
            print(f"  单笔买入: ${min_amount:.2f} - ${max_amount:.2f}")
            print(f"  预估总购买: ${total_min_est:.2f} - ${total_max_est:.2f}")
            if trade_mode == 'quick_mode':
                print(f"  模式说明: 买卖交替，限价单快速成交")
                print(f"  买入价格: 卖1（立即成交）")
                print(f"  卖出价格: 买1（立即成交）")
            else:
                print(f"  模式说明: 先买后挂卖")
                print(f"  买入价格: 卖1（立即成交）")
                print(f"  卖出价格: 用户选择挂单价格")
            print(f"{'='*60}")

            confirm2 = input("\n确认无误请输入 'done': ").strip().lower()
            if confirm2 != 'done':
                print("✗ 已取消交易")
                return

            # 执行快速模式或低损耗模式
            if trade_mode == 'quick_mode':
                # 快速模式：多账户串行，先买后卖策略
                self.execute_quick_mode_multi(
                    market_id=market_id,
                    token_id=token_id,
                    selected_token_name=selected_token_name,
                    total_trades=total_trades,
                    min_amount=min_amount,
                    max_amount=max_amount,
                    selected_account_indices=selected_account_indices
                )
            else:  # low_loss_mode
                # 低损耗模式：多账户串行
                self.execute_low_loss_mode_multi(
                    market_id=market_id,
                    token_id=token_id,
                    selected_token_name=selected_token_name,
                    total_trades=total_trades,
                    min_amount=min_amount,
                    max_amount=max_amount,
                    selected_account_indices=selected_account_indices
                )

            return

        # 4. 检查账户余额或持仓（只检查选中的账户）
        # 计算账户编号所需的位数
        account_num_width = len(str(max(selected_account_indices)))

        if trade_mode == 'sell_only':
            # 仅卖出模式：使用SDK查询positions
            print(f"\n正在检查选中账户的持仓...")
            token_balances = {}  # 改用字典 {账户索引: 余额}

            for idx in selected_account_indices:
                client = self.clients[idx - 1]
                config = self.configs[idx - 1]
                try:
                    # 使用SDK查询positions
                    positions_response = client.get_my_positions()

                    if positions_response.errno == 0:
                        # 查找对应token的持仓 - 修复：使用result.list
                        total_shares = 0
                        locked_shares = 0
                        positions = positions_response.result.list if hasattr(
                            positions_response.result, 'list') else []

                        for position in positions:
                            # 检查token_id是否匹配
                            pos_token_id = str(position.token_id) if hasattr(
                                position, 'token_id') else None
                            if pos_token_id == str(token_id):
                                # 获取shares_owned（总持仓）
                                shares = position.shares_owned if hasattr(
                                    position, 'shares_owned') else 0
                                total_shares = int(float(shares))

                                # 获取市场信息
                                market_id_pos = position.market_id if hasattr(
                                    position, 'market_id') else 'N/A'
                                market_title = position.market_title if hasattr(
                                    position, 'market_title') else ''
                                outcome_side = position.outcome_side_enum if hasattr(
                                    position, 'outcome_side_enum') else selected_token_name

                                break

                        # 查询该token的所有挂单，计算未成交数量
                        pending_amount = 0
                        try:
                            orders_response = client.get_my_orders()
                            if orders_response.errno == 0:
                                orders = orders_response.result.list if hasattr(
                                    orders_response.result, 'list') else []
                                for order in orders:
                                    # 检查是否是当前市场、当前outcome的卖单
                                    order_market_id = order.market_id if hasattr(
                                        order, 'market_id') else None
                                    order_outcome_side = order.outcome_side if hasattr(
                                        order, 'outcome_side') else None
                                    order_side = order.side if hasattr(
                                        order, 'side') else None
                                    order_status = order.status if hasattr(
                                        order, 'status') else None

                                    # 匹配条件：同市场 + 同outcome + 卖单 + Pending状态
                                    if (order_market_id == market_id and
                                        order_outcome_side == (1 if selected_token_name == 'YES' else 2) and
                                        order_side == 2 and  # 2 = Sell
                                            order_status == 1):  # 1 = Pending

                                        # 计算未成交数量 = 订单总数量 - 已成交数量
                                        order_shares = float(order.order_shares if hasattr(
                                            order, 'order_shares') else 0)
                                        filled_shares = float(order.filled_shares if hasattr(
                                            order, 'filled_shares') else 0)
                                        pending_amount += int(order_shares -
                                                              filled_shares)
                        except Exception as e:
                            # 查询订单失败，使用locked_shares（如果有的话）
                            try:
                                locked = position.locked_shares if hasattr(
                                    position, 'locked_shares') else 0
                                pending_amount = int(float(locked))
                            except Exception:
                                pending_amount = 0

                        # 可用余额 = 总持仓 - 挂单未成交数量
                        available_balance = total_shares - pending_amount
                        token_balances[idx] = available_balance

                        if total_shares > 0:
                            # 格式化市场显示：父市场ID#子市场名称
                            if parent_market_id and selected_child_market:
                                # 如果是分类市场的子市场，显示父市场ID和子市场标题
                                child_title = selected_child_market.market_title if hasattr(
                                    selected_child_market, 'market_title') else str(market_id)
                                market_display = f"市场{parent_market_id}#{child_title}"
                            else:
                                # 普通二元市场，显示市场ID
                                market_display = f"市场#{market_id_pos}"

                            # 显示详细信息：优先显示可用余额
                            if pending_amount > 0:
                                print(
                                    f"{idx:0{account_num_width}d}. {config.remark} {market_display} {outcome_side}可用: {available_balance} tokens (总持仓{total_shares}, 挂单{pending_amount})")
                            else:
                                print(
                                    f"{idx:0{account_num_width}d}. {config.remark} {market_display} {outcome_side}可用: {available_balance} tokens")
                        else:
                            print(
                                f"{idx:0{account_num_width}d}. {config.remark} 无{selected_token_name}持仓")
                    else:
                        print(
                            f"{idx:0{account_num_width}d}. {config.remark} SDK查询失败: errno={positions_response.errno}")
                        token_balances[idx] = 0

                except Exception as e:
                    print(f"{idx:0{account_num_width}d}. {config.remark} 查询异常: {e}")
                    token_balances[idx] = 0

            total_tokens = sum(token_balances.values())
            print(f"\n✓ 总可用: {total_tokens} {selected_token_name} tokens")

            if total_tokens == 0:
                print("✗ 选中账户持仓均为0，无法卖出")
                return

        # 先卖后买模式：需要同时检查持仓和余额
        elif trade_mode == 'sell_then_buy':
            # 先检查持仓
            print(f"\n正在检查选中账户的持仓...")
            token_balances = {}  # 改用字典

            for idx in selected_account_indices:
                client = self.clients[idx - 1]
                config = self.configs[idx - 1]
                try:
                    positions_response = client.get_my_positions()

                    if positions_response.errno == 0:
                        total_shares = 0
                        positions = positions_response.result.list if hasattr(
                            positions_response.result, 'list') else []

                        for position in positions:
                            pos_token_id = str(position.token_id) if hasattr(
                                position, 'token_id') else None
                            if pos_token_id == str(token_id):
                                shares = position.shares_owned if hasattr(
                                    position, 'shares_owned') else 0
                                total_shares = int(float(shares))
                                break

                        token_balances[idx] = total_shares
                        if total_shares > 0:
                            print(
                                f"{idx:0{account_num_width}d}. {config.remark} 持仓: {total_shares} tokens")
                        else:
                            print(
                                f"{idx:0{account_num_width}d}. {config.remark} 无{selected_token_name}持仓")
                    else:
                        token_balances[idx] = 0
                        print(
                            f"{idx:0{account_num_width}d}. {config.remark} 查询失败")
                except Exception as e:
                    token_balances[idx] = 0
                    print(f"{idx:0{account_num_width}d}. {config.remark} 异常: {e}")

            total_tokens = sum(token_balances.values())
            print(f"\n✓ 总持仓: {total_tokens} {selected_token_name} tokens")

            if total_tokens == 0:
                print("✗ 选中账户持仓均为0，无法进行先卖后买操作")
                return

            # 使用之前查询的余额
            available_amounts = {idx: all_account_balances.get(
                idx, 0) for idx in selected_account_indices}

        else:
            # 买入或买入+卖出模式：使用之前查询的余额
            available_amounts = {idx: all_account_balances.get(
                idx, 0) for idx in selected_account_indices}

        # 5. 串行执行模式（已移除并发设置）
        selected_count = len(selected_account_indices)
        actual_concurrent = 1  # 固定为串行执行
        print(f"\n✓ 执行模式: 串行（每个账户使用独立代理）")

        # 6. 创建账户列表（串行执行）
        # 创建账户列表：[(账户索引, client, config), ...] - 只包含选中的账户
        all_accounts = [(idx, self.clients[idx - 1], self.configs[idx - 1])
                        for idx in selected_account_indices]

        print(f"  选中账户数: {len(all_accounts)}")

        # 7. 设置交易参数
        num_trades = 1  # 默认交易次数，后续会被用户输入覆盖
        min_amt = 0  # 默认最低金额
        max_amt = 0  # 默认最高金额

        if trade_mode == 'sell_only':
            # 仅卖出模式：只询问卖出次数，不问数量范围
            min_amt = 0
            max_amt = 0
        else:
            # 买入或买入+卖出模式：询问购买金额
            print("\n设置单笔购买金额:")

            while True:
                try:
                    min_amt = float(input("请输入单笔最低金额 ($): ").strip())
                    if min_amt <= 0:
                        print("✗ 金额必须大于0")
                        continue
                    break
                except ValueError:
                    print("✗ 请输入有效的数字")

            while True:
                try:
                    max_amt = float(input("请输入单笔最高金额 ($): ").strip())
                    if max_amt <= 0:
                        print("✗ 金额必须大于0")
                        continue
                    if max_amt < min_amt:
                        print(f"✗ 最高金额不能小于最低金额(${min_amt:.2f})")
                        continue
                    break
                except ValueError:
                    print("✗ 请输入有效的数字")

            print(f"\n✓ 单笔金额范围: ${min_amt:.2f} - ${max_amt:.2f}")

        # 检查余额并自动调整
        if trade_mode != 'sell_only':
            adjusted_accounts = []
            zero_balance_accounts = []

            for idx in selected_account_indices:
                balance = available_amounts.get(idx, 0)
                config = self.configs[idx - 1]
                if balance < min_amt:
                    if balance > 0:
                        adjusted_accounts.append(
                            (idx, config.remark, balance, min_amt))
                    else:
                        zero_balance_accounts.append((idx, config.remark))

            if adjusted_accounts:
                print(f"\n[!]  以下账户余额低于最低金额，将自动调整:")
                for idx, remark, balance, min_amt_needed in adjusted_accounts:
                    print(
                        f"  {remark}: ${balance:.2f} (原需最低 ${min_amt_needed:.2f}) → 调整为 ${balance:.2f}")
                print(f"\n✓ 这些账户将使用实际余额进行交易")

            if zero_balance_accounts:
                print(f"\n[!]  以下账户余额为0，将跳过:")
                for idx, remark in zero_balance_accounts:
                    print(f"  {remark}")

                if len(zero_balance_accounts) == len(selected_account_indices):
                    print(f"\n✗ 所有选中账户余额为0，无法交易")
                    return

        # 8. 输入交易次数（根据模式显示不同提示）
        if trade_mode == 'buy_only':
            print(f"\n[*] 提示: 仅买入模式，每次买入算1笔交易")
            trades_prompt = "请输入买入次数: "
        elif trade_mode == 'sell_only':
            print(f"\n[*] 提示: 仅卖出模式，每次卖出算1笔交易")
            trades_prompt = "请输入卖出次数: "
        else:  # buy_then_sell, sell_then_buy
            print(f"\n[*] 提示: 输入交易轮数，每轮包含买入1次+卖出1次=2笔交易")
            print(f"   例如: 输入1 → 买1次+卖1次=2笔")
            print(f"   例如: 输入2 → 买2次+卖2次=4笔")
            trades_prompt = "请输入交易轮数: "

        while True:
            try:
                num_trades_input = input(f"{trades_prompt}").strip()
                num_trades = int(num_trades_input)
                if num_trades <= 0:
                    print("✗ 交易次数必须大于0")
                    continue
                break
            except ValueError:
                print("✗ 请输入有效的整数")

        if trade_mode in ['buy_then_sell', 'sell_then_buy']:
            print(
                f"✓ 将执行: 买{num_trades}次 + 卖{num_trades}次 = {num_trades*2}笔交易")
        else:
            print(f"✓ 交易次数: {num_trades}笔")

        # 显示预估总金额（非卖出模式）
        if trade_mode != 'sell_only':
            # 使用选中账户的余额（字典方式）
            selected_balances = [available_amounts.get(
                idx, 0) for idx in selected_account_indices]
            active_accounts = len(
                [b for b in selected_balances if b >= min_amt])
            if active_accounts == 0:
                active_accounts = len([b for b in selected_balances if b > 0])

            total_min = min_amt * active_accounts * num_trades
            total_max = max_amt * active_accounts * num_trades
            print(
                f"  预估总购买金额: ${total_min:.2f} - ${total_max:.2f} ({active_accounts}个账户 × {num_trades}笔)")

            # 检查每个账户余额是否足够
            insufficient_accounts = []
            for idx in selected_account_indices:
                balance = available_amounts.get(idx, 0)
                required = max_amt * num_trades
                if balance < required:
                    config = self.configs[idx - 1]
                    insufficient_accounts.append(
                        (idx, config.remark, balance, required))

            if insufficient_accounts:
                action, skip_remarks = handle_insufficient_balance(
                    insufficient_accounts)
                if action == 'cancel':
                    print("✗ 已取消")
                    return
                elif action == 'skip':
                    # 过滤掉余额不足的账户
                    original_count = len(selected_account_indices)
                    selected_account_indices = [
                        idx for idx in selected_account_indices if self.configs[idx - 1].remark not in skip_remarks]
                    available_amounts = {idx: bal for idx, bal in available_amounts.items(
                    ) if self.configs[idx - 1].remark not in skip_remarks}
                    print(
                        f"\n✓ 已跳过 {original_count - len(selected_account_indices)} 个余额不足账户，剩余 {len(selected_account_indices)} 个账户")
                    if not selected_account_indices:
                        print("✗ 没有剩余账户可执行交易")
                        return

        # 10. 大额交易额外确认（仅非"仅卖出"模式）
        if trade_mode != 'sell_only':
            # 计算最大可能总金额（单笔最大 × 选中账户数 × 交易次数）
            total_max_amount = max_amt * \
                len(selected_account_indices) * num_trades

            if total_max_amount > 5000:
                print(f"\n" + "!"*60)
                print("[!]  【大额交易警告】")
                print(f"  单笔金额范围: ${min_amt:.2f} - ${max_amt:.2f}")
                print(f"  选中账户数: {len(selected_account_indices)}")
                print(f"  交易次数: {num_trades}")
                print(f"  最大可能总金额: ${total_max_amount:.2f}")
                print("!"*60)

                # 第二次确认
                print(f"\n【第二次确认】")
                confirm2 = input("大额交易,请再次输入 'done' 确认: ").strip().lower()

                if confirm2 != 'done':
                    print("✗ 已取消交易")
                    return

                print(f"✓ 第二次确认通过")

                # 第三次确认 - 最后确认
                print(f"\n" + "="*60)
                print("【第三次确认 - 最后确认】")
                if parent_market_title and selected_child_market:
                    print(
                        f"  市场: {parent_market_title}----{selected_child_market.market_title}")
                else:
                    print(f"  市场: {market_data.market_title}")
                print(f"  方向: {selected_token_name}")
                print(f"  单笔金额范围: ${min_amt:.2f} - ${max_amt:.2f}")
                print(f"  最大可能总金额: ${total_max_amount:.2f}")
                print("="*60)
                print("\n[!]  请仔细检查:")
                print("  - 市场选择是否正确?")
                print("  - 交易方向是否正确?")
                print("  - 交易金额是否正确?")

                confirm3 = input("\n✓ 确定选择无误? (yes/no): ").strip().lower()

                if confirm3 != 'yes':
                    print("✗ 已取消交易")
                    return

                print(f"\n✓✓✓ 三次确认完成,准备开始交易...")

        # 10. 检查盘口深度
        print(f"\n正在检查盘口深度...")

        # 显示当前交易的市场信息
        if parent_market_title and selected_child_market:
            print(f"\n交易市场:")
            print(f"  主市场: {parent_market_title}")
            print(f"  子市场: {selected_child_market.market_title}")
            print(f"  子市场ID: {market_id}")
        elif parent_market_title:
            print(f"\n交易市场:")
            print(f"  市场: {parent_market_title}")
            print(f"  市场ID: {market_id}")
        else:
            print(f"\n交易市场:")
            print(f"  市场: {market_data.market_title}")
            print(f"  市场ID: {market_id}")

        # 根据交易方向确定token_id
        if side_input == 'YES':
            token_id = market_data.yes_token_id
            print(f"\n✓ 交易方向: YES")
            print(f"  Token ID: {token_id}")
        else:
            token_id = market_data.no_token_id
            print(f"\n✓ 交易方向: NO")
            print(f"  Token ID: {token_id}")

        # 格式化价格显示函数（*100并去掉小数点后多余的0），提前定义防止后续调用时未定义
        def format_price(price):
            # 先四舍五入到0.1分精度，避免浮点数精度问题
            price_cent = round(price * 100, 1)
            if price_cent == int(price_cent):
                return f"{int(price_cent)}"
            else:
                return f"{price_cent:.1f}"

        # 初始化盘口详情变量（防止后续使用时未定义）
        bid_details = []
        ask_details = []

        try:
            # 获取盘口数据
            ob = OrderbookService.fetch_and_display(
                client, token_id,
                title="盘口信息",
                mode=OrderbookDisplay.MODE_WITH_DEPTH,
                max_rows=5,
                format_price_func=format_price
            )

            if ob['success'] and ob['bids'] and ob['asks']:
                bid_depth = ob['bid_depth']
                ask_depth = ob['ask_depth']

                # 构建 bid_details 和 ask_details 用于后续价格选择
                bid_details = []
                bid_cumulative = 0
                for i, (price, size) in enumerate(ob['bids'][:5]):
                    bid_cumulative += price * size
                    bid_details.append((i + 1, price, size, bid_cumulative))

                ask_details = []
                ask_cumulative = 0
                for i, (price, size) in enumerate(ob['asks'][:5]):
                    ask_cumulative += price * size
                    ask_details.append((i + 1, price, size, ask_cumulative))

                # 仅买入或买入+卖出模式才需要检查盘口
                if trade_mode != 'sell_only':
                    # 计算最大可能总金额（单笔最高 × 选中账户数 × 交易次数）
                    max_total_amount = max_amt * \
                        len(selected_account_indices) * num_trades

                    # 买入时检查卖盘深度,卖出时检查买盘深度
                    required_depth = ask_depth if side_input == 'YES' else bid_depth
                    depth_label = "卖1" if side_input == 'YES' else "买1"

                    print(f"\n盘口深度检查:")
                    print(f"  选中账户数: {len(selected_account_indices)}")
                    print(f"  交易次数: {num_trades}")
                    print(f"  单笔金额范围: ${min_amt:.2f} - ${max_amt:.2f}")
                    print(f"  最大可能总金额: ${max_total_amount:.2f}")
                    print(f"  {depth_label}盘口深度: ${required_depth:.2f}")

                    if required_depth < max_total_amount:
                        shortage = max_total_amount - required_depth
                        print(f"\n[!]  警告: 盘口深度可能不足!")
                        print(f"  {depth_label}盘口: ${required_depth:.2f}")
                        print(
                            f"  最大可能{'买入' if side_input == 'YES' else '卖出'}: ${max_total_amount:.2f}")
                        print(f"  缺口: ${shortage:.2f}")
                        print(f"\n  注意: 由于每个账户独立随机金额，实际总金额会小于最大值")

                        continue_choice = input(
                            "\n是否继续? (y/n): ").strip().lower()
                        if continue_choice != 'y':
                            print("✗ 已取消交易")
                            return
                    else:
                        print(f"✓ 盘口深度充足")
            else:
                error_msg = ob.get('error', '盘口数据为空')
                print(f"[!]  警告: {error_msg}")
                continue_choice = input(
                    "\n无法获取盘口信息,是否继续? (y/n): ").strip().lower()
                if continue_choice != 'y':
                    print("✗ 已取消交易")
                    return

        except Exception as e:
            print(f"[!]  盘口检查失败: {e}")
            continue_choice = input("\n无法获取盘口信息,是否继续? (y/n): ").strip().lower()
            if continue_choice != 'y':
                print("✗ 已取消交易")
                return

        # 10. 选择交易策略（根据模式调整询问顺序）
        buy_order_type = None
        buy_use_ask = False
        buy_price_index = 0  # 价格档位索引(0-4)，默认第1档
        sell_order_type = None
        sell_use_ask = False
        sell_price_index = 0  # 价格档位索引(0-4)，默认第1档
        layered_buy_config = None  # 分层买入配置
        layered_sell_config = None  # 分层卖出配置

        if trade_mode == 'sell_then_buy':
            # 先卖后买模式：先询问卖出策略，再询问买入策略
            print("\n【第一步：卖出策略】")
            print("1. 限价单 (指定价格)")
            print("2. 市价单 (立即成交)")
            sell_strategy = input("请选择 (1/2): ").strip()
            sell_order_type = LIMIT_ORDER if sell_strategy == '1' else MARKET_ORDER

            if sell_order_type == LIMIT_ORDER:
                if not bid_details and not ask_details:
                    print("[!] 无盘口数据，自动切换为市价单")
                    sell_order_type = MARKET_ORDER
                else:
                    print("\n卖出限价单价格选择:")
                    # 卖盘在上（价格从高到低，即卖5到卖1）
                    print("  卖盘（挂单等待）:")
                    ask_reversed = list(reversed(ask_details[:5]))
                    for num, price, size, depth in ask_reversed:
                        print(f"    {num+5}. 卖{num} {format_price(price)}¢")
                    for i in range(len(ask_details) + 1, 6):
                        print(f"    {i+5}. 卖{i} (无)")
                    # 买盘在下（价格从高到低，即买1到买5）
                    print("  买盘（立即成交）:")
                    for i, (num, price, size, depth) in enumerate(bid_details[:5], 1):
                        print(f"    {i}. 买{num} {format_price(price)}¢")
                    for i in range(len(bid_details) + 1, 6):
                        print(f"    {i}. 买{i} (无)")
                    sell_price_choice = input("请选择 (1-10): ").strip()
                    try:
                        sell_price_level = int(sell_price_choice)
                        if sell_price_level < 1 or sell_price_level > 10:
                            sell_price_level = 1  # 默认买1
                    except ValueError:
                        sell_price_level = 1  # 默认买1
                    sell_use_ask = (sell_price_level >= 6)  # 6-10是卖盘
                    sell_price_index = (
                        sell_price_level - 1) if sell_price_level <= 5 else (sell_price_level - 6)

            print("\n【第二步：买入策略】")
            print("1. 限价单 (指定价格)")
            print("2. 市价单 (立即成交)")
            buy_strategy = input("请选择 (1/2): ").strip()
            buy_order_type = LIMIT_ORDER if buy_strategy == '1' else MARKET_ORDER

            if buy_order_type == LIMIT_ORDER:
                if not bid_details and not ask_details:
                    print("[!] 无盘口数据，自动切换为市价单")
                    buy_order_type = MARKET_ORDER
                else:
                    print("\n买入限价单价格选择:")
                    # 卖盘在上（价格从高到低，即卖5到卖1）
                    print("  卖盘（立即成交）:")
                    ask_reversed = list(reversed(ask_details[:5]))
                    for num, price, size, depth in ask_reversed:
                        print(f"    {num+5}. 卖{num} {format_price(price)}¢")
                    for i in range(len(ask_details) + 1, 6):
                        print(f"    {i+5}. 卖{i} (无)")
                    # 买盘在下（价格从高到低，即买1到买5）
                    print("  买盘（挂单等待）:")
                    for i, (num, price, size, depth) in enumerate(bid_details[:5], 1):
                        print(f"    {i}. 买{num} {format_price(price)}¢")
                    for i in range(len(bid_details) + 1, 6):
                        print(f"    {i}. 买{i} (无)")
                    buy_price_choice = input("请选择 (1-10): ").strip()
                    try:
                        buy_price_level = int(buy_price_choice)
                        if buy_price_level < 1 or buy_price_level > 10:
                            buy_price_level = 6  # 默认卖1
                    except ValueError:
                        buy_price_level = 6  # 默认卖1
                    buy_use_ask = (buy_price_level >= 6)  # 6-10是卖盘
                    buy_price_index = (
                        buy_price_level - 1) if buy_price_level <= 5 else (buy_price_level - 6)

        elif trade_mode == 'sell_only':
            # 仅卖出模式
            print("\n卖出策略:")
            print("1. 限价单 (单档价格)")
            print("2. 市价单 (立即成交)")
            print("3. 分层挂单 (多档价格分散)")
            sell_strategy = input("请选择 (1/2/3): ").strip()

            # 分层挂单配置
            layered_sell_config = None

            if sell_strategy == '3':
                # 分层挂单模式
                sell_order_type = LIMIT_ORDER
                if not bid_details and not ask_details:
                    print("[!] 无盘口数据，无法使用分层挂单，自动切换为市价单")
                    sell_order_type = MARKET_ORDER
                else:
                    layered_sell_config = self._configure_layered_order(
                        'sell', bid_details, ask_details, format_price)
                    if not layered_sell_config:
                        print("[!] 分层配置取消，自动切换为市价单")
                        sell_order_type = MARKET_ORDER
            else:
                sell_order_type = LIMIT_ORDER if sell_strategy == '1' else MARKET_ORDER

                if sell_order_type == LIMIT_ORDER:
                    if not bid_details and not ask_details:
                        print("[!] 无盘口数据，自动切换为市价单")
                        sell_order_type = MARKET_ORDER
                    else:
                        print("\n限价单价格选择:")
                        # 卖盘在上（价格从高到低，即卖5到卖1）
                        print("  卖盘（挂单等待）:")
                        ask_reversed = list(reversed(ask_details[:5]))
                        for num, price, size, depth in ask_reversed:
                            print(
                                f"    {num+5}. 卖{num} {format_price(price)}¢")
                        for i in range(len(ask_details) + 1, 6):
                            print(f"    {i+5}. 卖{i} (无)")
                        # 买盘在下（价格从高到低，即买1到买5）
                        print("  买盘（立即成交）:")
                        for i, (num, price, size, depth) in enumerate(bid_details[:5], 1):
                            print(f"    {i}. 买{num} {format_price(price)}¢")
                        for i in range(len(bid_details) + 1, 6):
                            print(f"    {i}. 买{i} (无)")
                        sell_price_choice = input("请选择 (1-10): ").strip()
                        try:
                            sell_price_level = int(sell_price_choice)
                            if sell_price_level < 1 or sell_price_level > 10:
                                sell_price_level = 1  # 默认买1
                        except ValueError:
                            sell_price_level = 1  # 默认买1
                        sell_use_ask = (sell_price_level >= 6)  # 6-10是卖盘
                        sell_price_index = (
                            # 档位索引(0-4)
                            sell_price_level - 1) if sell_price_level <= 5 else (sell_price_level - 6)

        elif trade_mode == 'buy_only':
            # 仅买入模式
            print("\n买入策略:")
            print("1. 限价单 (单档价格)")
            print("2. 市价单 (立即成交)")
            print("3. 分层挂单 (多档价格分散)")
            buy_strategy = input("请选择 (1/2/3): ").strip()

            # 分层挂单配置
            layered_buy_config = None

            if buy_strategy == '3':
                # 分层挂单模式
                buy_order_type = LIMIT_ORDER
                if not bid_details and not ask_details:
                    print("[!] 无盘口数据，无法使用分层挂单，自动切换为市价单")
                    buy_order_type = MARKET_ORDER
                else:
                    layered_buy_config = self._configure_layered_order(
                        'buy', bid_details, ask_details, format_price)
                    if not layered_buy_config:
                        print("[!] 分层配置取消，自动切换为市价单")
                        buy_order_type = MARKET_ORDER
            else:
                buy_order_type = LIMIT_ORDER if buy_strategy == '1' else MARKET_ORDER

                if buy_order_type == LIMIT_ORDER:
                    if not bid_details and not ask_details:
                        print("[!] 无盘口数据，自动切换为市价单")
                        buy_order_type = MARKET_ORDER
                    else:
                        print("\n限价单价格选择:")
                        # 卖盘在上（价格从高到低，即卖5到卖1）
                        print("  卖盘（立即成交）:")
                        ask_reversed = list(reversed(ask_details[:5]))
                        for num, price, size, depth in ask_reversed:
                            print(
                                f"    {num+5}. 卖{num} {format_price(price)}¢")
                        for i in range(len(ask_details) + 1, 6):
                            print(f"    {i+5}. 卖{i} (无)")
                        # 买盘在下（价格从高到低，即买1到买5）
                        print("  买盘（挂单等待）:")
                        for i, (num, price, size, depth) in enumerate(bid_details[:5], 1):
                            print(f"    {i}. 买{num} {format_price(price)}¢")
                        for i in range(len(bid_details) + 1, 6):
                            print(f"    {i}. 买{i} (无)")
                        buy_price_choice = input("请选择 (1-10): ").strip()
                        try:
                            buy_price_level = int(buy_price_choice)
                            if buy_price_level < 1 or buy_price_level > 10:
                                buy_price_level = 6  # 默认卖1
                        except ValueError:
                            buy_price_level = 6  # 默认卖1
                        buy_use_ask = (buy_price_level >= 6)  # 6-10是卖盘
                        buy_price_index = (
                            # 档位索引(0-4)
                            buy_price_level - 1) if buy_price_level <= 5 else (buy_price_level - 6)

        else:
            # 先买后卖模式（buy_then_sell）：先询问买入策略，再询问卖出策略
            print("\n【第一步：买入策略】")
            print("1. 限价单 (指定价格)")
            print("2. 市价单 (立即成交)")
            buy_strategy = input("请选择 (1/2): ").strip()
            buy_order_type = LIMIT_ORDER if buy_strategy == '1' else MARKET_ORDER

            if buy_order_type == LIMIT_ORDER:
                if not bid_details and not ask_details:
                    print("[!] 无盘口数据，自动切换为市价单")
                    buy_order_type = MARKET_ORDER
                else:
                    print("\n买入限价单价格选择:")
                    # 卖盘在上（价格从高到低，即卖5到卖1）
                    print("  卖盘（立即成交）:")
                    ask_reversed = list(reversed(ask_details[:5]))
                    for num, price, size, depth in ask_reversed:
                        print(f"    {num+5}. 卖{num} {format_price(price)}¢")
                    for i in range(len(ask_details) + 1, 6):
                        print(f"    {i+5}. 卖{i} (无)")
                    # 买盘在下（价格从高到低，即买1到买5）
                    print("  买盘（挂单等待）:")
                    for i, (num, price, size, depth) in enumerate(bid_details[:5], 1):
                        print(f"    {i}. 买{num} {format_price(price)}¢")
                    for i in range(len(bid_details) + 1, 6):
                        print(f"    {i}. 买{i} (无)")
                    buy_price_choice = input("请选择 (1-10): ").strip()
                    try:
                        buy_price_level = int(buy_price_choice)
                        if buy_price_level < 1 or buy_price_level > 10:
                            buy_price_level = 6  # 默认卖1
                    except ValueError:
                        buy_price_level = 6  # 默认卖1
                    buy_use_ask = (buy_price_level >= 6)  # 6-10是卖盘
                    buy_price_index = (
                        buy_price_level - 1) if buy_price_level <= 5 else (buy_price_level - 6)

            print("\n【第二步：卖出策略】")
            print("1. 限价单 (指定价格)")
            print("2. 市价单 (立即成交)")
            sell_strategy = input("请选择 (1/2): ").strip()
            sell_order_type = LIMIT_ORDER if sell_strategy == '1' else MARKET_ORDER

            if sell_order_type == LIMIT_ORDER:
                if not bid_details and not ask_details:
                    print("[!] 无盘口数据，自动切换为市价单")
                    sell_order_type = MARKET_ORDER
                else:
                    print("\n卖出限价单价格选择:")
                    # 卖盘在上（价格从高到低，即卖5到卖1）
                    print("  卖盘（挂单等待）:")
                    ask_reversed = list(reversed(ask_details[:5]))
                    for num, price, size, depth in ask_reversed:
                        print(f"    {num+5}. 卖{num} {format_price(price)}¢")
                    for i in range(len(ask_details) + 1, 6):
                        print(f"    {i+5}. 卖{i} (无)")
                    # 买盘在下（价格从高到低，即买1到买5）
                    print("  买盘（立即成交）:")
                    for i, (num, price, size, depth) in enumerate(bid_details[:5], 1):
                        print(f"    {i}. 买{num} {format_price(price)}¢")
                    for i in range(len(bid_details) + 1, 6):
                        print(f"    {i}. 买{i} (无)")
                    sell_price_choice = input("请选择 (1-10): ").strip()
                    try:
                        sell_price_level = int(sell_price_choice)
                        if sell_price_level < 1 or sell_price_level > 10:
                            sell_price_level = 1  # 默认买1
                    except ValueError:
                        sell_price_level = 1  # 默认买1
                    sell_use_ask = (sell_price_level >= 6)  # 6-10是卖盘
                    sell_price_index = (
                        sell_price_level - 1) if sell_price_level <= 5 else (sell_price_level - 6)

        # 12. 开始交易
        print("\n" + "="*60)
        print("开始执行交易")
        print("="*60)

        # 定义单账户交易执行函数
        def execute_account_trading(account_idx, client, config, account_balance):
            """单个账户的交易执行函数"""
            print(f"\n{'='*60}")
            print(f"{config.remark} [{config.eoa_address[:10]}...]")
            print(f"{'='*60}")

            actual_num_trades = num_trades

            # 根据交易模式和账户余额调整金额范围
            if trade_mode == 'sell_only':
                # 仅卖出模式：不需要调整金额范围，直接使用持仓
                if account_balance == 0:
                    print(f"  ⊘ 账户持仓为0，跳过")
                    return
                print(
                    f"  可用持仓: {account_balance} tokens，将分{actual_num_trades}次卖出")
            else:
                # 买入模式：根据账户USDT余额调整金额范围
                account_min = min(min_amt, account_balance)
                account_max = min(max_amt, account_balance)

                if account_balance == 0:
                    print(f"  ⊘ 账户余额为0，跳过")
                    return

                # 计算本次所需最低金额
                required_min = min_amt * actual_num_trades
                if account_balance < required_min:
                    # 检查是否连一次最低交易都做不了
                    if account_balance < min_amt:
                        print(
                            f"  ⊘ 余额不足: ${account_balance:.2f} < 单笔最低${min_amt:.2f}，跳过此账户")
                        return
                    # 余额不足以完成全部交易次数，但可以做部分
                    possible_trades = int(account_balance / min_amt)
                    print(
                        f"  [!] 余额${account_balance:.2f} < 所需${required_min:.2f}，调整交易次数: {actual_num_trades} → {possible_trades}")
                    actual_num_trades = possible_trades
                    account_max = min(
                        max_amt, account_balance / actual_num_trades)
                    account_min = min(min_amt, account_max)

                if account_balance < min_amt:
                    print(
                        f"  [!]  余额 ${account_balance:.2f} 低于最低金额，调整为 ${account_min:.2f}-${account_max:.2f}")

                # 为当前账户随机一个交易金额
                account_amount = random.uniform(account_min, account_max)
                account_amount = round(account_amount, 2)
                print(f"  本次交易金额: ${account_amount:.2f}")

            # 拆分金额（每次交易在范围内随机，使用调整后的次数）
            if trade_mode == 'sell_only':
                # 卖出模式：不预先分配数量，每次实时查询余额后动态计算
                # 因为挂单会占用余额，预先分配会导致失败
                amounts = []  # 留空，每次卖出时实时计算
            else:
                # 买入模式：拆分金额
                amounts = self.split_amounts(account_amount, actual_num_trades)

            # 初始化变量
            total_bought = 0  # 累计买入的token数量

            # 查询买入前的初始token余额（使用SDK的get_my_positions）
            initial_token_balance = 0
            try:
                positions_response = client.get_my_positions()

                if positions_response.errno == 0:
                    # 修复：使用result.list而不是result.data
                    positions = positions_response.result.list if hasattr(
                        positions_response.result, 'list') else []
                    for position in positions:
                        pos_token_id = str(position.token_id) if hasattr(
                            position, 'token_id') else None
                        if pos_token_id == str(token_id):
                            balance = position.shares_owned if hasattr(
                                position, 'shares_owned') else 0
                            initial_token_balance = int(float(balance))
                            print(f"  初始token余额: {initial_token_balance}")
                            break
            except Exception as e:
                print(f"  [!]  无法查询初始余额: {e}")

            # 根据交易模式决定执行顺序
            # sell_then_buy模式：先卖后买
            if trade_mode == 'sell_then_buy':
                # 先执行卖出
                pass  # 卖出逻辑在后面

            # buy_only, buy_then_sell模式：先执行买入
            if trade_mode in ['buy_only', 'buy_then_sell']:
                # 检查是否使用分层挂单
                if trade_mode == 'buy_only' and layered_buy_config:
                    # 分层买入模式
                    print(f"\n执行分层买入挂单 (总金额: ${account_amount:.2f})...")
                    layered_result = self._execute_layered_order(
                        client, market_id, token_id, 'buy',
                        layered_buy_config, total_amount=account_amount
                    )
                    print(
                        f"  分层买入完成: 成功{layered_result['success']}笔, 失败{layered_result['failed']}笔")
                else:
                    # 普通买入模式
                    print(f"\n执行 {actual_num_trades} 次买入交易...")
                    for i, amount in enumerate(amounts, 1):
                        try:
                            # 获取最新盘口
                            ob = OrderbookService.fetch(client, token_id)

                            if ob['success']:
                                if buy_order_type == LIMIT_ORDER:
                                    side = 'ask' if buy_use_ask else 'bid'
                                    price = OrderbookService.get_price_at_level(
                                        ob, side, buy_price_index)
                                    price_str = f"{price:.6f}"
                                    price_display = self.format_price(
                                        price) + '¢'
                                else:
                                    price_str = "0"  # 市价单
                                    price_display = "市价"

                                # 创建订单
                                order = PlaceOrderDataInput(
                                    marketId=market_id,
                                    tokenId=token_id,
                                    side=OrderSide.BUY,
                                    orderType=buy_order_type,
                                    price=price_str,
                                    makerAmountInQuoteToken=round(amount, 2)
                                )

                                # 下单
                                result = client.place_order(
                                    order, check_approval=True)

                                if result.errno == 0:
                                    print(
                                        f"  ✓ 买入#{i}: ${amount:.2f} @ {price_display}")
                                else:
                                    print(
                                        f"  ✗ 买入#{i}失败: {self.translate_error(result.errmsg)}")
                            else:
                                print(f"  ✗ 获取盘口失败: {ob.get('error', '未知错误')}")

                            # 随机延迟
                            delay = random.uniform(3, 10)
                            time.sleep(delay)

                        except Exception as e:
                            error_str = str(e)
                            if "504" in error_str or "Gateway Time-out" in error_str:
                                print(
                                    f"  [!] 买入#{i}: 网关超时(504)，订单可能已提交，请稍后检查持仓")
                            elif "502" in error_str or "Bad Gateway" in error_str:
                                print(f"  [!] 买入#{i}: 网关错误(502)，请稍后重试")
                            elif "503" in error_str or "Service Unavailable" in error_str:
                                print(f"  [!] 买入#{i}: 服务暂时不可用(503)，请稍后重试")
                            elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                                print(f"  [!] 买入#{i}: 请求超时，请检查网络连接")
                            elif "Connection" in error_str:
                                print(f"  [!] 买入#{i}: 连接失败，请检查网络或代理")
                            else:
                                print(f"  ✗ 买入#{i}异常: {e}")

            # 如果是仅买入模式，买入完成后直接结束
            if trade_mode == 'buy_only':
                print(f"\n✓ 仅买入模式，交易完成")
                return

            # 如果是买入+卖出模式，直接进入卖出（不等待，由外层统一等待）
            if trade_mode in ['buy_then_sell', 'sell_then_buy']:
                pass  # 继续执行卖出

            # 根据交易模式决定是否执行卖出
            if trade_mode in ['sell_only', 'buy_then_sell', 'sell_then_buy']:
                # 如果是仅卖出模式，需要先查询当前token余额
                if trade_mode == 'sell_only':
                    try:
                        positions_response = client.get_my_positions()

                        if positions_response.errno == 0:
                            total_shares = 0
                            # 使用result.list
                            positions = positions_response.result.list if hasattr(
                                positions_response.result, 'list') else []

                            for position in positions:
                                pos_token_id = str(position.token_id) if hasattr(
                                    position, 'token_id') else None
                                if pos_token_id == str(token_id):
                                    shares = position.shares_owned if hasattr(
                                        position, 'shares_owned') else 0
                                    total_shares = int(float(shares))
                                    break

                            # 查询挂单占用（使用Open Orders而不是locked_shares）
                            pending_amount = 0
                            try:
                                orders_response = client.get_my_orders()
                                if orders_response.errno == 0:
                                    orders = orders_response.result.list if hasattr(
                                        orders_response.result, 'list') else []
                                    for order in orders:
                                        order_market_id = order.market_id if hasattr(
                                            order, 'market_id') else None
                                        order_outcome_side = order.outcome_side if hasattr(
                                            order, 'outcome_side') else None
                                        order_side = order.side if hasattr(
                                            order, 'side') else None
                                        order_status = order.status if hasattr(
                                            order, 'status') else None

                                        if (order_market_id == market_id and
                                            order_outcome_side == (1 if selected_token_name == 'YES' else 2) and
                                                order_side == 2 and order_status == 1):
                                            order_shares = float(order.order_shares if hasattr(
                                                order, 'order_shares') else 0)
                                            filled_shares = float(order.filled_shares if hasattr(
                                                order, 'filled_shares') else 0)
                                            pending_amount += int(
                                                order_shares - filled_shares)
                            except Exception:
                                pending_amount = 0

                            # 可用余额 = 总持仓 - 挂单占用
                            total_bought = total_shares - pending_amount

                            if pending_amount > 0:
                                print(
                                    f"\n  当前总持仓: {total_shares} tokens (挂单{pending_amount}, 可用{total_bought})")
                            else:
                                print(f"\n  当前可用余额: {total_bought} tokens")

                            if total_bought <= 0:
                                print(f"  [!]  当前无可卖token，跳过卖出")
                                return

                            if total_bought < 5:
                                print(f"  [!]  可用余额太少(<5)，不值得卖出，跳过")
                                return
                        else:
                            print(
                                f"  [!]  无法查询余额: errno={positions_response.errno}")
                            return
                    except Exception as e:
                        print(f"  ✗ 查询余额异常: {e}")
                        return

                # 检查是否使用分层挂单（仅卖出模式）
                if trade_mode == 'sell_only' and layered_sell_config:
                    # 分层卖出模式
                    print(f"\n执行分层卖出挂单 (总份额: {total_bought})...")
                    layered_result = self._execute_layered_order(
                        client, market_id, token_id, 'sell',
                        layered_sell_config, total_shares=total_bought
                    )
                    print(
                        f"  分层卖出完成: 成功{layered_result['success']}笔, 失败{layered_result['failed']}笔")
                    return

                # 执行卖出交易（普通模式）
                print(f"\n执行 {actual_num_trades} 次卖出交易...")

                # 卖出循环：每次都实时查询可用余额
                for i in range(1, actual_num_trades + 1):
                    try:
                        # 实时查询当前可用余额
                        positions_response = client.get_my_positions()

                        if positions_response.errno != 0:
                            print(
                                f"  ✗ 卖出#{i}: 无法查询余额，errno={positions_response.errno}")
                            continue

                        total_shares = 0
                        positions = positions_response.result.list if hasattr(
                            positions_response.result, 'list') else []

                        for position in positions:
                            pos_token_id = str(position.token_id) if hasattr(
                                position, 'token_id') else None
                            if pos_token_id == str(token_id):
                                total_shares = int(
                                    float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
                                break

                        # 查询挂单占用（使用Open Orders）
                        pending_amount = 0
                        try:
                            orders_response = client.get_my_orders()
                            if orders_response.errno == 0:
                                orders = orders_response.result.list if hasattr(
                                    orders_response.result, 'list') else []
                                for order in orders:
                                    order_market_id = order.market_id if hasattr(
                                        order, 'market_id') else None
                                    order_outcome_side = order.outcome_side if hasattr(
                                        order, 'outcome_side') else None
                                    order_side = order.side if hasattr(
                                        order, 'side') else None
                                    order_status = order.status if hasattr(
                                        order, 'status') else None

                                    if (order_market_id == market_id and
                                        order_outcome_side == (1 if selected_token_name == 'YES' else 2) and
                                            order_side == 2 and order_status == 1):
                                        order_shares = float(order.order_shares if hasattr(
                                            order, 'order_shares') else 0)
                                        filled_shares = float(order.filled_shares if hasattr(
                                            order, 'filled_shares') else 0)
                                        pending_amount += int(order_shares -
                                                              filled_shares)
                        except Exception:
                            pending_amount = 0

                        # 计算可用余额 = 总持仓 - 挂单未成交
                        available = total_shares - pending_amount

                        if available <= 0:
                            # 递增等待重试：5s -> 10s -> 20s，三次不成功则跳过
                            retry_delays = [5, 10, 20]
                            retry_success = False
                            for retry_idx, delay in enumerate(retry_delays):
                                print(
                                    f"  ⊘ 卖出#{i}: 无可用余额（总持仓{total_shares}, 挂单{pending_amount}），等待{delay}秒后重试({retry_idx+1}/3)...")
                                time.sleep(delay)

                                # 重新查询持仓
                                positions_response = client.get_my_positions()
                                if positions_response.errno == 0:
                                    positions = positions_response.result.list if hasattr(
                                        positions_response.result, 'list') else []
                                    total_shares = 0
                                    for position in positions:
                                        pos_token_id = str(position.token_id) if hasattr(
                                            position, 'token_id') else None
                                        if pos_token_id == str(token_id):
                                            total_shares = int(
                                                float(position.shares_owned if hasattr(position, 'shares_owned') else 0))
                                            break

                                    # 重新查询挂单
                                    pending_amount = 0
                                    try:
                                        orders_response = client.get_my_orders()
                                        if orders_response.errno == 0:
                                            orders = orders_response.result.list if hasattr(
                                                orders_response.result, 'list') else []
                                            for order in orders:
                                                order_market_id = order.market_id if hasattr(
                                                    order, 'market_id') else None
                                                order_outcome_side = order.outcome_side if hasattr(
                                                    order, 'outcome_side') else None
                                                order_side = order.side if hasattr(
                                                    order, 'side') else None
                                                order_status = order.status if hasattr(
                                                    order, 'status') else None

                                                if (order_market_id == market_id and
                                                    order_outcome_side == (1 if selected_token_name == 'YES' else 2) and
                                                        order_side == 2 and order_status == 1):
                                                    order_shares = float(order.order_shares if hasattr(
                                                        order, 'order_shares') else 0)
                                                    filled_shares = float(order.filled_shares if hasattr(
                                                        order, 'filled_shares') else 0)
                                                    pending_amount += int(
                                                        order_shares - filled_shares)
                                    except Exception:
                                        pending_amount = 0

                                    available = total_shares - pending_amount
                                    if available > 0:
                                        print(
                                            f"  ✓ 持仓已到账: {available} tokens可用")
                                        retry_success = True
                                        break

                            if not retry_success:
                                print(f"  ✗ 卖出#{i}: 等待3次后仍无可用余额，跳过")
                                continue

                        # 计算本次卖出数量
                        if i == actual_num_trades:
                            # 构建市场显示名称
                            if parent_market_id and selected_child_market:
                                child_title = selected_child_market.market_title if hasattr(
                                    selected_child_market, 'market_title') else str(market_id)
                                market_display = f"市场{parent_market_id}#{child_title}"
                            else:
                                market_display = f"市场{market_id}#{selected_token_name}"

                            # 最后一次：清仓
                            token_amount = available
                            if pending_amount > 0:
                                print(
                                    f"  卖出#{i} (最后一次，清仓): {token_amount} tokens [{market_display}] (总持仓{total_shares}, 挂单{pending_amount})")
                            else:
                                print(
                                    f"  卖出#{i} (最后一次，清仓): {token_amount} tokens [{market_display}]")
                        else:
                            # 构建市场显示名称
                            if parent_market_id and selected_child_market:
                                child_title = selected_child_market.market_title if hasattr(
                                    selected_child_market, 'market_title') else str(market_id)
                                market_display = f"市场{parent_market_id}#{child_title}"
                            else:
                                market_display = f"市场{market_id}#{selected_token_name}"

                            # 前N-1次：动态计算
                            remaining_trades = actual_num_trades - i + 1
                            base_amount = available / remaining_trades
                            # 随机浮动 ±10%
                            token_amount = int(
                                base_amount * random.uniform(0.9, 1.1))
                            # 确保不超过可用余额，且为后续保留至少1个
                            token_amount = min(
                                token_amount, available - (remaining_trades - 1))
                            token_amount = max(1, token_amount)
                            print(
                                f"  卖出#{i}: {token_amount} tokens [{market_display}]")

                        # 检查金额是否太小
                        if token_amount < 20:
                            print(f"  ⊘ 卖出#{i}: 跳过(数量{token_amount}<20)")
                            continue

                        if token_amount <= 0:
                            print(f"  ⊘ 卖出#{i}: 跳过(数量为0)")
                            continue

                    except Exception as e:
                        print(f"  ✗ 卖出#{i}: 查询余额异常: {e}")
                        continue

                    try:
                        # 获取最新盘口
                        ob = OrderbookService.fetch(client, token_id)

                        if ob['success']:
                            if sell_order_type == LIMIT_ORDER:
                                side = 'ask' if sell_use_ask else 'bid'
                                price = OrderbookService.get_price_at_level(
                                    ob, side, sell_price_index)
                                price_str = f"{price:.6f}"
                                price_display = self.format_price(price) + '¢'
                            else:
                                price_str = "0"  # 市价单
                                price_display = "市价"

                            # 创建订单 - 按用户设置的次数卖出
                            order = PlaceOrderDataInput(
                                marketId=market_id,
                                tokenId=token_id,
                                side=OrderSide.SELL,
                                orderType=sell_order_type,
                                price=price_str,
                                makerAmountInBaseToken=token_amount
                            )

                            # 下单
                            result = client.place_order(
                                order, check_approval=True)

                            if result.errno == 0:
                                print(
                                    f"  ✓ 卖出#{i}: {token_amount} tokens @ {price_display}")
                            else:
                                # 检查是否是余额不足错误
                                if 'Insufficient token balance' in str(result.errmsg):
                                    # 解析可用余额
                                    import re
                                    match = re.search(
                                        r'only (\d+\.?\d*)', str(result.errmsg))
                                    if match:
                                        actual_available = int(
                                            float(match.group(1)))
                                        if actual_available >= 20:
                                            print(
                                                f"  [!]  余额不足，改卖可用余额: {actual_available} tokens")
                                            # 重新下单
                                            order2 = PlaceOrderDataInput(
                                                marketId=market_id,
                                                tokenId=token_id,
                                                side=OrderSide.SELL,
                                                orderType=sell_order_type,
                                                price=price_str,
                                                makerAmountInBaseToken=actual_available
                                            )
                                            result2 = client.place_order(
                                                order2, check_approval=True)
                                            if result2.errno == 0:
                                                print(
                                                    f"  ✓ 卖出#{i}: {actual_available} tokens @ {price_display}")
                                            else:
                                                print(
                                                    f"  ✗ 卖出#{i}重试失败: {self.translate_error(result2.errmsg)}")
                                        else:
                                            print(
                                                f"  ⊘ 卖出#{i}: 可用余额{actual_available}<20，跳过")
                                    else:
                                        print(
                                            f"  ✗ 卖出#{i}失败: {self.translate_error(result.errmsg)}")
                                else:
                                    print(
                                        f"  ✗ 卖出#{i}失败: {self.translate_error(result.errmsg)}")
                        else:
                            print(f"  ✗ 获取盘口失败: {ob.get('error', '未知错误')}")

                        # 随机延迟
                        delay = random.uniform(3, 10)
                        time.sleep(delay)

                    except Exception as e:
                        error_str = str(e)
                        if "504" in error_str or "Gateway Time-out" in error_str:
                            print(f"  [!] 卖出#{i}: 网关超时(504)，订单可能已提交，请稍后检查持仓")
                        elif "502" in error_str or "Bad Gateway" in error_str:
                            print(f"  [!] 卖出#{i}: 网关错误(502)，请稍后重试")
                        elif "503" in error_str or "Service Unavailable" in error_str:
                            print(f"  [!] 卖出#{i}: 服务暂时不可用(503)，请稍后重试")
                        elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                            print(f"  [!] 卖出#{i}: 请求超时，请检查网络连接")
                        elif "Connection" in error_str:
                            print(f"  [!] 卖出#{i}: 连接失败，请检查网络或代理")
                        else:
                            print(f"  ✗ 卖出#{i}异常: {e}")

            # 如果是sell_then_buy模式，卖出完成后执行买入
            if trade_mode == 'sell_then_buy':
                print(f"\n执行 {actual_num_trades} 次买入交易...")
                for i, amount in enumerate(amounts, 1):
                    try:
                        ob = OrderbookService.fetch(client, token_id)

                        if ob['success']:
                            if buy_order_type == LIMIT_ORDER:
                                side = 'ask' if buy_use_ask else 'bid'
                                price = OrderbookService.get_price_at_level(
                                    ob, side, buy_price_index)
                                price_str = f"{price:.6f}"
                                price_display = self.format_price(price) + '¢'
                            else:
                                price_str = "0"
                                price_display = "市价"

                            order = PlaceOrderDataInput(
                                marketId=market_id,
                                tokenId=token_id,
                                side=OrderSide.BUY,
                                orderType=buy_order_type,
                                price=price_str,
                                makerAmountInQuoteToken=round(amount, 2)
                            )

                            result = client.place_order(
                                order, check_approval=True)

                            if result.errno == 0:
                                print(
                                    f"  ✓ 买入#{i}: ${amount:.2f} @ {price_display}")
                            else:
                                print(
                                    f"  ✗ 买入#{i}失败: {self.translate_error(result.errmsg)}")
                        else:
                            print(f"  ✗ 获取盘口失败: {ob.get('error', '未知错误')}")

                        delay = random.uniform(3, 10)
                        time.sleep(delay)

                    except Exception as e:
                        error_str = str(e)
                        if "504" in error_str or "Gateway Time-out" in error_str:
                            print(f"  [!] 买入#{i}: 网关超时(504)，订单可能已提交，请稍后检查持仓")
                        elif "502" in error_str or "Bad Gateway" in error_str:
                            print(f"  [!] 买入#{i}: 网关错误(502)，请稍后重试")
                        elif "503" in error_str or "Service Unavailable" in error_str:
                            print(f"  [!] 买入#{i}: 服务暂时不可用(503)，请稍后重试")
                        elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                            print(f"  [!] 买入#{i}: 请求超时，请检查网络连接")
                        elif "Connection" in error_str:
                            print(f"  [!] 买入#{i}: 连接失败，请检查网络或代理")
                        else:
                            print(f"  ✗ 买入#{i}异常: {e}")

        # 多账户后台并发执行（每个账户独立线程，使用各自代理）
        import threading
        threads = []

        def run_account_in_background(account_idx, client, config, account_balance):
            """后台执行单个账户的交易（代理已绑定到client）"""
            execute_account_trading(
                account_idx, client, config, account_balance)

        print(f"\n启动 {len(all_accounts)} 个账户后台执行...")

        for i, (account_idx, client, config) in enumerate(all_accounts):
            # 获取账户余额
            if trade_mode == 'sell_only':
                account_balance = token_balances.get(account_idx, 0)
            else:
                account_balance = available_amounts.get(account_idx, 0)

            # 创建并启动线程
            t = threading.Thread(
                target=run_account_in_background,
                args=(account_idx, client, config, account_balance),
                name=f"Account-{config.remark}"
            )
            threads.append(t)
            t.start()

            # 错开启动时间，避免同时发起请求
            if i < len(all_accounts) - 1:
                time.sleep(random.uniform(0.5, 1.5))

        # 等待所有线程完成
        print(f"\n等待所有账户完成交易...")
        for t in threads:
            t.join()

        print("\n" + "="*60)
        print("所有交易完成!")
        print("="*60)

    def websocket_monitor_menu(self):
        """WebSocket 实时监控菜单"""
        print(f"\n{'='*60}")
        print(f"{'WebSocket 实时监控':^60}")
        print(f"{'='*60}")

        # 使用第一个账户的 API Key
        if not self.configs:
            print("✗ 没有可用的账户配置")
            return

        api_key = self.configs[0].api_key

        # 输入市场ID
        market_input = input("\n请输入要监控的市场ID (多个用逗号分隔): ").strip()
        if not market_input:
            print("✗ 未输入市场ID")
            return

        try:
            market_ids = [int(m.strip())
                          for m in market_input.split(',') if m.strip()]
        except ValueError:
            print("✗ 市场ID格式错误，请输入数字")
            return

        if not market_ids:
            print("✗ 未输入有效的市场ID")
            return

        # 获取市场标题
        market_titles = {}
        print("\n正在获取市场信息...")
        for market_id in market_ids:
            try:
                resp = requests.get(
                    f"https://api.opinion.trade/api/v1/markets/{market_id}",
                    headers={'apikey': api_key},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    market_titles[market_id] = data.get(
                        'title', f'Market#{market_id}')[:30]
                    print(f"  ✓ {market_id}: {market_titles[market_id]}")
            except Exception:
                market_titles[market_id] = f'Market#{market_id}'

        # 选择订阅类型
        print(f"\n{'='*60}")
        print(f"{'选择订阅类型':^60}")
        print(f"{'='*60}")
        print("  1. 全部 (订单簿+价格+成交)")
        print("  2. 仅订单簿变动")
        print("  3. 仅价格变动")
        print("  4. 仅成交信息")
        print("  5. 价格+成交 (推荐)")

        sub_choice = input("\n请选择 (1-5, 默认5): ").strip() or "5"

        subscribe_orderbook = sub_choice in ['1', '2']
        subscribe_price = sub_choice in ['1', '3', '5']
        subscribe_trade = sub_choice in ['1', '4', '5']

        # 创建监控器并启动
        monitor = WebSocketMonitor(api_key)

        print(f"\n正在连接 WebSocket...")

        async def run_monitor():
            await monitor.start_monitoring(
                market_ids=market_ids,
                market_titles=market_titles,
                subscribe_orderbook=subscribe_orderbook,
                subscribe_price=subscribe_price,
                subscribe_trade=subscribe_trade
            )

        try:
            asyncio.run(run_monitor())
        except KeyboardInterrupt:
            print("\n✓ 监控已停止")


# 代理地址缓存文件路径
PROXY_CACHE_FILE = "proxy_cache.json"


def load_proxy_cache() -> dict:
    """加载代理地址缓存

    Returns:
        {eoa_address: proxy_address, ...}
    """
    try:
        if os.path.exists(PROXY_CACHE_FILE):
            with open(PROXY_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_proxy_cache(cache: dict):
    """保存代理地址缓存"""
    try:
        with open(PROXY_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def fetch_proxy_address(eoa_address: str, use_cache: bool = True) -> Optional[str]:
    """通过API获取代理地址(multiSignedWalletAddress)

    Args:
        eoa_address: EOA钱包地址
        use_cache: 是否使用缓存（默认True）

    Returns:
        代理地址，获取失败返回None
    """
    # 先检查缓存
    if use_cache:
        cache = load_proxy_cache()
        if eoa_address.lower() in cache:
            return cache[eoa_address.lower()]

    try:
        profile_url = f"https://proxy.opinion.trade:8443/api/bsc/api/v2/user/{eoa_address}/profile?chainId=56"

        # 直连模式，不使用代理
        response = requests.get(profile_url, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data.get('errno') == 0:
                result = data.get('result', {})
                multi_signed = result.get('multiSignedWalletAddress', {})
                # BSC chainId = 56
                proxy_addr = multi_signed.get('56')
                if proxy_addr:
                    # 保存到缓存
                    cache = load_proxy_cache()
                    cache[eoa_address.lower()] = proxy_addr
                    save_proxy_cache(cache)
                return proxy_addr
        return None
    except Exception as e:
        return None


def parse_config_line(line: str) -> List[str]:
    """解析配置行，支持多种分隔符（|、空格、Tab）混合使用

    Returns:
        解析后的字段列表
    """
    import re
    # 先用 | 分割
    parts = line.split('|')
    result = []
    for part in parts:
        # 每个部分再用空格/Tab分割
        sub_parts = re.split(r'[\s\t]+', part.strip())
        result.extend([p for p in sub_parts if p])
    return result


def load_configs(config_file: str) -> List[TraderConfig]:
    """从配置文件加载配置

    支持多种分隔符: | 空格 Tab（可混合使用）

    格式:
    - 4字段: 备注 api_key EOA地址 私钥 → 代理地址自动获取
    - 5字段: 备注 api_key EOA地址 私钥 代理地址
    - 6字段: 备注 api_key EOA地址 私钥 代理地址 (忽略第6列)
    """
    configs = []
    need_fetch_proxy = []  # 需要获取代理地址的配置索引

    with open(config_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = parse_config_line(line)
            if len(parts) >= 4:
                remark = parts[0]
                api_key = parts[1]
                eoa_address = parts[2]
                private_key = parts[3]

                if len(parts) == 4:
                    # 4字段: 无代理地址
                    config = TraderConfig(
                        remark=remark,
                        api_key=api_key,
                        eoa_address=eoa_address,
                        private_key=private_key,
                        proxy_address=None
                    )
                    need_fetch_proxy.append(len(configs))
                elif len(parts) == 5:
                    # 5字段: 判断第5列是代理地址还是其他
                    fifth = parts[4]
                    if fifth.startswith('0x') and len(fifth) == 42:
                        # 第5列是代理地址
                        config = TraderConfig(
                            remark=remark,
                            api_key=api_key,
                            eoa_address=eoa_address,
                            private_key=private_key,
                            proxy_address=fifth
                        )
                    else:
                        # 第5列不是代理地址，忽略
                        config = TraderConfig(
                            remark=remark,
                            api_key=api_key,
                            eoa_address=eoa_address,
                            private_key=private_key,
                            proxy_address=None
                        )
                        need_fetch_proxy.append(len(configs))
                else:
                    # 6字段及以上: 第5列是代理地址
                    config = TraderConfig(
                        remark=remark,
                        api_key=api_key,
                        eoa_address=eoa_address,
                        private_key=private_key,
                        proxy_address=parts[4] if parts[4].startswith(
                            '0x') else None
                    )
                    if not config.proxy_address:
                        need_fetch_proxy.append(len(configs))
                configs.append(config)
            else:
                print(f"[!]  警告: 第{line_num}行格式不正确，已跳过 (只有{len(parts)}个字段)")
                print(f"   正确格式: 备注 api_key EOA地址 私钥 [代理地址]")
                print(f"   分隔符支持: | 空格 Tab（可混合使用）")

    # 自动获取缺失的代理地址（使用缓存优化）
    if need_fetch_proxy:
        # 先加载缓存，检查哪些已有缓存
        cache = load_proxy_cache()
        cached_count = 0
        fetch_needed = []

        for idx in need_fetch_proxy:
            config = configs[idx]
            eoa_lower = config.eoa_address.lower()
            if eoa_lower in cache:
                # 缓存命中，直接使用
                config.proxy_address = cache[eoa_lower]
                cached_count += 1
            else:
                # 需要从API获取
                fetch_needed.append(idx)

        if cached_count > 0:
            print(f"\n✓ 从缓存加载 {cached_count} 个代理地址")

        if fetch_needed:
            print(f"正在获取 {len(fetch_needed)} 个新账户的代理地址...")
            failed = []
            for idx in fetch_needed:
                config = configs[idx]
                proxy_addr = fetch_proxy_address(
                    config.eoa_address, use_cache=False)
                if proxy_addr:
                    config.proxy_address = proxy_addr
                    print(
                        f"  ✓ [{config.remark}] {proxy_addr[:10]}...{proxy_addr[-6:]}")
                else:
                    failed.append(config.remark)
                    print(f"  ✗ [{config.remark}] 获取失败")

            if failed:
                print(
                    f"\n[!] 警告: {len(failed)} 个账户获取代理地址失败: {', '.join(failed)}")
                print("    请检查网络连接或EOA地址是否正确")

    return configs


def load_configs_from_directory(config_dir: str) -> List[TraderConfig]:
    """从目录加载所有配置文件

    支持的文件格式: .txt, .conf, .cfg
    自动跳过以 . 或 _ 开头的文件
    """
    all_configs = []
    supported_extensions = ('.txt', '.conf', '.cfg')

    if not os.path.isdir(config_dir):
        print(f"✗ 目录不存在: {config_dir}")
        return []

    # 获取目录下所有配置文件
    config_files = []
    for filename in sorted(os.listdir(config_dir)):
        # 跳过隐藏文件和临时文件
        if filename.startswith('.') or filename.startswith('_'):
            continue
        if filename.endswith(supported_extensions):
            config_files.append(os.path.join(config_dir, filename))

    if not config_files:
        print(f"✗ 目录中没有找到配置文件: {config_dir}")
        print(f"  支持的格式: {', '.join(supported_extensions)}")
        return []

    print(f"\n在目录 {config_dir} 中找到 {len(config_files)} 个配置文件:")
    for f in config_files:
        print(f"  - {os.path.basename(f)}")

    # 加载每个配置文件
    for config_file in config_files:
        try:
            configs = load_configs(config_file)
            if configs:
                print(
                    f"  ✓ {os.path.basename(config_file)}: {len(configs)} 个账户")
                all_configs.extend(configs)
        except Exception as e:
            print(f"  ✗ {os.path.basename(config_file)}: 加载失败 - {e}")

    return all_configs


def main():
    # 处理命令行参数
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == 'stop':
            DaemonProcess.stop_daemon()
            return
        elif cmd == 'status':
            DaemonProcess.status()
            return
        elif cmd == 'log':
            # 实时查看日志
            log_file = DaemonProcess.LOG_FILE
            if os.path.exists(log_file):
                print(f"实时查看日志 (Ctrl+C 退出):\n")
                os.system(f"tail -f {log_file}")
            else:
                print("日志文件不存在")
            return
        elif cmd in ['help', '-h', '--help']:
            print("用法: python trade.py [命令] [配置路径]")
            print()
            print("命令:")
            print("  (无)      交互式启动")
            print("  stop      停止后台守护进程")
            print("  status    查看守护进程状态")
            print("  log       实时查看日志")
            print("  help      显示帮助信息")
            print()
            print("配置路径:")
            print("  可以是文件路径或目录路径")
            print("  - 文件: 直接加载该配置文件")
            print("  - 目录: 加载目录下所有 .txt/.conf/.cfg 文件")
            print()
            print("示例:")
            print("  python trade.py                    # 交互式输入配置路径")
            print("  python trade.py ./configs          # 加载 configs 目录下所有配置")
            print("  python trade.py trader_configs.txt # 加载指定配置文件")
            return

    try:
        # 支持命令行直接传入配置路径
        config_path = None
        if len(sys.argv) > 1 and sys.argv[1] not in ['stop', 'status', 'log', 'help', '-h', '--help']:
            config_path = sys.argv[1]

        if not config_path:
            config_path = input(
                "请输入配置文件或目录路径 (默认: trader_configs.txt): ").strip()
        if not config_path:
            config_path = "trader_configs.txt"

        # 判断是文件还是目录
        if os.path.isdir(config_path):
            # 目录模式：加载目录下所有配置文件
            configs = load_configs_from_directory(config_path)
        elif os.path.isfile(config_path):
            # 文件模式：加载单个配置文件
            configs = load_configs(config_path)
        else:
            print(f"✗ 路径不存在: {config_path}")
            return

        if not configs:
            print(f"✗ 未加载到任何账户配置")
            return

        print(f"\n✓ 总共加载了 {len(configs)} 个账户配置")

        trader = OpinionSDKTrader(configs)
        trader.run_trading_session()

    except KeyboardInterrupt:
        print(f"\n\n✓ 用户中断，程序退出")
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
