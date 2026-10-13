"""模块 3 / 实验 3：文件时间戳、只读保护、以及文件锁。

三个 spec-kit 真实用到的能力
----------------------------
1. **mtime（修改时间）**：判断产物是否比输入新，从而决定要不要重新生成。
   这是 make / 增量构建 / 缓存失效判断的最底层原语。
2. **只读保护**：把"已定稿"的契约文件设成只读，物理上阻止后手（包括 Agent）
   在实现阶段偷偷改需求。这就是"把定契约的权力收归人类"的落地手段之一。
3. **文件锁**：并发场景下防止两个进程同时写同一个文件。
   spec-kit 自己有 `spec-kit/tests/lock_helpers.py` 和
   `spec-kit/tests/test_shared_infra_lock.py` —— 同一手法。

跨平台差异（重要）
------------------
* 只读：POSIX 靠 `chmod 0o444`；Windows 靠 `attrib +R` 或 ACL。
  本实验用 Python 的 `os.chmod(path, stat.S_IREAD)`，两个平台都能生效。
* 锁：POSIX 用 `fcntl.flock`，Windows 用 `msvcrt.locking` 或"以独占模式打开"。
  本实验用最朴素、跨平台的**孤儿锁文件**方案，便于理解原理。

跑法
----
    python 03_filesystem.py
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import time
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


IS_WINDOWS = os.name == "nt"


def demo_mtime(work: Path) -> None:
    print("=" * 72)
    print("实验 3a：mtime —— 判断'谁更新'，决定要不要重建")
    print("=" * 72)

    contract = work / "spec.md"
    impl = work / "implementation.py"

    contract.write_text("需求：计算器必须支持幂运算\n", encoding="utf-8")
    time.sleep(1.1)  # 拉开时间差，避免秒级精度把两次写入算成同一时刻
    impl.write_text("def power(a, b): ...\n", encoding="utf-8")

    c_mtime = contract.stat().st_mtime
    i_mtime = impl.stat().st_mtime

    print(f"  spec.md            mtime = {time.strftime('%H:%M:%S', time.localtime(c_mtime))}")
    print(f"  implementation.py  mtime = {time.strftime('%H:%M:%S', time.localtime(i_mtime))}")

    if i_mtime > c_mtime:
        print("  -> 实现比契约新：产物是新鲜的 ✅")
    else:
        print("  -> 契约比实现新：**契约变了，实现过期了** ❌ 必须重新实现")

    print("\n  这就是增量构建的判定公式：if target.mtime < source.mtime: rebuild()")


def demo_readonly(work: Path) -> None:
    print("\n" + "=" * 72)
    print("实验 3b：只读保护 —— 物理阻断对已定稿契约的篡改")
    print("=" * 72)

    frozen = work / "constitution.frozen.md"
    frozen.write_text("第一条：测试必须先于实现。\n", encoding="utf-8")

    os.chmod(frozen, stat.S_IREAD)  # 0o444，POSIX 与 Windows 都认
    readonly_flag = not os.access(frozen, os.W_OK)
    print(f"  已设为只读: {frozen.name}")
    print(f"  os.access(W_OK) = {os.access(frozen, os.W_OK)}  -> 只读生效: {readonly_flag}")

    print("\n  现在尝试写入（应该失败）：")
    try:
        with open(frozen, "a", encoding="utf-8") as fh:
            fh.write("第二条：偷偷加的需求。\n")
        print("    !! 居然写成功了 —— 在某些环境下以管理员/root 运行会绕过只读位")
    except PermissionError as exc:
        print(f"    ✅ 被内核拦下: {type(exc).__name__}: {exc}")

    print(
        "\n  注意：只读位挡得住'手滑'，挡不住 root。真正的强制力来自\n"
        "  版本控制 + CI 门禁（谁能改、改完谁来验），只读位只是第一道软防线。"
    )

    os.chmod(frozen, stat.S_IREAD | stat.S_IWRITE)  # 复原，便于清理


def demo_lock(work: Path) -> None:
    print("\n" + "=" * 72)
    print("实验 3c：文件锁 —— 防止两个进程同时写同一份文件")
    print("=" * 72)

    lock = work / ".speckit.lock"
    target = work / "shared.txt"

    def acquire() -> bool:
        """原子创建锁文件：O_CREAT|O_EXCL 保证'检查并创建'是一步完成的。"""
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            return False

    print(f"  进程 A 尝试取锁 ... {'成功' if acquire() else '失败'}")
    print(f"  进程 B 尝试取锁 ... {'成功' if acquire() else '失败（锁被占）'}")
    print(f"  锁文件内容(持有者 pid) = {lock.read_text(encoding='utf-8')}")

    target.write_text("只有持锁者能写这里\n", encoding="utf-8")
    lock.unlink()
    print("  释放锁后，进程 C 可以取锁 ...", "成功" if acquire() else "失败")
    lock.unlink()

    print(
        "\n  关键点：一定要用 O_CREAT|O_EXCL（'不存在才创建'）这个原子语义。\n"
        "  先 os.path.exists() 再创建，两个进程会同时通过检查 —— 那就是竞态。"
    )


def main() -> int:
    _force_utf8()
    with tempfile.TemporaryDirectory(prefix="speckit-lab3-") as td:
        work = Path(td)
        print(f"临时工作目录: {work}  (platform={'windows' if IS_WINDOWS else 'posix'})\n")
        demo_mtime(work)
        demo_readonly(work)
        demo_lock(work)
    print("\n临时目录已自动清理。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
