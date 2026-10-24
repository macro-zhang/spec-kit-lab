"""契约的代码化表达 —— 用类型系统把"接口承诺"变成可执行的东西。

为什么静态类型能压制模型幻觉
----------------------------
LLM 生成代码时，最大的失效模式不是"语法错"，而是**接口漂移**：
它凭空发明一个字段名、把 `int` 写成 `str`、漏掉必填项、或者返回一个
调用方根本没约定的结构。语法完全合法，运行到线上才炸。

契约（Pydantic 模型 / TypeScript interface / JSON Schema）把这类错误
从"运行时/线上"提前到"校验时"，而且给出的是**机器可判定的失败**，
不是"看起来差不多"。在 spec-kit 的语境里，这就是把"什么算做对了"
从 Agent 的自我评价里剥离出来，交给确定性代码判定。

对应 spec-kit 真实做法（以及一处反直觉的差异）
--------------------------------------------
spec-kit 的 `tests/contract/` **既不用 jsonschema 也不用 pydantic**：
全仓搜 jsonschema 零命中。它的 schema 本体是 markdown 文档
（`contracts/bundle-manifest.schema.md`），**测试是唯一的执行器** ——
校验入口是手写的 `BundleManifest.from_dict(data).structural_errors()`，
返回一个错误清单 `list[str]`。

本实验台刻意走另一条路（用真正的 jsonschema 库），好让你把两种路线
放在一起对比：

  路线 A（spec-kit）：schema 是文档，校验器是手写代码，测试负责执行
  路线 B（本实验台）：schema 是机器可读文件，校验器是现成库

两者真正的共同点、也是唯一重要的那一点：**都必须有一个独立的执行器**。
没有执行器的 schema，无论是 markdown 还是 JSON，都只是一份没人遵守的愿望。
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator



class UserProfile(BaseModel):
    """对外承诺的用户画像契约。

    `extra="forbid"` 是最关键的一行：它让"多传了一个字段"变成硬失败。
    默认行为（ignore）会静默吞掉拼错的字段名 —— 那正是幻觉最喜欢的藏身处。
    """

    # extra="forbid" —— 多传一个字段 = 硬失败（默认是 ignore，会静默吞掉拼错的字段名）
    # strict=True   —— 禁止隐式类型强转（默认 lax 会把 "42" 强转成 42）
    #
    # 第二条在本项目的语境里同样关键：模型幻觉的典型形态之一就是
    # "类型差不多但不对"，而 lax 模式恰好会替你把它修好，
    # 于是错误被推后到消费端才爆。宁可在这里硬失败。
    model_config = ConfigDict(extra="forbid", strict=True)

    id: Annotated[int, Field(gt=0, description="用户 ID，必须为正整数")]
    username: Annotated[str, Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_]+$")]
    email: Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")]
    role: Literal["admin", "member", "guest"] = "member"
    tags: list[str] = Field(default_factory=list, max_length=10)
    locale: Annotated[str, Field(pattern=r"^[a-z]{2}_[A-Z]{2}$")]


    @field_validator("tags")
    @classmethod
    def _tags_must_match_pattern(cls, value: list[str]) -> list[str]:
        for tag in value:
            if re.fullmatch(r"[a-z0-9_-]+", tag) is None:
                raise ValueError(f"标签必须匹配 [a-z0-9_-]+，收到: {tag!r}")
        return value


class ProfilePage(BaseModel):
    """分页信封 —— 展示"契约可以嵌套，且嵌套也要被校验"。"""

    # 嵌套层同样要严：外层宽进，内层严出，等于白设。
    model_config = ConfigDict(extra="forbid", strict=True)

    total: Annotated[int, Field(ge=0)]
    items: list[UserProfile]
