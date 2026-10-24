/**
 * 跨语言契约校验器 —— 手写，零依赖。
 *
 * ## 为什么手写而不用 ajv / zod？
 *
 * 这不是偷懒，是在复刻 spec-kit 的真实做法。spec-kit 的 `tests/contract/` 里
 * **既没有 jsonschema 也没有 pydantic**（全仓 jsonschema 零命中）：它的 schema
 * 本体是 markdown 文档 `contracts/*.schema.md`，而**测试就是唯一的执行器** ——
 * `BundleManifest.from_dict(data).structural_errors()` 返回一个 `list[str]`。
 *
 * 这里用同一套形态：`structuralErrors(data)` 返回 `string[]`。
 * 空数组 = 通过。这个签名比"抛异常"或"返回 boolean"都好用，
 * 因为你能一次性把所有违规都报出来，而不是撞到第一个就停。
 *
 * ## 契约的三种表达，各自负责什么
 *
 *   1. 文档形态：`../contracts/user-profile.schema.json`（跨语言、给外部看的承诺）
 *   2. 代码形态：本文件（Node 侧的运行时守卫）
 *   3. 测试形态：`../test/contract.test.mjs`（证明前两者没漂移）
 *
 * 三份东西必须**语义一致**，但**不必逐字一致** —— 见测试里的漂移检查。
 */

const ROLES = Object.freeze(["admin", "member", "guest"]);

// 必填的四个：id / username / email / locale —— locale 无默认值，调用方必须给。
// role / tags 在实现里有默认值 -> 对调用方可省略，因此**不能**列进 required。
// 这正是 Python 侧第一次跑红的那个漂移：代码给了默认值、schema 却写
// required，两边说法不一致。
export const REQUIRED = Object.freeze(["id", "username", "email", "locale"]);

// 允许出现的字段全集。注意它和 REQUIRED 是**两个不同的集合**：
// 「可以出现」不等于「必须出现」。把这两个概念混成一个变量，
// 就会同时犯"必填漏检"和"可选字段被误报未知"两种错。
const ALLOWED = Object.freeze(["id", "username", "email", "locale", "role", "tags"]);

const USERNAME_RE = /^[a-z0-9_]+$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/;
const TAG_RE = /^[a-z0-9_-]+$/;
const LOCALE_RE = /^[a-z]{2}_[A-Z]{2}$/;

const isPlainObject = (v) =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * 纯结构校验，不做任何类型转换。
 *
 * @param {unknown} data
 * @returns {string[]} 违规清单；空数组表示通过
 */
export function structuralErrors(data) {
  const errors = [];

  if (!isPlainObject(data)) {
    // 这一行是 spec-kit 测试里被反复参数化的那种边界：
    // JSON.parse 永远不会给你 null/数组当顶层，但**调用方**会。
    // 写法上要小心 `data || {}` 这种"顺手兜底" —— 它会把
    // [] / "" / 0 / false 一起吞掉，于是错误数据被静默当成"空对象通过"。
    // spec-kit 专门为此参数化了 [[], "", 0, False] 四个输入断言必须报错。
    return [`顶层必须是对象，实际是 ${describe(data)}`];
  }

  // ── 未知字段：必须报错，不能静默丢弃 ──────────────────────────────
  // 对应 Pydantic 的 extra="forbid"。默认行为（丢弃多余字段）很危险：
  // 模型幻觉多塞一个字段时，你会得到"成功但语义错了"的结果。
  for (const key of Object.keys(data)) {
    if (!ALLOWED.includes(key)) {
      errors.push(`未知字段 ${JSON.stringify(key)}：契约 additionalProperties=false`);
    }
  }

  // ── 必填 ──────────────────────────────────────────────────────────
  for (const key of REQUIRED) {
    if (!(key in data)) {
      errors.push(`缺少必填字段 ${JSON.stringify(key)}`);
    }
  }

  // ── id ───────────────────────────────────────────────────────────
  if ("id" in data) {
    const v = data.id;
    if (!Number.isInteger(v)) {
      errors.push(`id 必须是整数，实际是 ${describe(v)}`);
    } else if (v < 1) {
      errors.push(`id 必须 >= 1，实际是 ${v}`);
    }
  }

  // ── username ─────────────────────────────────────────────────────
  if ("username" in data) {
    const v = data.username;
    if (typeof v !== "string") {
      errors.push(`username 必须是字符串，实际是 ${describe(v)}`);
    } else if (v.length < 3 || v.length > 32) {
      errors.push(`username 长度必须在 3..32，实际是 ${v.length}`);
    } else if (!USERNAME_RE.test(v)) {
      errors.push(`username 必须匹配 ${USERNAME_RE}：${JSON.stringify(v)}`);
    }
  }

  // ── email ────────────────────────────────────────────────────────
  if ("email" in data) {
    const v = data.email;
    if (typeof v !== "string") {
      errors.push(`email 必须是字符串，实际是 ${describe(v)}`);
    } else if (!EMAIL_RE.test(v)) {
      errors.push(`email 格式不合法：${JSON.stringify(v)}`);
    }
  }

  // ── locale ───────────────────────────────────────────────────────
  if ("locale" in data) {
    const v = data.locale;
    if (typeof v !== "string") {
      errors.push(`locale 必须是字符串，实际是 ${describe(v)}`);
    } else if (!LOCALE_RE.test(v)) {
      errors.push(`locale 必须形如 zh_CN（小写2_大写2）：${JSON.stringify(v)}`);
    }
  }

  // ── role ─────────────────────────────────────────────────────────
  if ("role" in data) {
    const v = data.role;
    // 注意这里拒绝的是"不在枚举里"，而不是"不是字符串"——
    // 因为 null / 数字都不在枚举里，一条规则就覆盖了。
    if (!ROLES.includes(v)) {
      errors.push(`role 必须是 ${ROLES.join("|")} 之一，实际是 ${JSON.stringify(v)}`);
    }
  }

  // ── tags ─────────────────────────────────────────────────────────
  if ("tags" in data) {
    const v = data.tags;
    if (!Array.isArray(v)) {
      errors.push(`tags 必须是数组，实际是 ${describe(v)}`);
    } else if (v.length > 10) {
      errors.push(`tags 最多 10 个，实际是 ${v.length} 个`);
    } else {
      v.forEach((tag, i) => {
        if (typeof tag !== "string" || !TAG_RE.test(tag)) {
          errors.push(`tags[${i}] 必须匹配 ${TAG_RE}：${JSON.stringify(tag)}`);
        }
      });
    }
  }

  return errors;
}

/** 给人看的类型描述，比 typeof 更有信息量（typeof null === "object" 是 JS 的著名坑）。 */
export function describe(v) {
  if (v === null) return "null";
  if (Array.isArray(v)) return `array(${v.length})`;
  if (typeof v === "number") return `number(${v})`;
  if (typeof v === "string") return `string(${JSON.stringify(v)})`;
  return typeof v;
}

/** 组合式：通过就返回值，不通过就抛出带完整清单的错误。 */
export function assertProfile(data) {
  const errors = structuralErrors(data);
  if (errors.length > 0) {
    throw new Error(`UserProfile 契约违规:\n  - ${errors.join("\n  - ")}`);
  }
  return data;
}
