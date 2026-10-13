"""驱动器：把 Red-Green-Refactor 循环**真的跑一遍并验证**。

它做的事：
    对每个变体 —— 把 variants/<变体>.py 复制成 src/calc/core.py，
    然后用子进程跑 pytest，回收退出码。

    变体            期望退出码   含义
    ------------------------------------------------
    core_red.py        非 0      🔴 测试应当失败
    core_green.py      0         🟢 测试应当通过
    core_refactored.py 0         🔵 重构后行为不变，仍应通过

本脚本最后会自检：如果期望与实际不符，自己以非 0 退出。
换句话说，这个驱动器本身也是一次测试。

跑法
----
    python run_red_green_refactor.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARIANTS = HERE / "variants"
CORE_PY = HERE / "src" / "calc" / "core.py"

# (显示名, 变体文件, 是否期望测试通过)
STAGES: list[tuple[str, str, bool]] = [
    ("🔴 RED      —— 只有骨架，测试必须失败", "core_red.py", False),
    ("🟢 GREEN    —— 最笨的实现，测试必须通过", "core_green.py", True),
    ("🔵 REFACTOR —— 改结构不改行为，仍须通过", "core_refactored.py", True),
]


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


def run_pytest() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=HERE,
        capture_output=True,
        text=True,
    )


def tail(text: str, lines: int = 4) -> str:
    kept = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(f"      {ln}" for ln in kept[-lines:])


def main() -> int:
    _force_utf8()
    print("=" * 74)
    print("Red-Green-Refactor 循环实跑")
    print("=" * 74)

    failures: list[str] = []

    for label, variant, expect_pass in STAGES:
        source = VARIANTS / variant
        if not source.is_file():
            print(f"\n{label}\n  !! 变体文件缺失: {source}")
            return 2

        shutil.copyfile(source, CORE_PY)
        print(f"\n{label}")
        print(f"  已载入 {variant} -> src/calc/core.py")

        proc = run_pytest()
        passed = proc.returncode == 0

        print(f"  pytest 退出码 = {proc.returncode}  ({'绿' if passed else '红'})")
        print(tail(proc.stdout or proc.stderr))

        if passed != expect_pass:
            expected = "通过" if expect_pass else "失败"
            actual = "通过" if passed else "失败"
            failures.append(f"{variant}: 期望{expected}，实际{actual}")

    print("\n" + "=" * 74)
    if failures:
        print("❌ 自检失败 —— 实验台的期望与实际不符：")
        for item in failures:
            print(f"   - {item}")
        return 1

    print("✅ 自检通过：红灯确实是红的，绿灯和重构确实是绿的。")
    print("=" * 74)
    print(
        "\n这就是把「什么算做对了」外包给确定性代码的全部意义：\n"
        "  红灯证明测试有效（不是永远为真的空断言）；\n"
        "  绿灯证明实现达成了契约；\n"
        "  重构仍绿证明结构手术没有伤到行为。\n"
        "  三步之间，Agent 只有「填实现」的自由，没有「改判卷标准」的自由。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
