# Opinion.trade SDK - 开发文档

> 版本: v2.4.9 | 最后更新: 2026-01-13

## 目录

- [架构概述](#架构概述)
- [模块说明](#模块说明)
- [核心类](#核心类)
- [关键函数](#关键函数)
- [数据流](#数据流)
- [扩展开发](#扩展开发)
- [调试技巧](#调试技巧)

---

## 架构概述

### 目录结构

```
opinion/sdk/auto/
├── trade.py              # 主程序入口 (~10500行)
│   ├── DaemonProcess     # 守护进程管理
│   ├── OpinionSDKTrader  # 主交易类
│   └── load_configs()    # 配置加载
├── models.py             # 数据模型定义
│   ├── TraderConfig      # 账户配置
│   ├── MarketMakerConfig # 做市商配置
│   └── MarketMakerState  # 做市商状态
├── display.py            # 显示模块
├── services.py           # 服务模块
│   └── OrderbookService  # 订单簿服务
├── websocket_client.py   # WebSocket 客户端
├── docs/
│   ├── USER_GUIDE.md     # 用户手册
│   └── DEVELOPMENT.md    # 开发文档 (本文件)
└── trader_configs.txt    # 配置文件
```

### 依赖关系

```
trade.py
├── models.py (TraderConfig, MarketMakerConfig, MarketMakerState)
├── services.py (OrderbookService)
├── display.py (显示函数)
├── websocket_client.py (WebSocketClient)
└── opinion_clob_sdk (外部SDK)
    ├── Client
    ├── PlaceOrderDataInput
    ├── OrderSide
    └── ...
```

---

## 模块说明

### trade.py - 主程序

**主要职责**：
- 程序入口和主循环
- 账户管理和交易执行
- 做市商策略实现
- 用户交互界面

**关键类**：

| 类名 | 职责 |
|------|------|
| `DaemonProcess` | 守护进程管理（PID文件、启停控制） |
| `OpinionSDKTrader` | 主交易类，包含所有交易逻辑 |

**关键函数**：

| 函数 | 说明 |
|------|------|
| `load_configs()` | 加载配置文件，自动获取代理地址 |
| `parse_config_line()` | 解析配置行（支持多分隔符） |
| `fetch_proxy_address()` | 获取代理地址（带缓存） |
| `load_proxy_cache()` | 加载代理地址缓存 |
| `save_proxy_cache()` | 保存代理地址缓存 |

### models.py - 数据模型

**TraderConfig** - 账户配置

```python
class TraderConfig:
    remark: str           # 备注
    api_key: str          # API Key
    eoa_address: str      # EOA 地址
    private_key: str      # 私钥
    proxy_address: str    # 代理地址（可自动获取）
    socks5: str           # SOCKS5 代理

    def get_proxies(proxy_type='socks5') -> dict
```

**MarketMakerConfig** - 做市商配置

```python
@dataclass
class MarketMakerConfig:
    # 基础参数
    market_id: int
    token_id: str
    min_spread: float         # 最小价差阈值
    price_step: float         # 价格调整步长

    # 价格边界保护
    max_buy_price: float      # 买入上限
    min_sell_price: float     # 卖出下限
    max_price_deviation: float

    # 仓位限制
    max_position_shares: int
    max_position_amount: float
    max_position_percent: float

    # 止损参数
    stop_loss_percent: float
    stop_loss_amount: float
    stop_loss_price: float

    # 分层挂单
    layered_sell_enabled: bool
    sell_price_levels: list
    sell_distribution_mode: str  # uniform/pyramid/inverse_pyramid/custom
    sell_custom_ratios: list

    # 网格策略
    grid_enabled: bool
    grid_profit_spread: float
    grid_levels: int
    ...
```

**MarketMakerState** - 做市商运行状态

```python
@dataclass
class MarketMakerState:
    is_running: bool
    reference_mid_price: float  # 启动时参考价

    # 挂单状态
    buy_order_id: str
    sell_order_id: str
    buy_order_price: float
    sell_order_price: float

    # 交易统计
    total_buy_shares: int
    total_buy_cost: float
    total_sell_shares: int
    total_sell_revenue: float
    realized_pnl: float

    # 网格持仓追踪
    grid_positions: list
    grid_buy_orders: list
    grid_sell_orders: list
    ...
```

### services.py - 服务模块

**OrderbookService** - 订单簿服务

```python
class OrderbookService:
    @staticmethod
    def fetch(client, token_id) -> dict:
        """获取订单簿数据"""

    @staticmethod
    def get_price_at_level(ob, side, level_index) -> float:
        """获取指定档位价格"""

    @staticmethod
    def calculate_depth(ob, side, levels=5) -> tuple:
        """计算盘口深度"""
```

---

## 核心类

### OpinionSDKTrader

主交易类，包含所有交易逻辑。

#### 初始化

```python
def __init__(self, configs: List[TraderConfig]):
    self.configs = configs
    self.clients = {}      # 缓存已初始化的客户端
    self.proxy_type = None # 用户选择的代理类型
```

#### 主要方法分类

**交易执行**

| 方法 | 说明 |
|------|------|
| `run_trading_session()` | 主交易会话 |
| `_batch_trade_menu()` | 批量交易菜单 |
| `_execute_layered_order()` | 执行分层挂单 |

**做市商**

| 方法 | 说明 |
|------|------|
| `_market_maker_menu()` | 做市商入口 |
| `_mm_run_loop()` | 做市主循环 |
| `_mm_place_buy_order()` | 挂买单 |
| `_mm_place_sell_order()` | 挂卖单 |
| `_mm_place_layered_buy_orders()` | 分层买入 |
| `_mm_place_layered_sell_orders()` | 分层卖出 |

**配置和辅助**

| 方法 | 说明 |
|------|------|
| `_configure_layered_order()` | 配置分层挂单 |
| `_calculate_distribution_ratios()` | 计算分布比例 |
| `get_usdt_balance()` | 查询USDT余额 |
| `format_price()` | 格式化价格显示 |
| `translate_error()` | 翻译错误信息 |

---

## 关键函数

### 配置加载

#### parse_config_line()

解析配置行，支持 `|`、空格、Tab 混合分隔符。

```python
def parse_config_line(line: str) -> List[str]:
    """
    支持格式:
    - 101|api_key|0xEOA|0x私钥|socks5
    - 101 api_key 0xEOA 0x私钥 socks5
    - 101\tapi_key\t0xEOA|0x私钥\tsocks5
    """
    import re
    parts = line.split('|')
    result = []
    for part in parts:
        sub_parts = re.split(r'[\s\t]+', part.strip())
        result.extend([p for p in sub_parts if p])
    return result
```

#### fetch_proxy_address()

通过 API 自动获取代理地址，支持本地缓存。

```python
def fetch_proxy_address(eoa_address: str, socks5: str = None, use_cache: bool = True) -> Optional[str]:
    """
    API: https://proxy.opinion.trade:8443/api/bsc/api/v2/user/{eoa}/profile?chainId=56
    返回: result.multiSignedWalletAddress["56"]

    缓存机制:
    - 首次获取后自动保存到 proxy_cache.json
    - 下次启动时从缓存读取，无需重新请求API
    - use_cache=False 可强制从API获取
    """
```

#### 代理地址缓存

```python
PROXY_CACHE_FILE = "proxy_cache.json"

def load_proxy_cache() -> dict:
    """加载缓存 {eoa_address: proxy_address}"""

def save_proxy_cache(cache: dict):
    """保存缓存到文件"""
```

缓存文件格式：
```json
{
  "0xabc123...": "0xdef456...",
  "0x789xyz...": "0x012abc..."
}
```

#### load_configs()

加载配置文件，自动获取缺失的代理地址（优先使用缓存）。

```python
def load_configs(config_file: str) -> List[TraderConfig]:
    """
    支持格式:
    - 新格式(4-5字段): 备注 api_key EOA 私钥 [socks5]
    - 旧格式(6字段): 备注 api_key EOA 私钥 代理地址 [socks5]

    智能判断第5列:
    - 0x开头且42位 → 代理地址
    - 其他 → socks5代理

    代理地址获取流程:
    1. 检查本地缓存 (proxy_cache.json)
    2. 缓存命中 → 直接使用
    3. 缓存未命中 → 调用API获取并保存到缓存
    """
```

### 分层挂单

#### _configure_layered_order()

配置分层挂单参数。

```python
def _configure_layered_order(self, side: str, bid_details: list,
                              ask_details: list, format_price) -> Optional[dict]:
    """
    价格选择方式:
    1. 按盘口档位 (如 买1-买3-买5)
    2. 自定义价格区间 (起始价、结束价、层数)
    3. 自定义价格列表 (如 60 62 65 70，不连续)

    返回配置:
    {
        'price_mode': 'levels' | 'custom_range' | 'custom_list',
        'prices': [0.55, 0.56, 0.57],  # 小数格式，非"分"
        'distribution': 'uniform' | 'pyramid' | 'inverse_pyramid' | 'custom',
        'custom_ratios': [1, 2, 3]  # 仅当 distribution='custom'
    }

    注意: 用户输入价格单位为"分" (如 60)，内部转换为小数 (0.60)
    """
```

#### _calculate_distribution_ratios()

计算各层分配比例。

```python
def _calculate_distribution_ratios(self, price_levels: list,
                                    distribution_mode: str,
                                    custom_ratios: list) -> list:
    """
    distribution_mode:
    - 'uniform': 均分 [0.33, 0.33, 0.33]
    - 'pyramid': 金字塔 [0.17, 0.33, 0.50]
    - 'inverse_pyramid': 倒金字塔 [0.50, 0.33, 0.17]
    - 'custom': 自定义比例
    """
```

#### _execute_layered_order()

执行分层挂单。

```python
def _execute_layered_order(self, client, market_id: int, token_id: str,
                            side: str, layered_config: dict,
                            total_amount: float = None,
                            total_shares: int = None) -> dict:
    """
    返回:
    {
        'success': 3,
        'failed': 0,
        'orders': [
            {'level': 1, 'price': 55.0, 'shares': 500, 'order_id': '...'},
            ...
        ]
    }
    """
```

---

## 数据流

### 交易执行流程

```
用户选择交易模式
       ↓
选择市场和代币
       ↓
选择账户
       ↓
设置金额/数量
       ↓
选择策略 ─────────────────┐
  │                       │
  ├─ 限价单               ├─ 分层挂单
  ├─ 市价单               │    ↓
  │                       │ _configure_layered_order()
  ↓                       │    ↓
获取盘口                  │ _execute_layered_order()
  │                       │    ↓
  ↓                       │ 多笔订单执行
构建订单                  │
  │                       │
  ↓                       │
client.place_order() ←────┘
  │
  ↓
返回结果
```

### 做市商循环

```
启动做市商
    ↓
初始化状态 (MarketMakerState)
    ↓
┌─────────────────────────────────┐
│ 主循环 (_mm_run_loop)           │
│   ↓                             │
│ 获取盘口数据                    │
│   ↓                             │
│ 检查止损条件                    │
│   ↓                             │
│ 检查深度骤降                    │
│   ↓                             │
│ 检查买单是否需要调价            │
│   ├─ 是 → 撤单 → 重新挂单       │
│   └─ 否 → 保持                  │
│   ↓                             │
│ 检查卖单是否需要调价            │
│   ├─ 是 → 撤单 → 重新挂单       │
│   └─ 否 → 保持                  │
│   ↓                             │
│ 等待 check_interval 秒          │
│   ↓                             │
│ 循环继续...                     │
└─────────────────────────────────┘
```

---

## 扩展开发

### 添加新的交易模式

1. 在主菜单添加选项（`_batch_trade_menu()` 约第8647行）

```python
print("  11. 你的新模式")
```

2. 添加模式处理

```python
elif mode_choice == '11':
    self._your_new_mode_menu(...)
```

3. 实现模式逻辑

```python
def _your_new_mode_menu(self, ...):
    """你的新交易模式"""
    pass
```

### 添加新的分布模式

在 `_calculate_distribution_ratios()` 中添加：

```python
elif distribution_mode == 'your_mode':
    # 自定义分布逻辑
    weights = [...]
    total_weight = sum(weights)
    ratios = [w / total_weight for w in weights]
```

### 添加新的配置参数

1. 在 `models.py` 的 `MarketMakerConfig` 中添加字段

```python
your_new_param: float = 0.0
```

2. 在 `_market_maker_menu()` 中添加配置输入

3. 在 `_mm_run_loop()` 中使用参数

---

## 调试技巧

### 日志

```python
# 添加调试输出
print(f"[DEBUG] variable = {variable}")

# 使用后台日志
./run_background.sh
tail -f logs/*.log | grep DEBUG
```

### 测试配置加载

```bash
python3 -c "
from trade import load_configs
configs = load_configs('trader_configs.txt')
for c in configs:
    print(f'{c.remark}: EOA={c.eoa_address[:10]}..., proxy={c.proxy_address}')
"
```

### 测试 API 连接

```bash
curl -s 'https://proxy.opinion.trade:8443/api/bsc/api/v2/user/0xYOUR_EOA/profile?chainId=56' | python3 -m json.tool
```

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: opinion_clob_sdk` | SDK未安装 | 运行 `./install.sh` |
| `SSL: TLSV1_ALERT_PROTOCOL_VERSION` | Python SSL版本过旧 | 升级Python或使用服务器环境 |
| `Insufficient token balance` | 余额不足 | 检查持仓，减少卖出数量 |
| `配置文件格式不正确` | 字段数量不对 | 检查分隔符和字段数 |

---

## API 参考

### Opinion CLOB SDK

```python
from opinion_clob_sdk import Client, PlaceOrderDataInput, OrderSide

# 初始化客户端
client = Client(
    api_key=config.api_key,
    eoa_address=config.eoa_address,
    proxy_address=config.proxy_address,
    private_key=config.private_key,
    proxies=config.get_proxies()
)

# 下单
order = PlaceOrderDataInput(
    marketId=123,
    tokenId="0x...",
    side=OrderSide.BUY,  # or OrderSide.SELL
    orderType=1,         # 1=限价, 2=市价
    price="0.55",
    makerAmountInQuoteToken=10.0  # 买入金额
    # or makerAmountInBaseToken=100  # 卖出份额
)
result = client.place_order(order, check_approval=True)

# 查询持仓
positions = client.get_my_positions()

# 查询挂单
orders = client.get_my_orders()

# 撤单
client.cancel_order(order_id)
```

### 内部 API

```python
# 获取代理地址
GET https://proxy.opinion.trade:8443/api/bsc/api/v2/user/{eoa}/profile?chainId=56

# 返回
{
    "errno": 0,
    "result": {
        "multiSignedWalletAddress": {
            "56": "0x..."  # BSC链代理地址
        },
        "netWorth": "1234.56",
        "portfolio": "1000.00",
        ...
    }
}
```

---

## 更新日志

### v2.4.9 (2026-01-13)

- 优化：卖出流程避免重复查询持仓，使用缓存机制
- 优化：`_execute_sell_for_market()` 支持传入 `market_title` 和 `cached_positions` 参数

### v2.4.8 (2026-01-13)

- 新增：分层挂单第三种价格选择方式 - 自定义价格列表（支持不连续价格，如 60 62 65 70）

### v2.4.7 (2026-01-13)

- 修复：分层挂单价格格式问题，用户输入"分"（如60）正确转换为小数格式（0.60）
- 修复：盘口数据格式从 dict 改为 tuple `(档位, 价格, 数量, 累计)`

### v2.4.6 (2026-01-13)

- 修复：卖出模式恢复分层挂单选项
- 优化：查询（余额、持仓、挂单）实时显示，查到一个显示一个

### v2.4.5 (2026-01-13)

- 优化：所有查询操作实时显示结果，不再等待全部完成

### v2.4.4 (2026-01-13)

- 修复：卖出模式流程改为先查询持仓再选择账户（之前错误地查询余额）

### v2.4.3 (2026-01-13)

- 新增：代理地址缓存机制（proxy_cache.json）
- 新增：配置文件支持多分隔符（|、空格、Tab混合）

### v2.4.0 (2026-01-13)

- 新增：分层挂单功能（仅买入/仅卖出模式）
- 新增：自动获取代理地址（无需手动配置）
- 新增：开发文档和用户手册

### v2.3.0

- 做市商模式增强
- 网格策略
- 深度骤降保护
