// 설정 화면 값 바꾸기(화면 지식 없이 시험할 수 있게 .ts로 둔다)

/** "1-5" · "1,3,5" → {1..7}. 서버 policy.parse_days와 같은 형식 */
export function parseDays(value: string): Set<number> {
  const out = new Set<number>();
  for (const part of value.split(',')) {
    const [a, b] = part.split('-').map(Number);
    if (!a) continue;
    for (let d = a; d <= (b ?? a); d++) if (d >= 1 && d <= 7) out.add(d);
  }
  return out;
}

export const formatDays = (days: Set<number>) => [...days].sort((a, b) => a - b).join(',');

const KST_MS = 9 * 3600_000;
/** <input type="datetime-local">의 값(한국 시각, 초 없음) */
export const toKstLocal = (ms: number) => new Date(ms + KST_MS).toISOString().slice(0, 16);
export const fromKstLocal = (v: string) => Date.parse(`${v}:00+09:00`);
