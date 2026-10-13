"""🔴 RED 阶段：只有骨架，没有实现。

这是 TDD 的第一条铁律 —— **先写测试，再把实现留空，跑一次确认它是红的**。
如果测试在实现之前就是绿的，那说明这个测试根本没在测东西。

Agent 在这里的角色就是"填空者"：测试已经把"什么叫做对了"锁死，
它唯一能做的就是把这几个 NotImplementedError 换成真正的逻辑。
"""

from __future__ import annotations


def parse_duration(text: str) -> int:
    """把 "1h30m" 这样的时长字符串解析成总秒数。

    契约：
        输入   str，由若干 <非负整数><单位> 组成，单位属于 d/h/m/s
        输出   int，总秒数
        失败   任何不合法的输入都抛 ValueError
    """
    raise NotImplementedError("RED：尚未实现")
