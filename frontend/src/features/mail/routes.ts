// 메일 화면 주소 규칙(components.md 4.1). 다른 화면(대시보드 · 알림 · 에이전트)도 이 함수로 주소를 만든다.
//   #/mail/<box>/<mailId>                   메일 하나
//   #/mail/<box>/<mailId>?reply=1           답장 쓰기
//   #/mail/<box>/<mailId>?reply=1&draft=…   답장 쓰기 + 내용 칸 미리 채움(에이전트 초안)
//   #/mail/<box>/<mailId>?compose=replyAll  전체 답장 · compose=forward 전달 (FE-18)
//   #/mail/<box>?compose=new                새 메일(고른 메일 없이)
//   navigate(mailPath(…), { state: { from: 'dashboard' } })  → 메일 화면 맨 위 [← 대시보드]
import type { ComposeMode } from '../../api/contract.ts';
import type { MailId } from '../../api/types.ts';

export interface MailPathOptions {
  /** 답장(compose: 'reply'와 같다) */
  reply?: boolean;
  compose?: ComposeMode;
  /** 답장 내용 칸에 미리 넣을 글(reply와 함께) */
  draft?: string;
}

export function mailPath(box: string, mailId?: MailId | number | null, opts: MailPathOptions = {}): string {
  const path = `/mail/${encodeURIComponent(box)}${mailId == null ? '' : `/${mailId}`}`;
  const mode = opts.compose ?? (opts.reply ? 'reply' : undefined);
  if (!mode || (mailId == null && mode !== 'new')) return path;
  const q = new URLSearchParams(mode === 'reply' ? { reply: '1' } : { compose: mode });
  if (opts.draft) q.set('draft', opts.draft);
  return `${path}?${q.toString()}`;
}

export interface ComposeParams {
  /** 쓰는 중이면 그 종류, 아니면 null */
  mode: ComposeMode | null;
  draft: string;
}

const MODES: readonly string[] = ['reply', 'replyAll', 'forward', 'new'] satisfies ComposeMode[];

export function readComposeParams(search: URLSearchParams): ComposeParams {
  const c = search.get('compose') ?? '';
  const mode = search.get('reply') === '1' ? 'reply' : MODES.includes(c) ? (c as ComposeMode) : null;
  return { mode, draft: search.get('draft') ?? '' };
}

/** 주소의 메일 번호. 숫자가 아니면 null(고른 메일 없음) */
export function parseMailId(value: string | undefined): MailId | null {
  if (value === undefined || !/^\d+$/.test(value)) return null;
  return Number(value) as MailId;
}

/** 넘어온 화면(라우터 state.from). 아는 화면만 [← 이름] 버튼을 보인다 */
const FROM_LABELS = { dashboard: '대시보드', settings: '설정', agent: '캐치봇' } as const;
export type FromScreen = keyof typeof FROM_LABELS;

export function readFrom(state: unknown): { key: FromScreen; label: string } | null {
  if (typeof state !== 'object' || state === null || !('from' in state)) return null;
  const from = (state as { from: unknown }).from;
  return from === 'dashboard' || from === 'settings' || from === 'agent' ? { key: from, label: FROM_LABELS[from] } : null;
}
