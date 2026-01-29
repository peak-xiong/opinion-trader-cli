"""
持仓服务模块 - 统一获取和处理持仓
"""
import time
from typing import Optional, Tuple, List

from opinion_trader.display.position import PositionDisplay


class PositionService:
    """持仓服务模块 - 统一获取和处理持仓"""

    @staticmethod
    def get_positions(client, market_id: int = 0, token_id: Optional[str] = None) -> List[dict]:
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
    def get_position_by_token(client, token_id: str) -> Optional[dict]:
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
    def wait_for_position_update(
        client,
        token_id: str,
        initial_balance: int,
        expected_direction: str,
        timeout: int = 10,
        check_interval: float = 1.0
    ) -> Tuple[bool, int]:
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
