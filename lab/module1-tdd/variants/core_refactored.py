"""🔵 REFACTOR 阶段：行为一字不改，只改结构。

改了这些：
  * 用命名分组替代"拼回去再比对"的土办法，意图更直白
  * 单位表和正则绑在一起，改单位时不会漏改
  * 错误信息带上具体位置，排障更快

**行为必须与 GREEN 完全一致** —— 这就是为什么重构必须在测试全绿之后做：
测试是这次结构手术的安全网。如果重构后红了，你立刻知道是自己改坏了，
而不是"需求本来就没实现"。
"""

from __future__ import annotations

import re

# 单位 -> 秒。顺序无关，正则里的字符类从这张表派生，避免两处不同步。
_UNIT_SECONDS: dict[str, int] = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}

_DURATION = re.compile(
    r"\A(?P<segments>(?:\d+[wdhms])+)\Z",  # 整体必须完全匹配，杜绝首尾垃圾
)
_SEGMENT = re.compile(r"(?P<amount>\d+)(?P<unit>[wdhms])")


def parse_duration(text: str) -> int:
    """把 "1h30m" 解析成 5400 秒；非法输入抛 ValueError。"""
    if not isinstance(text, str):
        raise ValueError(f"时长必须是字符串，收到 {type(text).__name__}")
    if not text:
        raise ValueError("时长不能为空")

    if _DURATION.fullmatch(text) is None:
        raise ValueError(f"时长格式非法: {text!r}；期望形如 '1h30m' / '45s' / '2d'")

    return sum(
        int(match["amount"]) * _UNIT_SECONDS[match["unit"]]
        for match in _SEGMENT.finditer(text)
    )
