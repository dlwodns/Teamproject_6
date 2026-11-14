// 모의 모드의 에이전트 패널 규칙: 제안 카드 판정 · 기록 문장 · 기억 문구.
// backend/app/services/suggestions.py · history.py · memory.py를 그대로 옮겼다(문구 · 순서 · 키 형식이 같아야
// 모의에서 본 화면이 실제 서버에서도 같다). 서버 응답 모양(snake_case · +09:00 ISO)을 만들고, 화면 모델 변환은 adapter가 한다.
// 순수 함수라 node --test로 모의 v2 데이터에 대해 바로 시험한다(agentPanelRules.test.ts).
//
// 모의 데이터에 없는 것은 만들지 않는다:
// - ⑤ 일정 참석(meeting): 메일 성격(mails.kind K09) 칸이 모의에 없고 backend도 아직 만들지 않는다 → 띄우지 않음
// - ④의 ASAP 조건: backend가 아직 붙이지 않았다(계약 4절) → 상급자 조건만 본다
import { toKstIso } from '../adapter.ts';
import type {
  ProvisionalContact,
  ProvisionalDashboardResponse,
  ProvisionalMail,
  ProvisionalSuggestion,
  ProvisionalSuggestionButton,
  ProvisionalTask,
} from '../provisional.ts';

const HOUR = 3600_000;
const DAY = 24 * HOUR;
const KST = 9 * HOUR;
export const DUE_SOON_MS = 24 * HOUR; // 계약 4절 ③
export const SUPERIOR_AFTER_MS = 2 * HOUR; // 계약 4절 ④
export const SUGGESTION_ORDER = ['morning', 'overdue', 'due_soon', 'priority_sender', 'meeting', 'no_reply'] as const;
const DRAFT_CATEGORIES = ['회신', '요청', '검토'];
const REPLY_PREFIX = /^\s*(re|fw|fwd|회신|답장|전달)\s*[:：]/i;
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
export const SUGGESTION_KEY = /^(morning|overdue|due_soon|priority_sender|meeting|no_reply):[0-9A-Za-z:_-]{1,80}$/;
export const NO_REPLY_KEY = 'no_reply:waiting';

// ── KST 시계 ──

const kstDay = (ms: number) => Math.floor((ms + KST) / DAY);
const kstAt = (day: number, hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return day * DAY - KST + (h ?? 0) * HOUR + (m ?? 0) * 60_000;
};
const kstParts = (ms: number) => {
  const d = new Date(ms + KST);
  return { month: d.getUTCMonth() + 1, date: d.getUTCDate(), wd: d.getUTCDay(), hm: d.toISOString().slice(11, 16) };
};
const isoDay = (ms: number) => new Date(ms + KST).toISOString().slice(0, 10);

/** 숨김이 풀리는 때: 다음 R-아침. 그때까지 1시간도 안 남았으면 그다음 날 R-아침(suggestions.next_morning) */
export function nextMorningMs(atMs: number, remind: string): number {
  const today = kstAt(kstDay(atMs), remind);
  const until = atMs < today ? today : today + DAY;
  return until - atMs >= HOUR ? until : until + DAY;
}

function when(dueMs: number, atMs: number): string {
  const p = kstParts(dueMs);
  const gap = kstDay(dueMs) - kstDay(atMs);
  if (gap === 0) return `오늘 ${p.hm}`;
  if (gap === 1) return `내일 ${p.hm}`;
  return `${p.month}/${p.date}(${WEEKDAYS[p.wd]}) ${p.hm}`;
}

export function shortText(text: string, n: number): string {
  const t = text.split(/\s+/).filter(Boolean).join(' ');
  return t.length <= n ? t : `${t.slice(0, n - 1)}…`;
}

function who(mail: ProvisionalMail, contact: ProvisionalContact | undefined): string {
  const name = contact?.name || mail.sender.split('@')[0];
  return contact?.position ? `${name} ${contact.position}님` : `${name}님`;
}

// ── 버튼 ──

function btn(
  label: string,
  action: string,
  o: { taskIds?: number[]; mailIds?: number[]; params?: Record<string, unknown>; primary?: boolean; kind?: string } = {},
): ProvisionalSuggestionButton {
  return {
    label,
    kind: o.kind ?? 'action',
    action,
    primary: o.primary ?? false,
    params: o.params ?? {},
    target: { task_ids: o.taskIds ?? [], mail_ids: o.mailIds ?? [] },
  };
}

const HIDE = () => btn('이 제안 숨기기', 'hide', { kind: 'hide' });

function taskButtons(task: ProvisionalTask, mail: ProvisionalMail) {
  const ids = { taskIds: [task.id], mailIds: [mail.id] };
  const first =
    mail.category && DRAFT_CATEGORIES.includes(mail.category)
      ? btn('초안 보기', 'T07', { ...ids, params: { tone: 'polite' }, primary: true })
      : btn('메일 열기', 'open_mail', { ...ids, primary: true, kind: 'navigate' });
  return {
    buttons: [first, btn('나중에', 'T05', { ...ids, params: { until: null } }), btn('완료', 'T03', ids)],
    menu: [btn('업무 아님', 'T10', ids), HIDE()],
  };
}

type Sort = number[];
type Card = ProvisionalSuggestion & { sort: Sort };

function card(
  key: string,
  rule: string,
  createdMs: number,
  title: string,
  buttons: ProvisionalSuggestionButton[],
  o: { menu?: ProvisionalSuggestionButton[]; taskIds?: number[]; mailIds?: number[]; detail?: string[]; sort: Sort },
): Card {
  return {
    key,
    rule,
    via: `suggestion:${rule}`,
    created_at: toKstIso(createdMs),
    title,
    detail: o.detail ?? [],
    task_ids: o.taskIds ?? [],
    mail_ids: o.mailIds ?? [],
    buttons,
    menu: o.menu ?? [HIDE()],
    sort: o.sort,
  };
}

// ── 판정 ──

export interface HideRow {
  untilMs: number;
  mailIds: number[];
}

export interface SuggestionInput {
  data: ProvisionalDashboardResponse;
  nowMs: number;
  /** 설정 remind_time(HH:MM) */
  remindTime: string;
  /** 설정 awaiting_reply_days(0 이하는 1) */
  awaitDays: number;
  /** 업무의 나중에 시각(모의 상태). 모르면 null → 나중에 업무는 미처리로 보지 않는다 */
  snoozedUntilMs: (taskId: number) => number | null;
  hides: ReadonlyMap<string, HideRow>;
}

const ms = (iso: string) => Date.parse(iso);

/** 미처리 업무: pending, 또는 나중에인데 그 시각이 지난 것. 받은 메일의 업무만 */
export function openTasks(input: SuggestionInput): [ProvisionalTask, ProvisionalMail][] {
  const mails = new Map(input.data.mails.map((m) => [m.id, m]));
  const out: [ProvisionalTask, ProvisionalMail][] = [];
  for (const t of input.data.tasks) {
    const m = mails.get(t.mail_id);
    if (!m || m.direction !== 'received') continue;
    const until = input.snoozedUntilMs(t.id);
    if (t.status === 'pending' || (t.status === 'snoozed' && until !== null && until <= input.nowMs)) out.push([t, m]);
  }
  return out;
}

function since(task: ProvisionalTask, mail: ProvisionalMail, formula: number, input: SuggestionInput): number {
  const marks = [formula, ms(mail.received_at)];
  const until = input.snoozedUntilMs(task.id);
  if (task.status === 'snoozed' && until !== null) marks.push(until);
  return Math.max(...marks);
}

function taskCard(task: ProvisionalTask, mail: ProvisionalMail, contact: ProvisionalContact | undefined, input: SuggestionInput): Card | null {
  const at = input.nowMs;
  const name = who(mail, contact);
  const what = shortText(task.text, 30);
  const { buttons, menu } = taskButtons(task, mail);
  const common = { menu, taskIds: [task.id], mailIds: [mail.id] };
  const due = task.due_at === null ? null : ms(task.due_at);
  const sent = ms(mail.received_at);
  if (due !== null && due < at) {
    const days = kstDay(at) - kstDay(due);
    const late = days >= 1 ? `기한이 D+${days} 지났어요` : `기한(${kstParts(due).hm})이 지났어요`;
    return card(`overdue:task:${task.id}`, 'overdue', since(task, mail, due, input), `${name} '${what}' ${late}.`, buttons, {
      ...common,
      sort: [due, sent],
    });
  }
  if (due !== null && due - at <= DUE_SOON_MS) {
    const ask = buttons[0]!.action === 'T07' ? '초안을 써 둘까요?' : '메일을 확인해 볼까요?';
    return card(
      `due_soon:task:${task.id}`,
      'due_soon',
      since(task, mail, due - DUE_SOON_MS, input),
      `${name} '${what}' 기한이 ${when(due, at)}이에요. ${ask}`,
      buttons,
      { ...common, sort: [due, sent] },
    );
  }
  if (contact?.is_superior && at - sent >= SUPERIOR_AFTER_MS) {
    const hours = Math.floor((at - sent) / HOUR);
    const ago = hours < 24 ? `${hours}시간` : `${Math.floor(hours / 24)}일`;
    return card(
      `priority_sender:task:${task.id}`,
      'priority_sender',
      since(task, mail, sent + SUPERIOR_AFTER_MS, input),
      `${name} 메일을 받은 지 ${ago} 지났어요.`,
      buttons,
      { ...common, sort: [due ?? Number.MAX_SAFE_INTEGER, sent] },
    );
  }
  return null;
}

/** 그날 아침 요약 창: R-아침부터 정오 전. 정오까지 1시간이 안 남으면 R-아침부터 4시간 */
function morningWindow(day: number, remind: string): [number, number] {
  const start = kstAt(day, remind);
  const noon = kstAt(day, '12:00');
  return [start, noon - start >= HOUR ? noon : start + 4 * HOUR];
}

function morning(open: [ProvisionalTask, ProvisionalMail][], input: SuggestionInput): Card | null {
  if (open.length === 0) return null;
  const at = input.nowMs;
  let start: number | null = null;
  for (const day of [kstDay(at), kstDay(at) - 1]) {
    const [s, e] = morningWindow(day, input.remindTime);
    if (s <= at && at < e) {
      start = s;
      break;
    }
  }
  if (start === null) return null;
  const today = open.filter(([t]) => t.due_at !== null && kstDay(ms(t.due_at)) === kstDay(at)).length;
  const day = isoDay(start);
  return card(`morning:${day}`, 'morning', start, `오늘 챙길 업무 ${open.length}건, 그중 오늘 마감 ${today}건이에요.`, [
    btn('오늘 요약 보기', 'T01', { params: { date: day }, primary: true }),
  ], { sort: [start] });
}

/** 응답 대기: 모의는 응답 대기 목록(awaiting, 이미 답이 없는 보낸 메일)에서 기준일이 지난 요청 메일만 */
function noReply(input: SuggestionInput): Card | null {
  const days = Math.max(1, input.awaitDays);
  const limit = input.nowMs - days * DAY;
  const waiting = (input.data.awaiting ?? [])
    .filter((a) => ms(a.sent_at) <= limit && !REPLY_PREFIX.test(a.subject))
    .sort((a, b) => ms(a.sent_at) - ms(b.sent_at) || a.mail_id - b.mail_id);
  if (waiting.length === 0) return null;
  const ids = waiting.map((a) => a.mail_id);
  return card(
    NO_REPLY_KEY,
    'no_reply',
    ms(waiting[waiting.length - 1]!.sent_at) + days * DAY,
    `보낸 요청 ${waiting.length}건에 ${days}일 넘게 답이 없어요.`,
    [btn('응답 대기 보기', 'T06', { mailIds: ids, primary: true })],
    { mailIds: ids, detail: waiting.slice(0, 3).map((a) => shortText(a.subject || '(제목 없음)', 40)), sort: [ms(waiting[0]!.sent_at)] },
  );
}

function compareSort(a: Sort, b: Sort): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

function isHidden(c: Card, h: HideRow | undefined, nowMs: number): boolean {
  if (!h || h.untilMs <= nowMs) return false;
  if (c.rule === 'no_reply') return c.mail_ids.every((id) => h.mailIds.includes(id));
  return true;
}

/** 지금 띄울 카드 전체(숨긴 것 제외), 표시 순서대로(suggestions.compute) */
export function computeSuggestions(input: SuggestionInput): ProvisionalSuggestion[] {
  const open = openTasks(input);
  const contacts = new Map(input.data.contacts.map((c) => [c.email.toLowerCase(), c]));
  const cards: Card[] = [];
  const m = morning(open, input);
  if (m) cards.push(m);
  for (const [t, mail] of open) {
    const c = taskCard(t, mail, contacts.get(mail.sender.toLowerCase()), input);
    if (c) cards.push(c);
  }
  const n = noReply(input);
  if (n) cards.push(n);
  return cards
    .filter((c) => !isHidden(c, input.hides.get(c.key), input.nowMs))
    .sort((a, b) => SUGGESTION_ORDER.indexOf(a.rule as never) - SUGGESTION_ORDER.indexOf(b.rule as never) || compareSort(a.sort, b.sort))
    .map(({ sort: _sort, ...c }) => c);
}

/** 숨길 때 남길 것: 끝 시각과 응답 대기면 그때 기다리던 메일 */
export function hideRow(key: string, input: SuggestionInput): HideRow {
  return { untilMs: nextMorningMs(input.nowMs, input.remindTime), mailIds: key === NO_REPLY_KEY ? (noReply(input)?.mail_ids ?? []) : [] };
}

// ── 기록 탭 문구(history.py) ──

const RULE_LABEL: Record<string, string> = {
  morning: '아침 요약',
  overdue: '기한 지남',
  due_soon: '기한 임박',
  priority_sender: '상급자',
  meeting: '일정 참석',
  no_reply: '응답 대기',
};
const SOURCE_LABEL: Record<string, string> = {
  agent_rule: '말로 시킴',
  agent_model: '말로 시킴',
  mcp: 'MCP',
  reply_auto: '자동',
  calendar_auto: '자동',
  mail_learn: '메일에서 알게 됨',
  ui: '화면 버튼',
};
export const AUTO_SOURCES = ['reply_auto', 'calendar_auto', 'mail_learn'];
const STATUS_WORD: Record<string, string> = { done: '완료', excluded: '목록에서 빼기', snoozed: '미루기', pending: '미처리로 돌리기' };

/** [코드, 화면 문구](history.label) */
export function viaLabel(via: string | null, source: string, memoryTarget = false): [string, string] {
  if (via === 'mail_learn') return [via, '메일에서 알게 됨'];
  if (via?.startsWith('suggestion:')) {
    const rule = via.split(':')[1] ?? '';
    return [via, `제안 카드(${RULE_LABEL[rule] ?? rule})`];
  }
  if (via === 'history') return [via, '기록 탭'];
  if (memoryTarget) return ['memory', source === 'ui' ? '에이전트가 아는 것' : (SOURCE_LABEL[source] ?? source)];
  return [source, SOURCE_LABEL[source] ?? source];
}

const mdhm = (ms: number) => {
  const p = kstParts(ms);
  return `${p.month}/${p.date} ${p.hm}`;
};

/** 업무 변경 한 줄(history._task_text) */
export function taskHistoryText(texts: readonly string[], status: string, snoozedUntilMs: number | null, action: string): string {
  const subject = texts.length === 1 ? `'${shortText(texts[0]!, 24)}' 업무를` : `업무 ${texts.length}건을`;
  if (status === 'done') return `${subject} 완료했어요`;
  if (status === 'excluded') return `${subject} 목록에서 뺐어요(업무 아님)`;
  if (status === 'snoozed') return snoozedUntilMs === null ? `${subject} 미뤘어요` : `${subject} ${mdhm(snoozedUntilMs)}까지 미뤘어요`;
  if (status === 'pending') return `${subject} 다시 미처리로 돌렸어요`;
  return `${subject} 바꿨어요(${action})`;
}

/**
 * 항목(업무 · 기억)마다 지금 되돌릴 수 있는 행동 id(task_status._top_actions · memory.top_actions).
 * 기록을 차례로 다시 훑는다: 보통 행동은 쌓고, 되돌리기는 그 행동을 빼고, 되돌리기를 되돌리면(다시 하기) 뺀 행동을 다시 쌓는다
 */
export function topActions(actions: readonly { id: number; kind: 'change' | 'undo'; undoneId: number | null; keys: string[] }[]): Map<string, number> {
  const stacks = new Map<string, number[]>();
  const byId = new Map(actions.map((a) => [a.id, a]));
  for (const a of actions) {
    for (const k of a.keys) {
      const st = stacks.get(k) ?? [];
      stacks.set(k, st);
      if (a.kind === 'change') st.push(a.id);
      else {
        const target = a.undoneId === null ? undefined : byId.get(a.undoneId);
        if (!target) continue;
        if (target.kind === 'undo') {
          if (target.undoneId !== null) st.push(target.undoneId);
        } else if (st[st.length - 1] === target.id) st.pop();
      }
    }
  }
  const top = new Map<string, number>();
  for (const [k, st] of stacks) if (st.length) top.set(k, st[st.length - 1]!);
  return top;
}

/** 확인 기다림 한 줄 */
export function waitingHistoryText(count: number, status: string): string {
  return `업무 ${count}건 ${STATUS_WORD[status] ?? status} — 확인을 기다려요`;
}

/** 기억 변경 한 줄(memory.describe, 화면 · 말로 바꾼 것) */
export function memoryHistoryText(action: 'memory_me' | 'memory_people', source: string): string {
  if (action === 'memory_me') return '내 정보(직책 · 팀 · 배포 목록)를 바꿨어요';
  return source === 'agent_rule' || source === 'agent_model' ? '에이전트에게 말해 중요한 사람으로 정했어요' : '중요한 사람 표시를 바꿨어요';
}

// ── 에이전트가 아는 것 문구(memory.py) ──

export const MEMORY_USED_BY = {
  me: ['메일 분류'],
  superior: ['제안 카드', '메일 분류'],
  favorite: ['메일 분류'],
  facts: ['제안 카드'],
} as const;

export const MEMORY_USES = {
  me: '직책 · 팀 배포 목록으로 온 지시는 나에게 온 것으로 보고 할 일로 잡아요.',
  superior: '상급자 메일은 우선순위를 높이고, 받은 지 2시간이 넘도록 처리하지 않으면 제안 카드로 알려 드려요.',
  favorite: '즐겨찾기한 분의 메일은 우선순위를 높여요.',
  facts: '제안 카드에 이름과 함께 맡은 일이나 소속을 보여 드려요.',
} as const;

export const FIRST_ORIGIN = '처음 설정에서 넣었어요';

/** 항목이 마지막으로 바뀐 때 한 줄(memory._how). kind: 보통 변경 · 되돌림 · 다시 함 */
export function originText(atMs: number, source: string, kind: 'change' | 'undo' | 'redo'): string {
  const p = kstParts(atMs);
  const whom =
    source === 'agent_rule' || source === 'agent_model' ? '에이전트에게 말해서' : source === 'mcp' ? '다른 도구(MCP)에서' : '화면에서';
  const verb = kind === 'undo' ? '되돌렸어요' : kind === 'redo' ? '다시 했어요' : '바꿨어요';
  return `${p.month}/${p.date} ${whom} ${verb}`;
}

/** 배포 목록 종류를 주소로 짐작(memory.list_kind) */
export function guessListKind(address: string): 'role' | 'team' | 'all' {
  const local = (address.split('@')[0] ?? '').toLowerCase();
  const words = local.replace(/[_.]/g, '-').split('-').filter(Boolean);
  const role = ['leader', 'lead', 'head', 'manager', 'chief', '팀장', '리더'];
  const all = ['all', 'everyone', 'staff', 'notice', 'company', '전사', '전체'];
  if (words.some((w) => role.some((r) => w.startsWith(r)))) return 'role';
  if (words.some((w) => all.includes(w) || w.startsWith('all'))) return 'all';
  return 'team';
}

/** 배포 목록 주소 형식(agent_panel.ADDRESS) */
export const LIST_ADDRESS = /^[^@\s,;<>"']+@[^@\s,;<>"']+$/;
