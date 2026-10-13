"""模块 3 / 实验 2：stdout / stderr 分流与管道、重定向。

三条流的职责（POSIX）
---------------------
    fd 0  stdin   标准输入   —— 数据从哪来
    fd 1  stdout  标准输出   —— **结果数据**。可以被安全地管道/重定向给下游
    fd 2  stderr  标准错误   —— **诊断信息**。不参与数据管道，直接给人看

最容易犯的错：把错误信息 print 到 stdout。一旦下游用 `| grep` / `| jq`
解析输出，错误信息就会被当成数据吃掉，产生"看起来成功了其实失败了"的假象。

管道的退出码陷阱
----------------
bash 默认只取**管道最后一个命令**的退出码。前面命令失败了但最后一个成功，
整条管道仍然返回 0 —— 这就是 CI 里"测试挂了但流水线是绿的"的经典根因。
解法是 `set -o pipefail`。

跑法
----
    python 02_pipeline.py                # 只讲解 + 自检
    python 02_pipeline.py --emit-good    # 被调用：正常输出
    python 02_pipeline.py --emit-bad     # 被调用：往 stderr 写错误并返回非 0
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


GOOD = "--emit-good"
BAD = "--emit-bad"


def emit_good() -> int:
    # 结果数据 -> stdout
    print("name=widget count=3")
    print("name=gadget count=7")
    return 0


def emit_bad() -> int:
    # 诊断信息 -> stderr（绝不写 stdout）
    print("ERROR: 数据源不可用", file=sys.stderr)
    return 4


def demo_streams() -> None:
    print("=" * 72)
    print("实验 2：stdout 是数据，stderr 是诊断，退出码是判定")
    print("=" * 72)

    for label, flag in (("正常", GOOD), ("故障", BAD)):
        proc = subprocess.run(
            [sys.executable, __file__, flag], capture_output=True, text=True
        )
        print(f"\n--- {label} 模式 ---")
        print(f"  stdout ({len(proc.stdout)} 字节): {proc.stdout!r}")
        print(f"  stderr ({len(proc.stderr)} 字节): {proc.stderr!r}")
        print(f"  returncode: {proc.returncode}")


def demo_shell_pipe() -> None:
    """在真实 bash 里演示 `2>/dev/null`、`2>&1`、以及 pipefail。"""
    print("\n" + "=" * 72)
    print("实验 2b：真实 bash 里的重定向与退出码")
    print("=" * 72)

    script = f'''
set -u
PY="{sys.executable}"
SELF="{__file__}"

echo "--- A) 只看 stdout：错误被丢弃，但退出码仍然是非 0 ---"
out=$("$PY" "$SELF" {BAD} 2>/dev/null); rc=$?
echo "  stdout='$out'  returncode=$rc"

echo
echo "--- B) 把 stderr 并进 stdout (2>&1) ---"
combined=$("$PY" "$SELF" {BAD} 2>&1); rc=$?
echo "  combined='$combined'  returncode=$rc"

echo
echo "--- C) 管道陷阱：前面失败，最后一个命令成功 ---"
"$PY" "$SELF" {BAD} 2>/dev/null | head -n 1
echo "  未开 pipefail -> 管道退出码 = $?  (被吞掉了！)"

set -o pipefail
"$PY" "$SELF" {BAD} 2>/dev/null | head -n 1
echo "  开了 pipefail -> 管道退出码 = $?  (终于暴露了)"
'''
    bash = _find_bash()
    if bash is None:
        print("\n(未找到 bash，跳过这一小节；Windows 上装了 Git for Windows 才有)")
        return
    proc = subprocess.run(
        [bash, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(proc.stdout)
    if proc.stderr.strip():
        print("[bash stderr]", proc.stderr)


def _find_bash() -> str | None:
    import shutil

    for cand in ("bash", r"C:\Program Files\Git\bin\bash.exe"):
        found = shutil.which(cand) if not cand.endswith(".exe") else cand
        if found:
            return found
    return None


def main() -> int:
    _force_utf8()
    demo_streams()
    demo_shell_pipe()
    print(
        "\n结论：\"失败\"这件事必须同时体现在**退出码**上，\n"
        "因为下游程序不会去读你的 stderr 文案来做判断。"
    )
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == GOOD:
        raise SystemExit(emit_good())
    if argv and argv[0] == BAD:
        raise SystemExit(emit_bad())
    raise SystemExit(main())
