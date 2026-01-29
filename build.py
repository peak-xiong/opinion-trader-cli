#!/usr/bin/env python3
"""
Opinion Trader CLI 打包脚本

使用 PyInstaller 将应用打包为独立可执行文件
支持 Windows、macOS、Linux

用法:
    python build.py          # 打包当前平台
    python build.py --clean  # 清理构建目录后打包
    python build.py --onedir # 使用 onedir 模式（默认 onefile）
"""
import os
import sys
import shutil
import platform
import subprocess
import argparse
from pathlib import Path


# 项目信息
APP_NAME = "opinion-trader"
APP_VERSION = "3.0.0"

# 打包配置
HIDDEN_IMPORTS = [
    # 项目模块
    "opinion_trader",
    "opinion_trader.app",
    "opinion_trader.core.trader",
    "opinion_trader.core.enhanced",
    "opinion_trader.config.models",
    "opinion_trader.config.loader",
    "opinion_trader.services.services",
    "opinion_trader.services.orderbook_manager",
    "opinion_trader.display.display",
    "opinion_trader.websocket.client",
    "opinion_trader.utils.daemon",
    "opinion_trader.utils.confirmation",
    "opinion_trader.utils.helpers",
    # SDK 和依赖
    "opinion_clob_sdk",
    "opinion_clob_sdk.chain",
    "opinion_clob_sdk.chain.py_order_utils",
    "opinion_clob_sdk.chain.py_order_utils.model",
    "httpx",
    "httpx._transports",
    "httpx._transports.default",
    "pydantic",
    "websockets",
    "websockets.client",
    "requests",
    "socks",
    "sockshandler",
    "json",
    "asyncio",
    "concurrent.futures",
]

# 排除的模块（减小体积）
EXCLUDES = [
    "tkinter",
    "unittest",
    "test",
    "tests",
    "pytest",
    "setuptools",
    "pip",
    "wheel",
]


def get_platform_info():
    """获取当前平台信息"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        platform_name = "macos"
    elif system == "windows":
        platform_name = "windows"
    else:
        platform_name = "linux"

    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine

    return platform_name, arch


def clean_build_dirs():
    """清理构建目录"""
    dirs_to_clean = ["build", "dist", "__pycache__"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"  清理 {dir_name}/")
            shutil.rmtree(dir_name)


def check_pyinstaller():
    """检查 PyInstaller 是否安装"""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} 已安装")
        return True
    except ImportError:
        print("✗ PyInstaller 未安装")
        print("  请运行: pip install pyinstaller")
        return False


def create_entry_script():
    """创建入口脚本"""
    entry_script = "__entry__.py"
    content = '''#!/usr/bin/env python3
"""PyInstaller 入口脚本"""
import sys
import os

# 确保当前目录在路径中
if getattr(sys, 'frozen', False):
    # 打包后的环境
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

os.chdir(app_dir)

from opinion_trader.app import cli
cli()
'''
    with open(entry_script, 'w', encoding='utf-8') as f:
        f.write(content)
    return entry_script


def build_executable(onedir=False):
    """构建可执行文件"""
    platform_name, arch = get_platform_info()
    print(f"\n平台: {platform_name}-{arch}")

    # 创建入口脚本
    entry_script = create_entry_script()

    # 输出文件名
    if platform_name == "windows":
        exe_suffix = ".exe"
    else:
        exe_suffix = ""

    output_name = f"{APP_NAME}-{APP_VERSION}-{platform_name}-{arch}{exe_suffix}"

    # 构建 PyInstaller 命令
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--name", APP_NAME,
        "--clean",
        "--noconfirm",
    ]

    # 模式: onefile 或 onedir
    if onedir:
        cmd.append("--onedir")
    else:
        cmd.append("--onefile")

    # 控制台应用
    cmd.append("--console")

    # 添加 src 目录到路径
    cmd.extend(["--paths", "src"])

    # 隐藏导入
    for module in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", module])

    # 排除模块
    for module in EXCLUDES:
        cmd.extend(["--exclude-module", module])

    # 收集 opinion_trader 包的所有数据
    cmd.extend(["--collect-all", "opinion_trader"])
    cmd.extend(["--collect-all", "opinion_clob_sdk"])

    # 主脚本
    cmd.append(entry_script)

    print(f"\n执行: {' '.join(cmd[:10])}...")
    print("-" * 60)

    # 执行打包
    result = subprocess.run(cmd)

    # 清理入口脚本
    if os.path.exists(entry_script):
        os.remove(entry_script)

    if result.returncode != 0:
        print(f"\n✗ 打包失败 (exit code: {result.returncode})")
        return False

    # 重命名输出文件
    if onedir:
        src_path = Path("dist") / APP_NAME
        dst_path = Path("dist") / f"{APP_NAME}-{APP_VERSION}-{platform_name}-{arch}"
    else:
        src_path = Path("dist") / (APP_NAME + exe_suffix)
        dst_path = Path("dist") / output_name

    if src_path.exists() and src_path != dst_path:
        if dst_path.exists():
            if dst_path.is_dir():
                shutil.rmtree(dst_path)
            else:
                dst_path.unlink()
        src_path.rename(dst_path)
        print(f"\n✓ 输出: dist/{dst_path.name}")
    else:
        print(f"\n✓ 输出: dist/{src_path.name}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Opinion Trader CLI 打包脚本")
    parser.add_argument("--clean", action="store_true", help="打包前清理构建目录")
    parser.add_argument("--onedir", action="store_true",
                        help="使用 onedir 模式（默认 onefile）")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Opinion Trader CLI 打包工具 v{APP_VERSION}")
    print("=" * 60)

    # 确保在项目根目录
    if not os.path.exists("src/opinion_trader"):
        print("✗ 请在项目根目录运行此脚本")
        sys.exit(1)

    # 检查 PyInstaller
    if not check_pyinstaller():
        print("\n安装 PyInstaller:")
        print("  pip install pyinstaller")
        sys.exit(1)

    # 清理
    if args.clean:
        print("\n清理构建目录...")
        clean_build_dirs()

    # 打包
    print("\n开始打包...")
    success = build_executable(onedir=args.onedir)

    if success:
        print("\n" + "=" * 60)
        print("✓ 打包完成！")
        print("=" * 60)

        # 显示使用说明
        platform_name, _ = get_platform_info()
        if platform_name == "windows":
            print("\n使用方法:")
            print("  1. 将 dist/ 目录下的 .exe 文件复制到目标机器")
            print("  2. 在同一目录创建 trader_configs.txt 配置文件")
            print("  3. 双击运行或在命令行执行")
        else:
            print("\n使用方法:")
            print("  1. 将 dist/ 目录下的可执行文件复制到目标机器")
            print("  2. 赋予执行权限: chmod +x opinion-trader-*")
            print("  3. 在同一目录创建 trader_configs.txt 配置文件")
            print("  4. 运行: ./opinion-trader-*")

        print("\n跨平台打包说明:")
        print("  - macOS 版本需要在 macOS 上打包")
        print("  - Windows 版本需要在 Windows 上打包")
        print("  - Linux 版本需要在 Linux 上打包")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
