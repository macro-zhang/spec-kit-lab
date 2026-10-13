"""模块 3 / 实验 1：POSIX 退出码 —— 进程向环境汇报结果的唯一通道。

核心事实
--------
1. 进程结束时向操作系统返回一个 0..255 的整数。0 = 成功，非 0 = 失败。
2. 这是**进程之间唯一通用的成功/失败协议**。测试框架、CI、git hook、
   shell 的 `&&` / `||` / `if`，全部建立在它之上，而不是建立在"解析输出"之上。
3. 退出码的来源（Python）：
       正常执行到脚本末尾        -> 0
       sys.exit(0)              -> 0
       sys.exit(3)              -> 3
       raise SystemExit("msg")  -> 非 0（字符串消息会打到 stderr）
       未捕获的异常             -> 1（并打印 traceback）

为什么 spec-kit 关心这个
------------------------
`spec-kit/scripts/bash/check-prerequisites.sh` 这类前置检查脚本，靠的就是
"退出码非 0 就中断后续步骤"。CI（`.github/workflows/test.yml` 里的
`uv run pytest`）也是如此：pytest 只要有一个用例失败就返回非 0，
GitHub Actions 看到非 0 就把这一 job 标红、阻断合并。

跑法
----
    python 01_exit_codes.py
"""

from __future__ import annotations

import subprocess
import sys


def _force_utf8() -> None:
    """把 stdout/stderr 切到 UTF-8，否则 Windows 控制台（GBK）会 UnicodeEncodeError。

    这不是本实验的凑数补丁 —— spec-kit 在 `src/specify_cli/__init__.py` 的
    `main()` 里做的正是同一件事：win32 上先 reconfigure 编码，再交给 Typer。
    脚本层还有更讲究的做法：`scripts/python/check_prerequisites.py` 的
    `_status_marker` 会先探测 `sys.stdout.encoding`，管道下退化成 `[OK]/[FAIL]`，
    防止 UnicodeEncodeError 把整份报告从中间截断。

    跨平台脚本的第一课：**不要假设终端能显示你的字符集**。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


# 子进程模式开关
CHILD_OK = "--child-ok"
CHILD_FAIL = "--child-fail"
CHILD_CRASH = "--child-crash"


def child_main(kind: str) -> int:
    """这是"被观察的进程"。它按 kind 决定自己返回什么退出码。"""
    if kind == CHILD_OK:
        print("      [子进程] 一切正常，返回 0")
        return 0
    if kind == CHILD_FAIL:
        print("      [子进程] 校验不通过，返回 3", file=sys.stderr)
        return 3
    if kind == CHILD_CRASH:
        # 故意不捕获：Python 会把退出码设为 1
        raise ValueError("我崩溃了 —— 未捕获的异常")
    raise SystemExit(f"未知的子进程模式: {kind}")


def probe(label: str, args: list[str]) -> int:
    """在当前进程之外启动一个子进程，回收它的 stdout / stderr / 退出码。

    注意 subprocess.run 本身**不会**因为子进程非 0 而抛异常（除非 check=True）。
    这正是"如何读取退出码"的关键：returncode 字段。
    """
    print(f"\n[{label}]  命令: python {__file__.split(chr(92))[-1]} {' '.join(args)}")
    proc = subprocess.run(
        [sys.executable, __file__, *args],
        capture_output=True,
        text=True,
    )
    for line in proc.stdout.splitlines():
        print(f"    stdout | {line}")
    for line in proc.stderr.splitlines():
        print(f"    stderr | {line}")
    print(f"    >>> returncode = {proc.returncode}")
    return proc.returncode


def main() -> int:
    _force_utf8()
    print("=" * 72)
    print("POSIX 退出码：0 = 成功，非 0 = 失败")
    print("=" * 72)

    codes = {
        probe("正常结束", [CHILD_OK]): "0 = 成功。shell 的 && 会继续往下走。",
        probe("显式失败", [CHILD_FAIL]): "3 = 失败。shell 的 && 会短路，CI 会标红。",
        probe("未捕获异常", [CHILD_CRASH]): "1 = 未捕获异常。注意 traceback 走的是 stderr。",
    }

    print("\n" + "-" * 72)
    print("读法总结")
    print("-" * 72)
    for code in sorted(codes):
        print(f"  退出码 {code:<3} -> {codes[code]}")

    print(
        "\n关键区别：stdout 是**给人/给下游程序的数据**，stderr 是**诊断信息**，\n"
        "退出码是**给机器的判定**。三者职责不同，绝不能混用——\n"
        "把错误信息打到 stdout，下游一旦用管道解析输出就会把错误当成数据吃进去。"
    )

    # 本脚本自己成功退出
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] in {CHILD_OK, CHILD_FAIL, CHILD_CRASH}:
        raise SystemExit(child_main(argv[0]))
    raise SystemExit(main())
