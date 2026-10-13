/**
 * GREEN 阶段的 Node 对应实现 —— 与 Python 版 `variants/core_green.py` 行为等价。
 *
 * 刻意保持"最笨但正确"：正则抓出所有 <数字><单位>，再拼回原文比对。
 * 朴素，但把契约写清楚比把代码写聪明重要得多。
 *
 * 契约（这就是"什么叫做对了"）：
 *   parseDuration(text: string): number   // 返回总秒数
 *   - 合法：一个或多个 <非负整数><单位 d|h|m|s> 的**无缝拼接**
 *   - 非法：抛 RangeError（对应 Python 版的 ValueError）
 *   - 非 string / 空串：非法
 */

const UNIT_SECONDS = Object.freeze({ d: 86400, h: 3600, m: 60, s: 1 });
const TOKEN = /(\d+)([dhms])/g;

export class DurationError extends RangeError {
  constructor(message) {
    super(message);
    this.name = "DurationError";
  }
}

/**
 * @param {unknown} text
 * @returns {number} 总秒数
 */
export function parseDuration(text) {
  if (typeof text !== "string" || text.length === 0) {
    throw new DurationError("时长不能为空");
  }

  // 全局正则带 g 标志 -> 有状态（lastIndex）。必须每次重置，
  // 否则连续两次调用会从上次的位置接着找 —— 这是 JS 里的经典陷阱，
  // Python 的 re.findall 没有这个问题。用 matchAll 更安全。
  TOKEN.lastIndex = 0;
  const tokens = [...text.matchAll(TOKEN)].map((m) => [m[1], m[2]]);

  if (tokens.length === 0) {
    throw new DurationError(`无法解析的时长: ${JSON.stringify(text)}`);
  }

  // 把识别到的片段原样拼回去。若与原文不符，说明夹了未识别的字符。
  const reconstructed = tokens.map(([amount, unit]) => `${amount}${unit}`).join("");
  if (reconstructed !== text) {
    throw new DurationError(`时长含非法片段: ${JSON.stringify(text)}`);
  }

  return tokens.reduce((sum, [amount, unit]) => sum + Number(amount) * UNIT_SECONDS[unit], 0);
}
