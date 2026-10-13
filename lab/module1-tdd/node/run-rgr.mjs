/**
 * Red-Green-Refactor 驱动器（Node 版）—— 与 Python 版 run_red_green_refactor.py 同构。
 *
 * 核心思想：**把"测试是否通过"这件事，还原成一个整数退出码**。
 * 脚本自己也是一个可执行的门禁 —— 三个阶段有一个不符合预期，它就 exit 1。
 *
 * 运行：node run-rgr.mjs
 *
 * 设计上刻意**不修改**实验目录里的任何源文件：每个阶段在系统临时目录里
 * 搭一个一次性小仓库（复制 test/ + 把变体放到 src/duration.mjs），跑完即弃。
 * 这样驱动器可以随便重跑，而 `src/duration.mjs` 始终停在 GREEN 版。
 *
 * 输出只用 ASCII —— 跨平台脚本的基本修养。Windows 控制台默认 GBK，
 * 打 emoji 或中文会 UnicodeEncodeError 甚至把输出从中间截断。
 */

import { spawnSync } from "node:child_process";
import {
  closeSync,
  cpSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/** 每个阶段：变体文件、期望的退出码语义、展示用标签。 */
const STAGES = [
  {
    label: "RED      ",
    variant: "variants/duration.red.mjs",
    expectPass: false,
    why: "只有骨架，测试必须失败",
  },
  {
    label: "GREEN    ",
    variant: "src/duration.mjs",
    expectPass: true,
    why: "最笨的实现，测试必须通过",
  },
  {
    label: "REFACTOR ",
    variant: "variants/duration.refactored.mjs",
    expectPass: true,
    why: "改结构不改行为，仍须通过",
  },
];

const line = (ch = "=") => ch.repeat(74);

/**
 * 在临时目录里跑一个阶段，返回 { code, ok, output }。
 * @param {{variant: string}} stage
 */
function runStage(stage) {
  const sandbox = mkdtempSync(join(tmpdir(), "rgr-node-"));

  try {
    // 搭出一份最小可运行的测试工程
    cpSync(join(HERE, "test"), join(sandbox, "test"), { recursive: true });
    mkdirSync(join(sandbox, "src"), { recursive: true });
    cpSync(join(HERE, stage.variant), join(sandbox, "src", "duration.mjs"));

    // ── 两个刻意的工程决定，都是为了绕开一个真实的 Windows 沙箱限制 ──
    //
    // ① 直接跑测试文件（`node test/duration.test.mjs`），**不用** `node --test`。
    //    原因：`node --test` 会为每个测试文件派生一个子进程，而子进程的
    //    stdio 走**命名管道**。某些受限环境（本实验台所在环境即是）禁止创建
    //    命名管道，结果是 `node --test` 直接炸：
    //        Error: spawn EPERM   errno: -4048
    //    （同样的病根会让 Windows 上的 Cygwin/MSYS `bash` 启动失败：
    //        fatal error - couldn't create signal pipe, Win32 error 5）
    //    直接跑文件时，node:test 在**本进程内**执行用例，不派生任何子进程，
    //    因此完全不受影响。功能上等价：退出码语义一样是 0=全过 / 1=有失败。
    //
    // ② 子进程输出重定向到**文件句柄**，而不是默认的 pipe。
    //    默认 `stdio: 'pipe'` 同样要建命名管道 -> 又是 EPERM。
    //    传一个打开的文件描述符，父进程稍后再把文件读回来，
    //    既拿到了输出，又完全不碰管道。
    const logPath = join(sandbox, "output.log");
    const fd = openSync(logPath, "w");
    let result;
    try {
      result = spawnSync(process.execPath, ["test/duration.test.mjs"], {
        cwd: sandbox,
        stdio: ["ignore", fd, fd],
        // 不设 shell —— 参数是数组且无需 shell 展开。
        // Node 里对应 Python 的"永远不要 shell=True 拼字符串"。
        shell: false,
      });
    } finally {
      closeSync(fd);
    }

    return {
      code: result.status,
      ok: stage.expectPass ? result.status === 0 : result.status !== 0,
      output: readFileSync(logPath, "utf8"),
    };
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
}

function main() {
  console.log(line());
  console.log("Red-Green-Refactor loop (Node / node:test)");
  console.log(line());

  const failures = [];

  for (const stage of STAGES) {
    const mark = stage.expectPass ? "must PASS" : "must FAIL";
    console.log(`\n[${stage.label}] ${stage.why}  (${mark})`);

    const { code, ok, output } = runStage(stage);
    const verdict = code === 0 ? "PASS" : "FAIL";
    console.log(`  node --test exit code = ${code}  ->  tests ${verdict}`);

    // 只在这一阶段不符合预期时，才把尾部输出打出来，避免刷屏
    if (!ok) {
      const tail = output.split(/\r?\n/).filter(Boolean).slice(-25).join("\n");
      console.log("  ---- output tail ----");
      console.log(tail.split(/\r?\n/).map((l) => `  | ${l}`).join("\n"));
      failures.push(
        `${stage.label.trim()}: 期望 ${stage.expectPass ? "通过" : "失败"}，实际退出码 ${code}`,
      );
    }
  }

  console.log(`\n${line()}`);

  if (failures.length > 0) {
    console.log("SELF-CHECK FAILED -- 实验台的期望与实际不符:");
    for (const f of failures) console.log(`   - ${f}`);
    console.log(line());
    // 驱动器自己也是一个门禁：不符就非 0 退出。
    // 这样 CI 里一条 `node run-rgr.mjs` 就能同时验证"实现正确"和"实验台自身没坏"。
    return 1;
  }

  console.log("SELF-CHECK PASSED -- RED 确实红，GREEN/REFACTOR 确实绿。");
  console.log(line());
  return 0;
}

process.exit(main());
