// 메일 속 이전 메일(인용) 나누기(AI-42). 아웃룩은 회신 · 전달할 때 가로줄 + '보낸 사람: · 보낸 날짜:'(영문 From: · Sent:) 머리를 붙이고,
// 데스크톱 · 옛 메일은 '-----Original Message-----'를 쓴다. 화면은 그 지점부터를 '이전 메일' 카드로 접어 지금 메일과 나눈다.

/** 인용 머리로 시작하나(가로줄 바로 뒤 글) */
export const startsQuoteHead = (text: string): boolean => /^\s*(보낸 사람|From)\s*:/.test(text);
/** 데스크톱 아웃룩 · 옛 메일의 원본 표시 */
export const ORIGINAL_MARK = /-{3,}\s*(Original Message|원본 메시지)\s*-{3,}/i;

const field = (text: string, names: string): string | null => {
  const m = new RegExp(`(?:${names})\s*:\s*(.+?)(?=\s*(?:보낸 사람|보낸 날짜|받는 사람|참조|제목|From|Sent|Date|To|Cc|Subject)\s*:|$)`, 's').exec(text);
  return m?.[1]?.replace(/\s+/g, ' ').trim() || null;
};

/** 인용 머리 글에서 보낸 사람 · 보낸 날짜(카드 제목). 이름 <주소>면 이름만 */
export function parseQuoteHead(text: string): { from: string | null; sent: string | null } {
  const head = text.slice(0, 600);
  const from = field(head, '보낸 사람|From');
  return { from: from?.replace(/\s*<[^>]*>\s*$/, '').trim() || from, sent: field(head, '보낸 날짜|Sent|Date') };
}
