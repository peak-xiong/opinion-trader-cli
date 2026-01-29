# 钱包工具 - 助记词转 EVM 地址

批量将 BIP39 助记词转换为 EVM (以太坊/BSC) 钱包地址和私钥。

## 功能

- 读取助记词文件 (`wallet.txt`)
- 使用标准 BIP44 派生路径: `m/44'/60'/0'/0/0`
- 输出 EVM 地址和私钥到 `evm_result.txt`

## 使用方法

### 1. 安装依赖

```bash
pip install bip-utils
```

### 2. 准备助记词

编辑 `wallet.txt`，每行一个助记词（12个单词，空格分隔）：

```
word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12
word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12
```

### 3. 运行

```bash
python wallet.py
```

### 4. 查看结果

生成的 `evm_result.txt` 格式：

```
地址|私钥
0x742d35Cc6634C0532925a3b844Bc454e4438f44e|0x1234...abcd
0xabc123...|0x5678...efgh
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `wallet.py` | 主程序 |
| `wallet.txt` | 输入文件 - 助记词（每行一个） |
| `evm_result.txt` | 输出文件 - 地址和私钥 |

## 安全提示

1. **私钥安全**: 生成的私钥文件包含敏感信息，请妥善保管
2. **助记词安全**: 助记词文件使用后建议删除或加密存储
3. **离线使用**: 建议在离线环境下运行此工具
4. **不要分享**: 切勿将包含真实助记词或私钥的文件上传或分享

## 技术说明

- 派生路径: `m/44'/60'/0'/0/0` (以太坊标准路径)
- 支持 BIP39 标准助记词（12/24 词）
- 输出地址为 EIP-55 校验和格式
- 私钥为 0x 前缀的 64 位十六进制字符串
