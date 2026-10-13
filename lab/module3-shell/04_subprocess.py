"""模块 3 / 实验 4：子进程调用与退出码的四种读法。

Python 里跑外部命令的四种姿势
-----------------------------
    subprocess.run(...)                返回值里带 returncode，**不抛异常**
    subprocess.run(..., check=True)    非 0 直接抛 CalledProcessError
    subprocess.run(..., capture_output=True)  抓 stdout/stderr 到内存
    subprocess.Popen(...)              要流式读写、要并发时用

绝大多数 CLI 工具的骨架就是：解析参数 -> 调子进程 -> 把子进程的退出码
当成自己的退出码返回。这正是 `spec-kit/scripts/bash/*.sh` 和
`spec-kit/scripts/python/*.py` 在做的事。

安全提醒
--------
永远不要用 `shell=True` 拼用户输入 —— 那是命令注入。要传参数就传 list，
让操作系统直接 execve，不经过 shell 解析。

跑法
----
    python 04_subprocess.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def demo_basic() -> None:
    section("4a：默认不抛异常 —— 退出码要自己看 returncode")
    proc = subprocess.run(
        [sys.executable, "-c", "import sys; print('ok'); sys.exit(7)"],
        capture_output=True,
        text=True,
    )
    print(f"  returncode = {proc.returncode}")
    print(f"  stdout     = {proc.stdout.strip()!r}")
    print("  -> run() 把'子进程失败了'当成正常返回值交给你判断。")
    print("     这是刻意的设计：让调用者显式处理失败分支。")


def demo_check() -> None:
    section("4b：check=True —— 让失败立刻变成异常")
    try:
        subprocess.run(
            [sys.executable, "-c", "import sys; sys.exit(7)"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  捕获到 CalledProcessError")
        print(f"    exc.returncode = {exc.returncode}")
        print(f"    exc.cmd        = {exc.cmd}")
    print("  -> 适合'这一步失败就没有后续可言'的场景。")


def demo_propagate() -> None:
    section("4c：CLI 的骨架 —— 把子进程的退出码原样透传出去")
    # 模拟一个真实的 CLI：跑测试，测试挂了自己也挂
    fake_test = "import sys; print('2 passed, 1 failed'); sys.exit(1)"
    proc = subprocess.run(
        [sys.executable, "-c", fake_test], capture_output=True, text=True
    )
    print(f"  子进程(测试)退出码 = {proc.returncode}")
    print(f"  子进程输出         = {proc.stdout.strip()!r}")
    print(f"  -> 本 CLI 将返回同样的退出码: {proc.returncode}")
    print("     这就是 pytest / ruff / git 能被 CI 理解的原因：它们都说同一种语言。")


def demo_no_shell_injection() -> None:
    section("4d：不要用 shell=True 拼输入")
    evil = "a; echo 我被注入了"

    print("  ❌ shell=True 的写法会把分号当命令分隔符执行：")
    print(f'     subprocess.run(f"echo {evil}", shell=True)')

    print("\n  ✅ 传 list，参数不经过 shell 解析：")
    proc = subprocess.run(
        [sys.executable, "-c", "import sys; print('收到参数:', sys.argv[1])", evil],
        capture_output=True,
        text=True,
    )
    print(f"     {proc.stdout.strip()}")

    if sys.platform == "win32":
        print("  （Windows 上 shell=True 走的是 cmd.exe，注入风险同样存在）")


def demo_streaming() -> None:
    section("4e：Popen —— 需要边跑边读输出时")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "for i in range(3):\n"
         "    print(f'  第 {i+1} 行', flush=True)\n"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"    [实时] {line.rstrip()}")
    proc.wait()
    print(f"  Popen 最终 returncode = {proc.returncode}")
    print("  -> `python -u` 关闭输出缓冲，否则你会等到进程结束才看到输出。")


def main() -> int:
    _force_utf8()
    print("模块 3 / 实验 4：子进程与退出码")
    demo_basic()
    demo_check()
    demo_propagate()
    demo_no_shell_injection()
    demo_streaming()

    section("小结：一个 CLI 工具的生命线")
    print("  读取参数 -> 调子进程 -> 判定 returncode -> 用自己的退出码汇报")
    print("  中间任何一步把失败吞掉，上层 CI 就失去了拦截能力。")
    print(f"\n  当前仓库根: {Path(__file__).resolve().parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
