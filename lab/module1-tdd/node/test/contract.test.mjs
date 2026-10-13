/**
 * 契约测试 —— 与 Python 版 `tests/test_contract_schema.py` 同构。
 *
 * 运行：node --test test/contract.test.mjs
 *
 * 这里演示三件事：
 *   1. 正例要过
 *   2. **负例同样要过**（只测正例的契约测试等于没测）
 *   3. 代码侧契约与文档侧 schema **不许漂移**
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { structuralErrors, assertProfile } from "../src/profile.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA_PATH = join(HERE, "..", "..", "contracts", "user-profile.schema.json");
const SCHEMA = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));

const VALID_PROFILE = Object.freeze({
  id: 7,
  username: "alice_01",
  email: "alice@example.com",
  role: "member",
  tags: ["alpha", "beta-2"],
});

// ── 正例 ─────────────────────────────────────────────────────────────
test("合法 profile 应该零违规", () => {
  assert.deepEqual(structuralErrors(VALID_PROFILE), []);
});

test("assertProfile 对合法输入原样返回", () => {
  assert.equal(assertProfile(VALID_PROFILE), VALID_PROFILE);
});

test("三种 role 都应该被接受", () => {
  for (const role of ["admin", "member", "guest"]) {
    assert.deepEqual(structuralErrors({ ...VALID_PROFILE, role }), [], `role=${role}`);
  }
});

// ── 负例：未知字段 ───────────────────────────────────────────────────
test("多塞一个字段必须报错，不能静默丢弃", () => {
  const errors = structuralErrors({ ...VALID_PROFILE, is_admin: true });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /未知字段 "is_admin"/);
});

test("多余字段的错误信息里必须出现字段名，否则没法排查", () => {
  const errors = structuralErrors({ ...VALID_PROFILE, superpower: "fly" });
  assert.ok(errors.some((e) => e.includes("superpower")));
});

// ── 负例：顶层类型 ───────────────────────────────────────────────────
// 这一组直接对应 spec-kit 用参数化覆盖的 [[], "", 0, False]。
// 如果实现里写了 `data || {}` 之类的顺手兜底，这四条就会静默通过 —— 测试会抓住它。
for (const bad of [[], "", 0, false, null, undefined, 42]) {
  test(`顶层非对象必须报错: ${JSON.stringify(bad) ?? String(bad)}`, () => {
    const errors = structuralErrors(bad);
    assert.equal(errors.length, 1);
    assert.match(errors[0], /顶层必须是对象/);
  });
}

// ── 负例：逐字段 ─────────────────────────────────────────────────────
const FIELD_CASES = [
  [{ id: 0 }, /id 必须 >= 1/],
  [{ id: -3 }, /id 必须 >= 1/],
  [{ id: 1.5 }, /id 必须是整数/],
  [{ id: "7" }, /id 必须是整数/],
  [{ username: "ab" }, /username 长度必须在 3\.\.32/],
  [{ username: "a".repeat(33) }, /username 长度必须在 3\.\.32/],
  [{ username: "Has-Upper" }, /username 必须匹配/],
  [{ username: "with space" }, /username 必须匹配/],
  [{ email: "not-an-email" }, /email 格式不合法/],
  [{ email: "a@b" }, /email 格式不合法/],
  [{ role: "owner" }, /role 必须是/],
  [{ role: null }, /role 必须是/],
  [{ tags: "alpha" }, /tags 必须是数组/],
  [{ tags: Array.from({ length: 11 }, () => "x") }, /tags 最多 10 个/],
  [{ tags: ["OK", "ok"] }, /tags\[0\] 必须匹配/],
];

for (const [patch, pattern] of FIELD_CASES) {
  const label = Object.keys(patch)[0];
  const value = JSON.stringify(patch[label]);
  test(`字段违规 / ${label}=${value}`, () => {
    const errors = structuralErrors({ ...VALID_PROFILE, ...patch });
    assert.ok(
      errors.some((e) => pattern.test(e)),
      `期望匹配 ${pattern}，实际错误清单: ${JSON.stringify(errors)}`,
    );
  });
}

test("缺失字段要逐个报出来", () => {
  const errors = structuralErrors({});
  assert.equal(errors.length, 3, "id / username / email 三个必填全应被指出");
  // role 与 tags 有默认值，所以缺席**不算**违规 —— 这条断言防止
  // 有人把「可选」误实现成「必填」。
  assert.deepEqual(structuralErrors({ id: 1, username: "abc", email: "a@b.co" }), []);
});

// ── 一次报全部，而不是撞到第一个就停 ─────────────────────────────────
test("多个违规应一次性全部报出", () => {
  const errors = structuralErrors({ id: -1, username: "X", email: "nope", role: "boss" });
  // id / username / email / role 各一处。
  // 注意 tags 缺席**不算**违规（它有默认值），所以这里是 4 而不是 5 ——
  // 这个数字本身就在替契约说话。
  assert.equal(errors.length, 4, `实际 ${errors.length} 条: ${JSON.stringify(errors)}`);
});

// ── 漂移检查：代码契约 vs 文档契约 ───────────────────────────────────
test("代码侧契约与 JSON Schema 不许漂移（只比语义骨架）", () => {
  assert.equal(SCHEMA.$schema, "https://json-schema.org/draft/2020-12/schema");
  assert.equal(SCHEMA.type, "object");

  // additionalProperties=false 是这篇文章的重点，必须在
  assert.equal(
    SCHEMA.additionalProperties,
    false,
    "schema 必须声明 additionalProperties=false，否则多塞字段不会被拦",
  );

  // 必填集合必须一致 —— 与 Pydantic 侧的 model_json_schema()["required"] 对齐：
  // role / tags 有默认值 -> 非必填。
  assert.deepEqual([...SCHEMA.required].sort(), ["email", "id", "username"]);

  // 逐字段语义骨架：类型 + 关键约束
  assert.equal(SCHEMA.properties.id.type, "integer");
  assert.equal(SCHEMA.properties.id.minimum, 1);

  assert.equal(SCHEMA.properties.username.type, "string");
  assert.equal(SCHEMA.properties.username.minLength, 3);
  assert.equal(SCHEMA.properties.username.maxLength, 32);
  assert.equal(SCHEMA.properties.username.pattern, "^[a-z0-9_]+$");

  assert.equal(SCHEMA.properties.email.type, "string");
  assert.ok(SCHEMA.properties.email.pattern, "email 必须有 pattern");

  assert.deepEqual(SCHEMA.properties.role.enum, ["admin", "member", "guest"]);

  assert.equal(SCHEMA.properties.tags.type, "array");
  assert.equal(SCHEMA.properties.tags.maxItems, 10);
  assert.equal(SCHEMA.properties.tags.items.type, "string");

  // 刻意**不**做逐字比对（比如不比对 description / $id / 键顺序）。
  // 逐字比对会让任何格式化改动都变成假警报，而契约测试要盯的是
  // **承诺**（类型、边界、枚举、必填），不是**排版**。
  // Python 版的 test_schema_does_not_drift_from_code 出于同样理由只比语义骨架。
});
