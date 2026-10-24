"""🟢 GREEN 阶段：用**最笨但正确**的办法让测试变绿。

TDD 的第二条铁律：这一步不要追求优雅，只追求通过。
先让红灯变绿，重构留到第三步 —— 那时你有测试兜底，可以放心改结构。

注意这里的实现是"够用就好"：正则一次性抓出所有 <数字><单位>，
再把抓出来的片段拼回去跟原文比对，不一致就说明有垃圾字符。
朴素，但对测试覆盖到的行为是正确的。
"""

from __future__ import annotations

import re

_UNIT_SECONDS: dict[str, int] = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
_TOKEN = re.compile(r"(\d+)([wdhms])")


def parse_duration(text: str) -> int:
    if not isinstance(text, str) or not text:
        raise ValueError("时长不能为空")

    tokens = _TOKEN.findall(text)
    if not tokens:
        raise ValueError(f"无法解析的时长: {text!r}")

    # 把识别到的片段原样拼回去。若与原文不符，说明夹了未识别的字符。
    reconstructed = "".join(f"{amount}{unit}" for amount, unit in tokens)
    if reconstructed != text:
        raise ValueError(f"时长含非法片段: {text!r}")

    return sum(int(amount) * _UNIT_SECONDS[unit] for amount, unit in tokens)
