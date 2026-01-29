"""
Opinion Trader CLI 应用主入口

提供统一的应用启动入口和命令行接口
"""
import sys
import os

# 确保项目根目录在 Python 路径中
_project_root = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main():
    """应用主入口函数"""
    # 导入原始的 trade.py 并运行
    # 这是临时方案，保证功能正常运行
    try:
        from trade import main as trade_main
        trade_main()
    except ImportError as e:
        print(f"✗ 无法启动应用: {e}")
        print("  请确保在项目根目录运行")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n已退出")
        sys.exit(0)


def run_daemon():
    """以守护进程模式运行"""
    from opinion_trader.utils.daemon import DaemonProcess
    DaemonProcess.daemonize()
    main()


def stop_daemon():
    """停止守护进程"""
    from opinion_trader.utils.daemon import DaemonProcess
    DaemonProcess.stop_daemon()


def daemon_status():
    """查看守护进程状态"""
    from opinion_trader.utils.daemon import DaemonProcess
    DaemonProcess.status()


def cli():
    """命令行入口，处理子命令"""
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == 'daemon':
            run_daemon()
        elif cmd == 'stop':
            stop_daemon()
        elif cmd == 'status':
            daemon_status()
        elif cmd in ('--help', '-h', 'help'):
            print_help()
        elif cmd in ('--version', '-v'):
            print_version()
        else:
            # 未知命令，直接运行主程序
            main()
    else:
        # 没有参数，直接运行主程序
        main()


def print_help():
    """打印帮助信息"""
    print("""
Opinion Trader CLI - Opinion.trade 自动交易程序

用法:
  opinion-trader          启动交互式交易程序
  opinion-trader daemon   以守护进程模式运行
  opinion-trader stop     停止守护进程
  opinion-trader status   查看守护进程状态
  opinion-trader --help   显示此帮助信息
  opinion-trader --version 显示版本信息

快速开始:
  1. 配置账户信息到 trader_configs.txt
  2. 运行 opinion-trader 启动程序
  3. 选择市场和交易模式

更多信息请参阅: docs/使用说明.md
""")


def print_version():
    """打印版本信息"""
    from opinion_trader import __version__
    print(f"Opinion Trader CLI v{__version__}")


if __name__ == "__main__":
    cli()
