"""时长字符串解析 —— 本实验台的被测对象。

契约见 parse_duration 的 docstring 与 tests/test_duration.py。
注意：本文件由 run_red_green_refactor.py 从 variants/ 复制生成，
手改内容会在下次跑驱动器时被覆盖（误覆盖后用 git restore 找回）。
"""

from __future__ import annotations
import re

_DURATION = re.compile(r"^(?:\d+[wdhms])+$")
_SEGMENT = re.compile(r"(\d+)([wdhms])")
_UNIT_SECONDS: dict[str, int] = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}

def parse_duration(text: str) -> int:
    """把 "1h30m" 这样的时长字符串解析成总秒数。

    契约：
        输入   str，由若干 <非负整数><单位> 组成，单位属于 w/d/h/m/s
        输出   int，总秒数
        失败   任何不合法的输入都抛 ValueError
    """
    if not isinstance(text,str) or not _DURATION.fullmatch(text):
        raise ValueError(f"不合法时长格式：{text!r}")
    total = 0
    for value_str,unit in _SEGMENT.findall(text):
        total += int(value_str) * _UNIT_SECONDS[unit]
    return total

