"""契约测试（Pydantic 侧）：把"接口承诺"变成可执行的断言。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from calc.contracts import ProfilePage, UserProfile

pytestmark = pytest.mark.contract

VALID_PAYLOAD = {
    "id": 42,
    "username": "zhb_dev",
    "email": "zhb@example.com",
    "role": "admin",
    "tags": ["study", "spec-kit"],
}


def test_valid_payload_roundtrips() -> None:
    profile = UserProfile.model_validate(VALID_PAYLOAD)
    assert profile.id == 42
    assert profile.role == "admin"
    # 序列化回去必须还是同一份数据 —— 契约是双向的
    assert profile.model_dump() == VALID_PAYLOAD


def test_role_defaults_to_member() -> None:
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "role"}
    assert UserProfile.model_validate(payload).role == "member"


@pytest.mark.parametrize(
    ("field", "bad_value", "why"),
    [
        ("id", 0, "id 必须 > 0"),
        ("id", "42", "id 必须是整数，不接受数字字符串"),
        ("username", "ab", "太短"),
        ("username", "ZHB", "必须小写"),
        ("username", "zhb-dev", "连字符不合法，只允许 [a-z0-9_]"),
        ("email", "not-an-email", "邮箱格式"),
        ("role", "root", "role 是封闭枚举"),
        ("tags", ["OK_UPPER"], "标签必须小写"),
    ],
)
def test_invalid_fields_rejected(field: str, bad_value: object, why: str) -> None:
    payload = {**VALID_PAYLOAD, field: bad_value}
    with pytest.raises(ValidationError):
        UserProfile.model_validate(payload)


def test_extra_field_is_a_hard_error() -> None:
    """`extra="forbid"` 是压制幻觉的核心开关。

    模型幻觉最常见的形态之一，就是"自作主张多写一个字段"
    （`fullname` 而不是 `username`，或者凭空加一个 `nickname`）。
    默认的 ignore 行为会让它静默通过，错误被推迟到消费端才爆。
    """
    with pytest.raises(ValidationError) as excinfo:
        UserProfile.model_validate({**VALID_PAYLOAD, "nickname": "阿彪"})

    errors = excinfo.value.errors()
    assert errors[0]["type"] == "extra_forbidden"
    assert errors[0]["loc"] == ("nickname",)


def test_nested_contract_is_also_enforced() -> None:
    """契约可以嵌套，而且嵌套层同样要拦。"""
    good = ProfilePage.model_validate({"total": 1, "items": [VALID_PAYLOAD]})
    assert good.total == 1

    with pytest.raises(ValidationError):
        ProfilePage.model_validate({"total": 1, "items": [{"id": 1}]})


def test_negative_total_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfilePage.model_validate({"total": -1, "items": []})
