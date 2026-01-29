"""
订单构建器模块 - 统一创建和执行订单
"""
import time
from typing import Optional, Callable


class OrderBuilder:
    """订单构建器 - 统一创建和执行订单"""

    @staticmethod
    def create_limit_buy(token_id: str, price: float, shares: int, reduce_only: bool = False):
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
    def create_limit_sell(token_id: str, price: float, shares: int, reduce_only: bool = False):
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
    def create_order(
        token_id: str,
        price: float,
        shares: int,
        side: str,
        order_type: str = 'limit',
        reduce_only: bool = False
    ):
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
    def execute(
        client,
        order,
        translate_error_func: Optional[Callable[[str], str]] = None,
        remark: str = ''
    ) -> dict:
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
    def execute_with_retry(
        client,
        order,
        max_retries: int = 2,
        translate_error_func: Optional[Callable[[str], str]] = None,
        remark: str = ''
    ) -> dict:
        """带重试的订单执行

        Args:
            client: SDK客户端
            order: 订单对象
            max_retries: 最大重试次数
            translate_error_func: 错误翻译函数
            remark: 账户备注
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
