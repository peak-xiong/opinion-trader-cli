"""
市场信息服务模块 - 获取市场详情和列表
"""
import time
import threading
from datetime import datetime
from typing import Optional, Callable, List

import requests

from opinion_trader.services.orderbook import OrderbookService


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
    def get_all_child_markets_info(client, parent_market_id: int, include_prices: bool = False) -> dict:
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


class MarketListService:
    """市场列表服务 - 后台获取和缓存市场列表 (SSOT: Single Source of Truth)

    所有市场数据的读写都必须通过此服务，确保数据一致性。
    支持：
    - 程序启动时自动加载
    - 后台定期自动刷新
    - 线程安全的读写操作
    """

    _markets_cache: List[dict] = []  # 市场列表缓存
    _cache_time: float = 0  # 缓存时间
    _loading: bool = False  # 是否正在加载
    _loaded: bool = False  # 是否已加载完成
    _lock = threading.Lock()  # 读写锁

    # 后台刷新相关
    _client = None  # SDK客户端引用
    _auto_refresh_enabled: bool = False  # 是否启用自动刷新
    _refresh_interval: int = 60  # 刷新间隔（秒）
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
    def start_background_fetch(cls, client, callback: Optional[Callable[[List[dict]], None]] = None):
        """启动后台线程获取市场列表（兼容旧接口）

        Args:
            client: SDK客户端
            callback: 加载完成后的回调函数（已废弃，保留兼容）
        """
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
            except Exception:
                pass  # 静默失败
            finally:
                with cls._lock:
                    cls._loading = False

        thread = threading.Thread(target=fetch_markets, daemon=True)
        thread.start()

    @classmethod
    def _fetch_all_markets(cls, client, limit: int = 50) -> List[dict]:
        """获取所有活跃市场并按到期时间排序

        优先使用 SDK 的 get_markets 方法，失败时回退到 HTTP API
        """
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
    def get_cached_markets(cls) -> List[dict]:
        """获取缓存的市场列表（线程安全）"""
        with cls._lock:
            return cls._markets_cache.copy()  # 返回副本避免外部修改

    @classmethod
    def get_market_by_id(cls, market_id: int) -> Optional[dict]:
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
    def search_markets(cls, keyword: str) -> List[dict]:
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
