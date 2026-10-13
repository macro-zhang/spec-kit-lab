"""TDD 的行为测试 —— 这些断言在实现之前就先写好了。

读法：每一行 parametrize 就是一条"契约条款"。
Agent 的作业范围被这张表框死：它只能想办法让这些断言全过，
不能自行决定"什么叫做对了"。
"""

from __future__ import annotations

import pytest

from calc import parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("45s", 45),
        ("2m", 120),
        ("1h", 3600),
        ("1d", 86400),
        ("1h30m", 5400),
        ("1d2h3m4s", 86400 + 7200 + 180 + 4),
        ("0s", 0),  # 边界：零是合法的
        ("10h10h", 72000),  # 重复单位允许，语义是累加
        ("1w", 604800),
        ("2w3d", 1468800),

    ],
    ids=[
        "秒",
        "分",
        "时",
        "天",
        "时+分",
        "全单位组合",
        "零边界",
        "重复单位累加",
        "周",
        "周+天",
    ],
)
def test_valid_durations(text: str, expected: int) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",  # 空串
        "abc",  # 完全没有数字
        "1h30",  # 尾部有裸数字，没单位
        "30m1",  # 同上
        "-5s",  # 负数
        "1x",  # 未知单位
        "1H",  # 大小写敏感，大写不认
        " 1h",  # 首部空白
        "1h 30m",  # 中间空白
        "h",  # 只有单位没有数字
    ],
    ids=[
        "空串",
        "无数字",
        "尾部裸数字",
        "尾部裸数字2",
        "负数",
        "未知单位",
        "大写单位",
        "首部空白",
        "中间空白",
        "只有单位",
    ],
)
def test_invalid_durations_raise_value_error(text: str) -> None:
    """负例 —— 和正例同等重要。

    只测"正确输入能得到正确结果"的测试是半个测试：它完全放行
    "对任何输入都返回 0" 这种荒谬实现。必须同时规定**什么必须失败**。
    这正是 spec-kit 的 CONTRIBUTING.md 里 "positive cases AND negative cases" 的要求。
    """
    with pytest.raises(ValueError):
        parse_duration(text)


def test_non_string_input_rejected() -> None:
    with pytest.raises(ValueError):
        parse_duration(None)  # type: ignore[arg-type]
