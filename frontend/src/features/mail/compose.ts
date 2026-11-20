// 답장 쓰기의 판단(wireframe 13-5 · UX-D5 · UX-D14): 제목 · 받는 사람 표시 · 템플릿 미리보기.
// 사용자는 하고 싶은 말만 쓰고, 템플릿의 인사 · 맺음 · 서명 사이에 넣어 보여 준다. 템플릿을 바꿔도 쓴 말은 그대로다.
import type { ReplyTemplate } from '../../api/contract.ts';
import type { Contact } from '../../api/types.ts';

/** 제목: RE: {원메일제목}. 이미 RE:로 시작하면 그대로(RE: RE: 를 만들지 않는다) */
export function replySubject(subject: string): string {
  const s = subject.trim();
  return /^re\s*:/i.test(s) ? s : `RE: ${s}`;
}

/** 전달 제목: FW: {원메일제목}. 이미 FW: · FWD:로 시작하면 그대로 */
export function forwardSubject(subject: string): string {
  const s = subject.trim();
  return /^fwd?\s*:/i.test(s) ? s : `FW: ${s}`;
}

/**
 * 주소 칸 글 → 주소 목록(FE-18). 쉼표 · 세미콜론 · 공백 · 줄바꿈으로 나눈다. 같은 주소는 한 번만.
 * Outlook에서 복사한 `홍길동 <a@x.com>`은 꺾쇠 안 주소만 쓴다(이름은 쉼표 · 세미콜론 · 줄 첫머리부터, @가 없을 때만 버린다).
 * bad = 메일 주소 형식이 아닌 것(서버 reply.py _check_addresses와 같은 기준: @ 하나, 앞뒤가 @가 아님, 꺾쇠 · 따옴표 없음, 255자 이하)
 */
export function parseAddresses(text: string): { ok: string[]; bad: string[] } {
  const ok: string[] = [];
  const bad: string[] = [];
  const flat = text.replace(/(^|[,;\n])(?:"[^"]*"|[^<>,;@\n"])*<([^<>]*)>/g, '$1 $2 ');
  for (const a of flat.split(/[,;\s]+/)) {
    if (!a) continue;
    const valid = a.length <= 255 && a.split('@').length === 2 && !a.startsWith('@') && !a.endsWith('@') && !/[<>"]/.test(a);
    if (!valid) bad.push(a);
    else if (!ok.some((o) => o.toLowerCase() === a.toLowerCase())) ok.push(a);
  }
  return { ok, bad };
}

/** 보내기 실패 안내. retry = [다시 시도]를 보일지 — 보내졌는지 모를 때는 두 번 나가지 않게 보이지 않는다 */
export interface SendFailure {
  title: string;
  description?: string;
  retry: boolean;
}

/** status: HTTP 상태(HttpError), 'network' = 응답을 받지 못함(연결 끊김 · 제한 시간 초과) */
export function sendFailure(status: number | 'network'): SendFailure {
  // 504: 서버가 Outlook 응답을 못 받음. network: 우리가 서버 응답을 못 받음. 502(Outlook 거절) · 503(보내기 전 포기)이 아닌
  // 5xx도 어디서 끊겼는지 모른다 — 모두 메일이 나갔을 수 있다
  if (status === 'network' || (status >= 500 && status !== 502 && status !== 503)) {
    return { title: '보냈는지 확인하지 못했습니다', description: '보낸 편지함을 확인한 뒤 필요하면 다시 보내 주세요', retry: false };
  }
  if (status === 409) return { title: '보내지 못했습니다', description: '설정 > 메일 계정에서 Outlook을 다시 연결해 주세요', retry: false };
  if (status === 422) return { title: '보내지 못했습니다', description: '받는 사람 주소와 내용을 확인해 주세요', retry: false };
  return { title: '보내지 못했습니다', retry: true };
}

/** 받는 사람 표시 이름: 이름 + 직책(예: 김민준 팀장). 이름이 없으면 주소 */
export function recipientName(contact: Contact | undefined, email: string): string {
  const name = contact?.name?.trim();
  if (!name) return email;
  const position = contact?.position?.trim();
  return position ? `${name} ${position}` : name;
}

export interface TemplateVars {
  /** {수신자명}: 답장을 받는 사람(원메일 발신자) */
  recipient: string;
  /** {발신자명}: 나. 모르면 null — 자리표시를 지어내지 않고 그대로 둔다 */
  sender: string | null;
  /** {원메일제목} */
  subject: string;
}

/** 미리보기 세 조각. content가 사용자가 쓴 부분(밑줄) */
export interface ReplyParts {
  before: string;
  content: string;
  after: string;
}

const CONTENT = '{내용}';

function fill(text: string, vars: TemplateVars): string {
  let out = text.replaceAll('{수신자명}', vars.recipient).replaceAll('{원메일제목}', vars.subject);
  if (vars.sender !== null) out = out.replaceAll('{발신자명}', vars.sender);
  return out.replaceAll(CONTENT, ''); // 쓴 글 자리는 첫 {내용} 하나. 자유 글 틀에 두 번 써도 나머지가 메일에 나가지 않게
}

/**
 * 템플릿에 쓴 말을 넣는다. 템플릿의 pattern에서 {내용} 자리 앞뒤를 채우고, 쓴 말은 따로 둔다(미리보기 밑줄 · 템플릿을 바꿔도 그대로).
 * pattern에 {내용}이 없으면 템플릿 글 뒤에 빈 줄을 두고 쓴 말을 붙인다. 템플릿이 없으면 쓴 말만.
 */
export function renderReply(template: ReplyTemplate | null, vars: TemplateVars, content: string): ReplyParts {
  if (!template) return { before: '', content, after: '' };
  const at = template.pattern.indexOf(CONTENT);
  if (at < 0) return { before: `${fill(template.pattern, vars)}\n\n`, content, after: '' };
  return {
    before: fill(template.pattern.slice(0, at), vars),
    content,
    after: fill(template.pattern.slice(at + CONTENT.length), vars),
  };
}

/** 보낼 본문 전체(미리보기에 보인 글자 그대로) */
export const replyText = (parts: ReplyParts): string => `${parts.before}${parts.content}${parts.after}`;

/** 쓰던 답장이 있는가(떠날 때 '버릴까요?'를 물을지) */
export const hasDraft = (content: string): boolean => content.trim() !== '';

/** 다듬기 결과를 넣어도 되는가: 요청한 뒤 글이 바뀌었으면(더 쓰거나 말했으면) 덮어쓰지 않는다(#193 리뷰) */
export const canApplyPolish = (before: string, current: string): boolean => before === current;
