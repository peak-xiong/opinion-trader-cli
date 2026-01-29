"""
用户确认交互模块 - 统一处理用户输入确认
"""
from typing import List, Tuple, Optional, Set, Union


class UserConfirmation:
    """用户确认交互模块 - 统一处理用户输入确认"""

    @staticmethod
    def yes_no(prompt: str, default: bool = False) -> bool:
        """简单是/否确认

        Args:
            prompt: 提示语
            default: 默认值 (直接回车时使用)

        Returns:
            bool: 用户确认结果
        """
        suffix = "(Y/n)" if default else "(y/N)"
        response = input(f"{prompt} {suffix}: ").strip().lower()
        if not response:
            return default
        return response in ('y', 'yes', '是')

    @staticmethod
    def confirm_keyword(prompt: str, keyword: str = 'yes') -> bool:
        """关键词确认 (需要输入特定词如 'yes' 或 'done')

        Args:
            prompt: 提示语
            keyword: 需要输入的关键词

        Returns:
            bool: 是否输入了正确关键词
        """
        response = input(f"{prompt}: ").strip().lower()
        return response == keyword.lower()

    @staticmethod
    def continue_or_abort(warning_msg: str, show_warning: bool = True) -> bool:
        """警告后询问是否继续

        Args:
            warning_msg: 警告消息
            show_warning: 是否显示警告前缀

        Returns:
            bool: 是否继续
        """
        if show_warning:
            print(f"\n[!] {warning_msg}")
        return UserConfirmation.yes_no("是否继续?")

    @staticmethod
    def select_option(title: str, options: list, allow_cancel: bool = True) -> int:
        """多选项选择

        Args:
            title: 标题
            options: 选项列表 [(label, description), ...] 或 [label, ...]
            allow_cancel: 是否允许取消(留空返回)

        Returns:
            int: 选择的索引 (1-based), 0表示取消
        """
        print(f"\n{title}")
        for i, opt in enumerate(options, 1):
            if isinstance(opt, tuple):
                label, desc = opt
                print(f"  [{i}] {label} - {desc}")
            else:
                print(f"  [{i}] {opt}")

        cancel_hint = " (留空返回)" if allow_cancel else ""
        while True:
            choice = input(f"\n请选择{cancel_hint}: ").strip()
            if not choice:
                if allow_cancel:
                    return 0
                print("  请输入有效选项")
                continue
            try:
                idx = int(choice)
                if 1 <= idx <= len(options):
                    return idx
            except ValueError:
                pass
            print("  无效输入，请重新选择")

    @staticmethod
    def confirm_with_summary(title: str, items: List[Tuple[str, str]], keyword: str = 'done') -> bool:
        """显示摘要后确认

        Args:
            title: 标题
            items: 摘要项 [(label, value), ...]
            keyword: 确认关键词

        Returns:
            bool: 是否确认
        """
        print(f"\n{title}")
        print("-" * 40)
        for label, value in items:
            print(f"  {label}: {value}")
        print("-" * 40)
        return UserConfirmation.confirm_keyword(f"确认无误请输入 '{keyword}'", keyword)

    @staticmethod
    def handle_insufficient_balance_choice(insufficient_list: list) -> Tuple[str, Optional[Set[str]]]:
        """处理余额不足的选择

        Args:
            insufficient_list: [(remark, balance, required), ...] 或 [(idx, remark, balance, required), ...]

        Returns:
            (action, skip_remarks)
            action: 'continue'/'skip'/'cancel'
            skip_remarks: 需跳过的账户备注集合
        """
        if not insufficient_list:
            return ('continue', None)

        print(f"\n[!] 余额不足警告:")
        for item in insufficient_list:
            if len(item) == 3:
                remark, balance, required = item
            else:
                _, remark, balance, required = item
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")

        options = [
            ("继续", "忽略警告继续执行"),
            ("跳过", "跳过余额不足的账户"),
            ("停止", "取消操作")
        ]
        choice = UserConfirmation.select_option(
            "请选择操作", options, allow_cancel=False)

        if choice == 1:
            return ('continue', None)
        elif choice == 2:
            skip_remarks = set()
            for item in insufficient_list:
                remark = item[0] if len(item) == 3 else item[1]
                skip_remarks.add(remark)
            return ('skip', skip_remarks)
        else:
            return ('cancel', None)


def handle_insufficient_balance(insufficient_accounts: list) -> Tuple[str, Optional[Set[str]]]:
    """处理余额不足的账户（便捷函数）

    Args:
        insufficient_accounts: [(idx, remark, balance, required), ...] 或 [(remark, balance, required), ...] 

    Returns:
        (action, skip_remarks)
        action: 'continue' 继续执行, 'skip' 跳过不足账户, 'cancel' 取消
        skip_remarks: 需要跳过的账户备注集合（仅当action='skip'时有效）
    """
    if not insufficient_accounts:
        return ('continue', None)

    print(f"\n[!] 余额不足警告:")
    for item in insufficient_accounts:
        if len(item) == 3:
            remark, balance, required = item
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")
        elif len(item) == 4:
            _, remark, balance, required = item
            print(f"   [{remark}] 余额${balance:.2f} < 需要${required:.2f}")

    print(f"\n请选择操作:")
    print(f"  [1] 继续 - 忽略警告继续执行")
    print(f"  [2] 跳过 - 跳过余额不足的账户，仅使用余额充足的账户")
    print(f"  [3] 停止 - 取消操作")

    while True:
        choice = input("\n请选择 (1/2/3): ").strip()
        if choice == '1':
            return ('continue', None)
        elif choice == '2':
            # 获取需要跳过的账户备注列表
            skip_remarks = set()
            for item in insufficient_accounts:
                if len(item) == 3:
                    remark, _, _ = item
                elif len(item) == 4:
                    _, remark, _, _ = item
                skip_remarks.add(remark)
            return ('skip', skip_remarks)
        elif choice == '3':
            return ('cancel', None)
        else:
            print("  无效输入，请输入 1、2 或 3")
