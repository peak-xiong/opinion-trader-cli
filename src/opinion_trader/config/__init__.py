"""
配置管理模块

包含配置模型和配置加载功能
"""

from opinion_trader.config.models import (
    TraderConfig,
    MarketMakerConfig,
    MarketMakerState,
)

# 尝试导入 loader 模块（可能依赖 requests）
try:
    from opinion_trader.config.loader import (
        load_configs,
        parse_config_line,
        fetch_proxy_address,
        load_proxy_cache,
        save_proxy_cache,
    )
    _LOADER_AVAILABLE = True
except ImportError:
    # requests 未安装时，loader 功能不可用
    load_configs = None
    parse_config_line = None
    fetch_proxy_address = None
    load_proxy_cache = None
    save_proxy_cache = None
    _LOADER_AVAILABLE = False

__all__ = [
    "TraderConfig",
    "MarketMakerConfig",
    "MarketMakerState",
    "load_configs",
    "parse_config_line",
    "fetch_proxy_address",
    "load_proxy_cache",
    "save_proxy_cache",
]
