"""
通用表格显示模块
"""
from typing import List, Optional


class TableDisplay:
    """通用表格显示模块"""

    @staticmethod
    def print_table(
        headers: List[str],
        rows: List[List[str]],
        col_widths: Optional[List[int]] = None,
        alignments: Optional[List[str]] = None,
        title: Optional[str] = None,
        indent: int = 2
    ):
        """打印通用表格

        Args:
            headers: 表头列表 ["列1", "列2", ...]
            rows: 数据行列表 [["值1", "值2", ...], ...]
            col_widths: 列宽列表，None则自动计算
            alignments: 对齐方式列表 ["<", "^", ">"]，默认居中
            title: 表格标题
            indent: 缩进空格数
        """
        if not headers:
            return

        prefix = " " * indent
        num_cols = len(headers)

        # 自动计算列宽（如果未指定）
        if col_widths is None:
            col_widths = []
            for i, h in enumerate(headers):
                max_w = len(str(h)) + 2  # 表头宽度 + 边距
                for row in rows:
                    if i < len(row):
                        max_w = max(max_w, len(str(row[i])) + 2)
                col_widths.append(min(max_w, 20))  # 最大20字符

        # 默认对齐：居中
        if alignments is None:
            alignments = ["^"] * num_cols

        # 构建分隔线
        def make_line(left, mid, right, fill="─"):
            parts = [fill * w for w in col_widths]
            return prefix + left + mid.join(parts) + right

        top_line = make_line("┌", "┬", "┐")
        mid_line = make_line("├", "┼", "┤")
        bot_line = make_line("└", "┴", "┘")

        # 构建行
        def make_row(values):
            cells = []
            for i, v in enumerate(values):
                w = col_widths[i] if i < len(col_widths) else 10
                a = alignments[i] if i < len(alignments) else "^"
                cells.append(f"{str(v):{a}{w}}")
            return prefix + "│" + "│".join(cells) + "│"

        # 打印标题
        if title:
            print(f"\n{prefix}{title}")

        # 打印表格
        print(top_line)
        print(make_row(headers))
        print(mid_line)
        for row in rows:
            print(make_row(row))
        print(bot_line)

    @staticmethod
    def print_simple_header(title: str, width: int = 60, char: str = "─"):
        """打印简单的标题分隔线"""
        print(f"\n{char*width}")
        print(title)
        print(f"{char*width}")

    @staticmethod
    def print_section(title: str, width: int = 60):
        """打印区块标题"""
        print(f"\n{'='*width}")
        print(title)
        print(f"{'='*width}")
