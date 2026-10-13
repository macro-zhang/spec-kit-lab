/**
 * REFACTOR 变体：行为一字不改，只改结构。
 *
 * 用一条整体正则 + 命名分组一次性判定"整串是否合法"，
 * 比 GREEN 版"先抓再拼回去比对"更直接：不合法就是压根匹配不上。
 * 这正是 Python 版 `variants/core_refactored.py` 的思路。
 *
 * 重构的底气来自测试：改完跑一遍，绿的就说明行为没变。
 */

export class DurationError extends RangeError {
  constructor(message) {
    super(message);
    this.name = "DurationError";
  }
}

const UNIT_SECONDS = Object.freeze({ d: 86400, h: 3600, m: 60, s: 1 });
// \A ... \Z 在 JS 里就是 ^ ... $（且不用 m 标志时 $ 只匹配串尾）
const FULL = /^(?<segments>(?:\d+[dhms])+)$/;
const SEGMENT = /(?<amount>\d+)(?<unit>[dhms])/g;

export function parseDuration(text) {
  if (typeof text !== "string" || text.length === 0) {
    throw new DurationError("时长不能为空");
  }
  if (!FULL.test(text)) {
    throw new DurationError(`时长含非法片段: ${JSON.stringify(text)}`);
  }

  let total = 0;
  for (const { groups } of text.matchAll(SEGMENT)) {
    total += Number(groups.amount) * UNIT_SECONDS[groups.unit];
  }
  return total;
}
