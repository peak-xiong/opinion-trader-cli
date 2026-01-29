from bip_utils import (
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes
)

INPUT_FILE = "wallet.txt"
OUTPUT_FILE = "evm_result.txt"

def mnemonic_to_evm(mnemonic: str):
    # 生成种子
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()

    # EVM 使用 BIP44 ETH 路径: m/44'/60'/0'/0/0
    bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.ETHEREUM)
    account = (
        bip44_ctx
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )

    private_key = "0x" + account.PrivateKey().Raw().ToHex()
    address = account.PublicKey().ToAddress()

    return address, private_key


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        mnemonics = [line.strip() for line in f if line.strip()]

    results = []

    for mnemonic in mnemonics:
        try:
            address, private_key = mnemonic_to_evm(mnemonic)
            results.append(f"{address}|{private_key}")
        except Exception as e:
            print(f"助记词解析失败: {mnemonic[:10]}... 错误: {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(results))

    print(f"完成，共生成 {len(results)} 条，已保存到 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()