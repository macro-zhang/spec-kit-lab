/**
 * 行为测试 —— 与 Python 版 `tests/test_duration.py` 逐条对应。
 *
 * 用的是 Node 内置测试运行器 `node:test`，零依赖。
 * 运行：node --test test/duration.test.mjs
 *
 * 关于断言风格：这里用 node:assert/strict。注意 `assert.throws` 的第二个参数
 * 可以传构造函数或正则 —— 传正则能进一步收紧"抛的是不是我要的那类错误"，
 * 而不是"随便抛个错就算过"。
 */

import test from "node:test";
import assert from "node:assert/strict";

import { parseDuration, DurationError } from "../src/duration.mjs";

// ── 正例：8 条，与 Python 版 id 一一对应 ────────────────────────────────
const VALID = [
  ["45s", 45, "秒"],
  ["2m", 120, "分"],
  ["1h", 3600, "时"],
  ["1d", 86400, "天"],
  ["1h30m", 5400, "时+分"],
  ["1d2h3m4s", 86400 + 7200 + 180 + 4, "全单位组合"],
  ["0s", 0, "零边界"],
  ["10h10h", 72000, "重复单位累加"],
];

for (const [text, expected, id] of VALID) {
  test(`合法时长 / ${id}: ${text} -> ${expected}`, () => {
    assert.equal(parseDuration(text), expected);
  });
}

// ── 负例：10 条 ───────────────────────────────────────────────────────
const INVALID = [
  ["", "空串"],
  ["abc", "无数字"],
  ["1h30", "尾部裸数字"],
  ["30m1", "尾部裸数字2"],
  ["-5s", "负数"],
  ["1x", "未知单位"],
  ["1H", "大写单位"],
  [" 1h", "首部空白"],
  ["1h 30m", "中间空白"],
  ["h", "只有单位"],
];

for (const [text, id] of INVALID) {
  test(`非法时长 / ${id}: ${JSON.stringify(text)}`, () => {
    // 只断言"抛错"是不够的 —— 要断言抛的是 DurationError。
    // 否则实现里任何手滑造成的 TypeError 都会让测试假绿。
    assert.throws(() => parseDuration(text), DurationError);
  });
}

test("非字符串输入必须被拒绝", () => {
  assert.throws(() => parseDuration(null), DurationError);
  assert.throws(() => parseDuration(42), DurationError);
  assert.throws(() => parseDuration(undefined), DurationError);
});

/**
 * 回归测试的味道：这是一个真实的 JS 陷阱。
 * 全局正则带 g 标志后是有状态的（lastIndex），如果不重置，
 * 第二次调用会从上次匹配结束处开始搜索，导致同一个输入时对时错。
 */
test("回归：连续调用不受全局正则 lastIndex 残留影响", () => {
  assert.equal(parseDuration("1h30m"), 5400);
  assert.equal(parseDuration("1h30m"), 5400, "第二次调用必须给出相同结果");
  assert.equal(parseDuration("45s"), 45);
  assert.equal(parseDuration("1h30m"), 5400);
});
