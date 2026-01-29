"""
账户迭代器模块 - 统一处理多账户操作
"""
from typing import List, Callable, Any, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from opinion_trader.display.progress import ProgressBar


class AccountIterator:
    """账户迭代器 - 统一处理多账户操作"""

    def __init__(self, configs: list, clients: list):
        """
        Args:
            configs: TraderConfig列表
            clients: Client列表
        """
        self.configs = configs
        self.clients = clients

    def iterate(
        self,
        selected_indices: List[int],
        callback: Callable[[int, Any, Any], Any],
        show_progress: bool = True,
        progress_prefix: str = '处理账户'
    ) -> dict:
        """遍历选中的账户执行操作

        Args:
            selected_indices: 账户索引列表 [1, 2, 3, ...] (1-based)
            callback: 回调函数 func(acc_idx, client, config) -> result
            show_progress: 是否显示进度
            progress_prefix: 进度条前缀

        Returns:
            {acc_idx: result, ...}
        """
        results = {}
        total = len(selected_indices)
        errors = []

        for i, acc_idx in enumerate(selected_indices):
            if acc_idx < 1 or acc_idx > len(self.configs):
                continue

            config = self.configs[acc_idx - 1]
            client = self.clients[acc_idx - 1]

            if show_progress:
                ProgressBar.show_progress(
                    i, total, prefix=progress_prefix, suffix=config.remark)

            try:
                results[acc_idx] = callback(acc_idx, client, config)
            except Exception as e:
                results[acc_idx] = {'error': str(e)}
                errors.append((config.remark, str(e)))

        if show_progress:
            ProgressBar.show_progress(
                total, total, prefix=progress_prefix, suffix='完成')

        # 显示错误
        for remark, error in errors:
            print(f"  [!] [{remark}] 异常: {error}")

        return results

    def iterate_all(
        self,
        callback: Callable[[int, Any, Any], Any],
        show_progress: bool = True,
        progress_prefix: str = '处理账户'
    ) -> dict:
        """遍历所有账户"""
        all_indices = list(range(1, len(self.configs) + 1))
        return self.iterate(all_indices, callback, show_progress, progress_prefix)

    def iterate_parallel(
        self,
        selected_indices: List[int],
        callback: Callable[[int, Any, Any], Any],
        max_workers: int = 5,
        show_progress: bool = True
    ) -> dict:
        """并行遍历账户 (使用线程池)

        Args:
            selected_indices: 账户索引列表
            callback: 回调函数 func(acc_idx, client, config) -> result
            max_workers: 最大并发数
            show_progress: 是否显示进度

        Returns:
            {acc_idx: result, ...}
        """
        results = {}
        total = len(selected_indices)
        completed = 0

        def worker(acc_idx):
            config = self.configs[acc_idx - 1]
            client = self.clients[acc_idx - 1]
            return acc_idx, callback(acc_idx, client, config)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker, idx): idx for idx in selected_indices
                       if 1 <= idx <= len(self.configs)}

            for future in as_completed(futures):
                try:
                    acc_idx, result = future.result()
                    results[acc_idx] = result
                except Exception as e:
                    acc_idx = futures[future]
                    results[acc_idx] = {'error': str(e)}

                completed += 1
                if show_progress:
                    ProgressBar.show_progress(completed, total, prefix='并行处理')

        return results

    def get_balances(
        self,
        selected_indices: List[int],
        get_balance_func: Callable[[Any], float],
        show_progress: bool = True
    ) -> dict:
        """获取多个账户余额

        Args:
            selected_indices: 账户索引列表
            get_balance_func: 获取余额函数 func(config) -> float

        Returns:
            {acc_idx: balance, ...}
        """
        def callback(acc_idx, client, config):
            return get_balance_func(config)

        return self.iterate(selected_indices, callback, show_progress, '查询余额')

    def filter_by_balance(
        self,
        selected_indices: List[int],
        get_balance_func: Callable[[Any], float],
        min_balance: float
    ) -> Tuple[List[int], List[Tuple[str, float, float]]]:
        """按余额筛选账户

        Returns:
            (sufficient_indices, insufficient_list)
            sufficient_indices: 余额充足的账户索引列表
            insufficient_list: [(remark, balance, required), ...]
        """
        balances = self.get_balances(selected_indices, get_balance_func)

        sufficient = []
        insufficient = []

        for acc_idx in selected_indices:
            config = self.configs[acc_idx - 1]
            balance = balances.get(acc_idx, 0)

            if isinstance(balance, dict) and 'error' in balance:
                insufficient.append((config.remark, 0, min_balance))
            elif balance >= min_balance:
                sufficient.append(acc_idx)
            else:
                insufficient.append((config.remark, balance, min_balance))

        return sufficient, insufficient
