#!/usr/bin/env python3
"""
Opinion Trader CLI Build Script

Build standalone executables using PyInstaller
Supports Windows, macOS, Linux

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build directories first
    python build.py --onedir # Use onedir mode (default: onefile)
"""
import os
import sys
import shutil
import platform
import subprocess
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Project info
APP_NAME = "opinion-trader"
APP_VERSION = "3.0.0"

# Build config
HIDDEN_IMPORTS = [
    # Project modules
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
    # SDK and dependencies
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

# Exclude modules (reduce size)
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
    """Get current platform info"""
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
    """Clean build directories"""
    dirs_to_clean = ["build", "dist", "__pycache__"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"  Cleaning {dir_name}/")
            shutil.rmtree(dir_name)


def check_pyinstaller():
    """Check if PyInstaller is installed"""
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__} installed")
        return True
    except ImportError:
        print("[ERROR] PyInstaller not installed")
        print("  Please run: pip install pyinstaller")
        return False


def create_entry_script():
    """Create entry script"""
    entry_script = "__entry__.py"
    content = '''#!/usr/bin/env python3
"""PyInstaller entry script"""
import sys
import os

# Ensure current directory in path
if getattr(sys, 'frozen', False):
    # Packaged environment
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
    """Build executable"""
    platform_name, arch = get_platform_info()
    print(f"\nPlatform: {platform_name}-{arch}")

    # Create entry script
    entry_script = create_entry_script()

    # Output filename
    if platform_name == "windows":
        exe_suffix = ".exe"
    else:
        exe_suffix = ""

    output_name = f"{APP_NAME}-{APP_VERSION}-{platform_name}-{arch}{exe_suffix}"

    # Build PyInstaller command
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--name", APP_NAME,
        "--clean",
        "--noconfirm",
    ]

    # Mode: onefile or onedir
    if onedir:
        cmd.append("--onedir")
    else:
        cmd.append("--onefile")

    # Console application
    cmd.append("--console")

    # Add src directory to path
    cmd.extend(["--paths", "src"])

    # Hidden imports
    for module in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", module])

    # Exclude modules
    for module in EXCLUDES:
        cmd.extend(["--exclude-module", module])

    # Collect opinion_trader package data
    cmd.extend(["--collect-all", "opinion_trader"])
    cmd.extend(["--collect-all", "opinion_clob_sdk"])
    cmd.extend(["--collect-all", "rich"])
    cmd.extend(["--collect-all", "questionary"])
    cmd.extend(["--collect-all", "prompt_toolkit"])

    # Main script
    cmd.append(entry_script)

    print(f"\nExecuting: {' '.join(cmd[:10])}...")
    print("-" * 60)

    # Execute build
    result = subprocess.run(cmd)

    # Clean entry script
    if os.path.exists(entry_script):
        os.remove(entry_script)

    if result.returncode != 0:
        print(f"\n[ERROR] Build failed (exit code: {result.returncode})")
        return False

    # Rename output file
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
        print(f"\n[OK] Output: dist/{dst_path.name}")
    else:
        print(f"\n[OK] Output: dist/{src_path.name}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Opinion Trader CLI Build Script")
    parser.add_argument("--clean", action="store_true", help="Clean build directories first")
    parser.add_argument("--onedir", action="store_true",
                        help="Use onedir mode (default: onefile)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Opinion Trader CLI Build Tool v{APP_VERSION}")
    print("=" * 60)

    # Ensure in project root
    if not os.path.exists("src/opinion_trader"):
        print("[ERROR] Please run this script from project root")
        sys.exit(1)

    # Check PyInstaller
    if not check_pyinstaller():
        print("\nInstall PyInstaller:")
        print("  pip install pyinstaller")
        sys.exit(1)

    # Clean
    if args.clean:
        print("\nCleaning build directories...")
        clean_build_dirs()

    # Build
    print("\nStarting build...")
    success = build_executable(onedir=args.onedir)

    if success:
        print("\n" + "=" * 60)
        print("[OK] Build completed!")
        print("=" * 60)

        # Show usage
        platform_name, _ = get_platform_info()
        if platform_name == "windows":
            print("\nUsage:")
            print("  1. Copy the .exe file from dist/ to target machine")
            print("  2. Create trader_configs.txt in the same directory")
            print("  3. Double-click to run or execute from command line")
        else:
            print("\nUsage:")
            print("  1. Copy the executable from dist/ to target machine")
            print("  2. Grant execute permission: chmod +x opinion-trader-*")
            print("  3. Create trader_configs.txt in the same directory")
            print("  4. Run: ./opinion-trader-*")

        print("\nCross-platform build notes:")
        print("  - macOS version must be built on macOS")
        print("  - Windows version must be built on Windows")
        print("  - Linux version must be built on Linux")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
