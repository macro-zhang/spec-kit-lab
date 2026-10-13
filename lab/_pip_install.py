"""把 pip 装依赖这件事，用一个"输出一定看得见"的启动器包起来。

为什么需要它
------------
在受限沙箱里直接 `python -m pip install ...` 会**静默卡死**：pip 默认把
HTTP 缓存写到 `%LOCALAPPDATA%\\pip\\cache`，那是工作区**之外**的路径，
写入被拒绝后 pip 既不报错也不前进。

两层修法：
  1. `--no-cache-dir`  —— 根本不碰工作区外的缓存目录
  2. 输出重定向到**文件句柄**而不是管道
     （本环境禁止命名管道；PowerShell 的 `*>` 也会缓冲到进程结束，
      所以父进程在 pip 跑完前看不到任何东西，看起来就像"卡住"）

用 subprocess 传一个真实的文件描述符，输出就是**边跑边落盘**的，
随时可以 tail 出来看进度。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "pip-install.log"

DEFAULT_PACKAGES = ["pytest", "pydantic", "jsonschema"]


def build_args(packages):
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        "--progress-bar",
        "off",
        *packages,
    ]


def main() -> int:
    PACKAGES = sys.argv[1:] or DEFAULT_PACKAGES
    ARGS = build_args(PACKAGES)
    # stdout/stderr 都指向同一个真实文件句柄 -> 不建管道、不缓冲在父进程里
    with LOG.open("wb") as handle:
        proc = subprocess.run(ARGS, stdout=handle, stderr=subprocess.STDOUT)

    print(f"PIP_EXIT {proc.returncode}")
    print(f"LOG {LOG}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
