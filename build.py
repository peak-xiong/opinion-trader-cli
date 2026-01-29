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
MAIN_SCRIPT = "trade.py"

# 打包配置
HIDDEN_IMPORTS = [
    "opinion_clob_sdk",
    "httpx",
    "pydantic",
    "websockets",
    "requests",
    "socks",
    "sockshandler",
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
]

# 需要包含的数据文件
DATAS = [
    # (源路径, 目标目录)
    # ("trader_configs.txt", "."),  # 配置文件示例
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

    # 清理 .spec 文件
    for spec_file in Path(".").glob("*.spec"):
        print(f"  删除 {spec_file}")
        spec_file.unlink()


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


def build_executable(onedir=False):
    """构建可执行文件"""
    platform_name, arch = get_platform_info()
    print(f"\n平台: {platform_name}-{arch}")

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

    # 隐藏导入
    for module in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", module])

    # 排除模块
    for module in EXCLUDES:
        cmd.extend(["--exclude-module", module])

    # 数据文件
    for src, dst in DATAS:
        if os.path.exists(src):
            cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # 主脚本
    cmd.append(MAIN_SCRIPT)

    print(f"\n执行: {' '.join(cmd)}")
    print("-" * 60)

    # 执行打包
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n✗ 打包失败 (exit code: {result.returncode})")
        return False

    # 重命名输出文件
    if onedir:
        src_path = Path("dist") / APP_NAME
        dst_path = Path("dist") / \
            f"{APP_NAME}-{APP_VERSION}-{platform_name}-{arch}"
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

    # 检查主脚本
    if not os.path.exists(MAIN_SCRIPT):
        print(f"✗ 找不到主脚本: {MAIN_SCRIPT}")
        sys.exit(1)

    # 检查 PyInstaller
    if not check_pyinstaller():
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
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
