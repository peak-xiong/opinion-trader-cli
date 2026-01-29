"""
守护进程管理模块
"""
import os
import sys
import time
import signal
import atexit
from datetime import datetime
from typing import Tuple, Optional


class DaemonProcess:
    """守护进程管理类"""

    PID_FILE = "/tmp/opinion_trade.pid"
    LOG_FILE = "opinion_trade.log"

    @classmethod
    def is_running(cls) -> Tuple[bool, Optional[int]]:
        """检查是否有守护进程在运行

        Returns:
            (is_running, pid)
        """
        if not os.path.exists(cls.PID_FILE):
            return False, None
        try:
            with open(cls.PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # 检查进程是否存在
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            # 进程不存在或PID无效，清理过期的PID文件
            cls._remove_pid_file()
            return False, None

    @classmethod
    def _remove_pid_file(cls):
        """删除PID文件"""
        try:
            if os.path.exists(cls.PID_FILE):
                os.remove(cls.PID_FILE)
        except Exception:
            pass

    @classmethod
    def _write_pid_file(cls):
        """写入PID文件"""
        with open(cls.PID_FILE, 'w') as f:
            f.write(str(os.getpid()))

    @classmethod
    def stop_daemon(cls) -> bool:
        """停止守护进程"""
        running, pid = cls.is_running()
        if not running:
            print("没有运行中的守护进程")
            return False

        try:
            print(f"正在停止守护进程 (PID: {pid})...")
            os.kill(pid, signal.SIGTERM)
            # 等待进程结束
            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except OSError:
                    print("✓ 守护进程已停止")
                    cls._remove_pid_file()
                    return True
            # 强制杀死
            os.kill(pid, signal.SIGKILL)
            print("✓ 守护进程已强制停止")
            cls._remove_pid_file()
            return True
        except Exception as e:
            print(f"✗ 停止失败: {e}")
            return False

    @classmethod
    def status(cls):
        """显示守护进程状态"""
        running, pid = cls.is_running()
        if running:
            print(f"✓ 守护进程运行中 (PID: {pid})")
            print(f"  日志文件: {os.path.abspath(cls.LOG_FILE)}")
            # 显示最后几行日志
            if os.path.exists(cls.LOG_FILE):
                print("\n  最近日志:")
                try:
                    with open(cls.LOG_FILE, 'r') as f:
                        lines = f.readlines()
                        for line in lines[-10:]:
                            print(f"  {line.rstrip()}")
                except Exception:
                    pass
        else:
            print("✗ 没有运行中的守护进程")

    @classmethod
    def daemonize(cls):
        """将当前进程转为守护进程（双fork方式）"""
        # 检查是否已有守护进程在运行
        running, pid = cls.is_running()
        if running:
            print(f"✗ 已有守护进程在运行 (PID: {pid})")
            print(f"  使用 'python trade.py stop' 停止")
            sys.exit(1)

        # 第一次fork
        try:
            pid = os.fork()
            if pid > 0:
                # 父进程退出
                print(f"✓ 守护进程已启动")
                print(f"  日志文件: {os.path.abspath(cls.LOG_FILE)}")
                print(f"  查看状态: python trade.py status")
                print(f"  停止进程: python trade.py stop")
                sys.exit(0)
        except OSError as e:
            print(f"✗ fork失败: {e}")
            sys.exit(1)

        # 创建新会话
        os.setsid()

        # 第二次fork
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError:
            sys.exit(1)

        # 重定向标准输入输出
        sys.stdout.flush()
        sys.stderr.flush()

        # 打开日志文件和/dev/null
        try:
            dev_null = open('/dev/null', 'r+')
            log_file = open(cls.LOG_FILE, 'a', buffering=1)

            # 重定向
            os.dup2(dev_null.fileno(), 0)  # stdin
            os.dup2(log_file.fileno(), 1)  # stdout
            os.dup2(log_file.fileno(), 2)  # stderr
        except Exception:
            # 如果重定向失败，尝试继续运行
            pass

        # 写入PID文件
        cls._write_pid_file()

        # 注册退出时清理
        atexit.register(cls._remove_pid_file)

        # 处理终止信号
        def signal_handler(signum, frame):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 收到终止信号，正在退出...")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
