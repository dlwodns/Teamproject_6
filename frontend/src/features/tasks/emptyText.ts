// 빈 칸 안내 문구. 왼쪽 칸은 aggregate.ts의 실제 포함 조건대로 풀어 쓰고,
// 오른쪽 칸은 "○○으로/로 분류된"으로 쓴다(조사는 받침 없음 · ㄹ 받침 → '로', 그 밖의 받침 → '으로').

const HANGUL_FIRST = 0xac00;
const HANGUL_LAST = 0xd7a3;
const RIEUL_FINAL = 8; // 종성 ㄹ

export function withRo(word: string): string {
  const code = word.charCodeAt(word.length - 1);
  if (Number.isNaN(code) || code < HANGUL_FIRST || code > HANGUL_LAST) return `${word}(으)로`;
  const final = (code - HANGUL_FIRST) % 28;
  return final === 0 || final === RIEUL_FINAL ? `${word}로` : `${word}으로`;
}

// aggregate.ts buildDashboard: due = 기한 지남 · 오늘 마감(기한 남음) · 내일 마감, superior · favorite = 발신자 연락처 표시
const PRIORITY_EMPTY: Record<string, string> = {
  due: '기한이 지났거나 오늘·내일 마감인 미처리 업무가 없습니다.',
  superior: '상급자가 보낸 메일에서 나온 미처리 업무가 없습니다.',
  favorite: '즐겨찾기한 발신자의 메일에서 나온 미처리 업무가 없습니다.',
};

export function emptyColumnText(key: string, label: string): string {
  return PRIORITY_EMPTY[key] ?? `${withRo(label)} 분류된 미처리 업무가 없습니다.`;
}
