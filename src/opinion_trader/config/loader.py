"""
配置加载模块

负责从配置文件加载账户配置，支持代理地址缓存
"""
import os
import re
import json
from typing import List, Optional

import requests

from opinion_trader.config.models import TraderConfig


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
    except Exception:
        return None


def parse_config_line(line: str) -> List[str]:
    """解析配置行，支持多种分隔符（|、空格、Tab）混合使用

    Returns:
        解析后的字段列表
    """
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

    Args:
        config_file: 配置文件路径

    Returns:
        TraderConfig 列表
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
                print(f"[!] 警告: 第{line_num}行格式不正确，已跳过 (只有{len(parts)}个字段)")
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

    Args:
        config_dir: 配置文件目录

    Returns:
        TraderConfig 列表
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
