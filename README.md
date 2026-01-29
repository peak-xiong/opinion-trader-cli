# Opinion Trader CLI

Opinion.trade 自动交易程序 - 一个功能完整的预测市场交易工具。

## 功能特性

- **多账户管理** - 支持批量导入和管理多个交易账户
- **多种交易模式** - 批量买入/卖出、做市商、分层挂单、网格交易
- **实时数据** - WebSocket 实时订单簿和价格更新
- **智能订单** - 自动拆单、滑点控制、余额检查
- **后台运行** - 支持守护进程模式

## 项目结构

```
opinion-trader-cli/
├── src/
│   └── opinion_trader/          # 主要代码包
│       ├── config/              # 配置管理
│       ├── core/                # 核心交易逻辑
│       ├── display/             # 终端显示
│       ├── services/            # 业务服务
│       ├── utils/               # 工具函数
│       ├── wallet/              # 钱包工具
│       └── websocket/           # WebSocket 客户端
├── scripts/                     # Shell 脚本
├── docs/                        # 文档
├── archive/                     # 旧版代码存档
├── pyproject.toml              # 项目配置
├── requirements.txt            # 依赖列表
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
# 使用 pip
pip install -e .

# 或使用 uv (推荐)
uv sync
```

### 2. 配置账户

创建 `trader_configs.txt` 文件，格式如下：

```
备注名,私钥,API_KEY
账户1,0x...,your_api_key
账户2,0x...,your_api_key
```

### 3. 运行程序

```bash
# 方式1: 使用命令行工具
opinion-trader

# 方式2: 使用 Python 模块
python -m opinion_trader

# 方式3: 使用脚本
./scripts/run.sh
```

## 命令行选项

```bash
opinion-trader              # 启动交互式程序
opinion-trader daemon       # 后台守护进程模式
opinion-trader stop         # 停止守护进程
opinion-trader status       # 查看运行状态
opinion-trader --help       # 显示帮助
opinion-trader --version    # 显示版本
```

## 交易模式

1. **批量交易** - 多账户同时买入/卖出
2. **做市商模式** - 自动挂买卖单赚取价差
3. **分层挂单** - 按价格区间分批挂单
4. **网格交易** - 自动在价格区间内网格交易
5. **合并/拆分** - Token 份额的合并和拆分

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 代码格式化
black src/
isort src/

# 类型检查
mypy src/
```

## 打包

```bash
# 安装打包依赖
pip install -e ".[build]"

# 打包为可执行文件
python build.py
```

## 注意事项

- 请妥善保管私钥和 API Key，不要提交到版本控制
- `trader_configs.txt` 已被 `.gitignore` 排除
- 交易有风险，请谨慎操作

## License

MIT License
