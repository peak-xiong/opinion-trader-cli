"""
进度条和动画显示工具
"""
import sys
import time
import threading


class ProgressBar:
    """进度条/动画显示工具"""

    @staticmethod
    def show_spinner(message: str, stop_event: threading.Event):
        """显示旋转动画（在后台线程运行）

        Args:
            message: 显示的消息
            stop_event: 停止事件
        """
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        idx = 0
        while not stop_event.is_set():
            sys.stdout.write(f'\r{spinner_chars[idx]} {message}')
            sys.stdout.flush()
            idx = (idx + 1) % len(spinner_chars)
            time.sleep(0.1)
        # 清除spinner行
        sys.stdout.write('\r' + ' ' * (len(message) + 4) + '\r')
        sys.stdout.flush()

    @staticmethod
    def show_progress(
        current: int,
        total: int,
        prefix: str = '',
        suffix: str = '',
        bar_length: int = 30
    ):
        """显示进度条

        Args:
            current: 当前进度
            total: 总数
            prefix: 前缀文本
            suffix: 后缀文本
            bar_length: 进度条长度
        """
        if total == 0:
            percent = 100
        else:
            percent = current / total * 100
        filled = int(bar_length * current / total) if total > 0 else bar_length
        bar = '█' * filled + '░' * (bar_length - filled)
        sys.stdout.write(
            f'\r{prefix} [{bar}] {percent:.0f}% ({current}/{total}) {suffix}')
        sys.stdout.flush()
        if current >= total:
            print()  # 完成时换行

    @staticmethod
    def clear_line():
        """清除当前行"""
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()
