/** RED 变体：只有骨架，任何调用都失败。 */
export class DurationError extends RangeError {}

export function parseDuration() {
  throw new DurationError("RED：尚未实现");
}
