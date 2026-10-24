"""契约测试（JSON Schema 侧）：冻结的契约文件本身也要被测。

测试负责保证三件事：
  (a) 这份文件是合法的 JSON Schema；
  (b) 它和数据实现（这里是 Pydantic 模型）没有漂移；
  (c) 它对正例放行、对负例拦截。

⚠️ 与 spec-kit 的差异（别误引）
------------------------------
不要以为 spec-kit 也是这么干的。实测 `spec-kit/tests/contract/` 里搜
`jsonschema` / `Draft` / `check_schema` **零命中**：它的契约本体是
markdown 文档 `contracts/*.schema.md`（见 `test_manifest_schema.py:2-4`
的 docstring "Mirrors contracts/bundle-manifest.schema.md"），
执行器是手写校验函数。

本实验台用 jsonschema 库是**另一条路线**，目的是让你把两条放在一起比：
真正不可或缺的不是 schema 的格式，而是**是否存在一个独立的执行器**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from calc.contracts import UserProfile

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "contracts" / "user-profile.schema.json"

VALID_PAYLOAD: dict[str, Any] = {
    "id": 42,
    "username": "alice_dev",
    "email": "alice@example.com",
    "role": "admin",
    "tags": ["study", "spec-kit"],
    "locale": "zh_CN",
}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_dataset_file_exists() -> None:
    assert SCHEMA_PATH.is_file(), f"契约文件丢了: {SCHEMA_PATH}"


def test_schema_itself_is_valid(schema: dict[str, Any]) -> None:
    """(a) schema 首先必须自己合法，否则它校验不了任何东西。"""
    Draft202012Validator.check_schema(schema)


def test_schema_accepts_valid_payload(schema: dict[str, Any]) -> None:
    """(c) 正例放行。"""
    jsonschema.validate(instance=VALID_PAYLOAD, schema=schema)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: {**p, "id": 0},
        lambda p: {**p, "username": "AB"},
        lambda p: {**p, "email": "nope"},
        lambda p: {**p, "role": "root"},
        lambda p: {**p, "tags": ["UPPER"]},
        lambda p: {**p, "nickname": "多余字段"},
        lambda p: {k: v for k, v in p.items() if k != "email"},
        lambda p: {**p, "tags": ["has space"]},
        lambda p: {**p, "locale": "zh-cn"},
    ],
    ids=["id非正", "用户名大写", "邮箱错", "角色越界", "标签大写", "多余字段", "缺必填", "标签带空格", "locale格式错"]
)
def test_schema_rejects_invalid_payload(schema: dict[str, Any], mutate) -> None:
    """(c) 负例拦截 —— 注意 `additionalProperties: false` 对应多余字段那条。"""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=mutate(VALID_PAYLOAD), schema=schema)


def test_schema_does_not_drift_from_code(schema: dict[str, Any]) -> None:
    """(b) 防漂移：冻结的 Schema 必须和代码里的类型定义一致。

    为什么不直接做「文本全等」比对？因为 Pydantic 生成的 schema 会带
    `title`、`$defs` 之类的实现细节，逐字比对会因为无关噪音天天报红，
    最后大家就把这个测试删了 —— 那才是真正的失败。

    所以只比对**契约的语义骨架**：必填项集合 + 每个字段的类型。
    骨架一致 = 契约一致；其余是实现细节。

    ⚠️ 这条断言是真会红的 —— 本实验台第一次跑就红了：Pydantic 那边
    `role` 和 `tags` 有默认值（所以是可选），而冻结的 schema 却把它们
    列进了 `required`。这正是契约测试的价值：它把"两边说法不一致"
    变成一个确定性的失败，而不是等线上才发现。

    修法是让 schema 跟随代码（有默认值 = 可省略），而不是删掉这条断言。
    """
    generated = UserProfile.model_json_schema()

    assert set(schema["required"]) == set(generated["required"]), (
        "必填字段集合漂移了："
        f"schema={sorted(schema['required'])} vs code={sorted(generated['required'])}"
    )

    for field in generated["required"]:
        assert field in schema["properties"], f"schema 里缺字段定义: {field}"

    # 枚举字段必须完全一致
    assert set(schema["properties"]["role"]["enum"]) == set(
        generated["properties"]["role"]["enum"]
    )

    # 类型必须一致
    for field, spec in schema["properties"].items():
        if "type" in spec and "type" in generated["properties"].get(field, {}):
            assert spec["type"] == generated["properties"][field]["type"], (
                f"字段 {field} 类型漂移: {spec['type']} vs {generated['properties'][field]['type']}"
            )

    # 关键开关：多字段必须一律拒绝，两边都要硬
    assert schema["additionalProperties"] is False
    assert generated["additionalProperties"] is False
