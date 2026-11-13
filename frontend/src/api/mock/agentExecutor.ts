// 모의 에이전트 실행기 — 해석 결과(PlanResponse) → AgentResult 서버 형식(snake_case).
// backend/app/agent/executor.py · resolve.py · policy.py(BE-11 #50)를 그대로 옮겼다. 제목 · 되묻기 문구 · 확인 판정(D37)도 같다.
// 상태 바꾸기 · 미리보기 · 되돌리기는 mockClient의 BE-4 흉내(store)만 쓴다. 이 파일에는 상태 변경 로직이 없다.
//
// FE 제안: T01 오늘 요약 · T06 답장 없는 메일 · T07 회신 초안은 서버에서 아직 준비 중(ready=False)이라
// 실제 서버는 unsupported('…아직 준비 중이에요')로 답한다. 모의만 summary · awaiting · draft 결과를 만든다(contract.ts AGENT_PROPOSED_KINDS).
import { HttpError } from '../errors.ts';
import type {
  ProvisionalAgentResult,
  ProvisionalAgentTarget,
  ProvisionalAwaiting,
  ProvisionalContact,
  ProvisionalDashboardResponse,
  ProvisionalMail,
  ProvisionalTask,
} from '../provisional.ts';
import type { TaskStatus } from '../types.ts';
import { mockReplyDraft, parseKstNaive, type ActionId, type PlanResponse, type PlanTarget } from './agentPlanner.ts';

/** mockClient가 넘기는 BE-4 흉내. 시각은 epoch 밀리초 */
export interface AgentStore {
  data: ProvisionalDashboardResponse;
  nowMs: number;
  snoozedUntilMs(taskId: number): number | null;
  /** 미리보기 만들기 → {preview_id, expires_at} */
  preview(taskIds: number[], status: TaskStatus, untilMs: number | null, action: string): { preview_id: string; expires_at: string };
  /** 바로 바꾸기 → 기록 id(바뀐 것이 없으면 null) */
  change(taskIds: number[], status: TaskStatus, untilMs: number | null, action: string): number | null;
  /** 가장 최근 기록 */
  latestAction(): { id: number; action: string; undoneId: number | null } | null;
  findAction(id: number): { id: number } | null;
  /** 되돌리기. 못 하면 HttpError(404 · 409) */
  undo(actionId: number): { backId: number; undoneId: number; undoneAction: string; taskIds: number[] };
  toIso(ms: number | null): string | null;
}

// ── registry.py · policy.py ──

interface ActionDef {
  name: string;
  kind: 'query' | 'display' | 'state_change';
  params: readonly string[];
  required?: readonly string[];
}

// 모의가 고를 수 있는 행동만(agentPlanner MOCK_SUPPORTED). T01 · T06 · T07은 FE 제안으로 모의에서만 준비됨
const REGISTRY: Partial<Record<ActionId, ActionDef>> = {
  T01: { name: '오늘_요약', kind: 'query', params: ['date'] },
  T02: { name: '미처리_조회', kind: 'query', params: [] },
  T03: { name: '일괄_완료', kind: 'state_change', params: [] },
  T04: { name: '되돌리기', kind: 'state_change', params: ['action_id'] },
  T05: { name: '나중에_처리', kind: 'state_change', params: ['until'], required: ['until'] },
  T06: { name: '무응답_확인', kind: 'query', params: ['min_days'] },
  T07: { name: '회신_초안', kind: 'display', params: ['tone'] },
};

const STATUS: Partial<Record<ActionId, TaskStatus>> = { T03: 'done', T05: 'snoozed' };
const SOURCE = { rule: 'agent_rule', model: 'agent_model' } as const;
const ASK_UNTIL = '언제 다시 알려 드릴까요?';

function needsConfirm(a: ActionDef, count: number, ambiguous: boolean): boolean {
  if (a.kind !== 'state_change') return false;
  return count >= 2 || ambiguous;
}

// ── 시각 ──

const KST = 9 * 3600_000;
const DAY = 86_400_000;
const pad = (n: number) => String(n).padStart(2, '0');

/** executor.py의 `%m/%d %H:%M`(KST) */
function mdhm(ms: number): string {
  const d = new Date(ms + KST);
  return `${pad(d.getUTCMonth() + 1)}/${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

const kstDay = (ms: number) => Math.floor((ms + KST) / DAY);

function verb(status: TaskStatus, untilMs: number | null, done: boolean): string {
  if (status === 'snoozed') return `${mdhm(untilMs!)}까지 ` + (done ? '미뤘어요' : '미룰까요?');
  if (status === 'excluded') return '목록에서 ' + (done ? '뺐어요' : '뺄까요?');
  return '완료로 ' + (done ? '바꿨어요' : '바꿀까요?');
}

// ── resolve.py ──

const OPEN = new Set(['pending', 'snoozed']);
const MIN_PHRASE = 2;

const norm = (s: string) => s.trim().replace(/\s+|님$/g, '');

/** '김 팀장' · '김민준' · '민준' · 메일 주소 → 연락처(resolve.py match_contacts) */
export function matchContacts(contacts: readonly ProvisionalContact[], phrase: string): ProvisionalContact[] {
  const p = norm(phrase).toLowerCase();
  if (p.length < MIN_PHRASE) return [];
  return contacts.filter((c) => {
    const name = norm(c.name ?? '').toLowerCase();
    const pos = norm(c.position ?? '').toLowerCase();
    return (
      c.email.toLowerCase().includes(p) ||
      (name !== '' && (name.includes(p) || p.includes(name))) ||
      (pos !== '' && p === pos) ||
      (name !== '' && pos !== '' && p.startsWith(name[0]!) && p.endsWith(pos) && p.length <= pos.length + 2)
    );
  });
}

interface Resolution {
  taskIds: number[];
  ambiguous: boolean;
  noFilter: boolean;
  notes: string[];
}

// date_range는 모의 규칙이 만들지 않아 옮기지 않았다
function resolve(data: ProvisionalDashboardResponse, target: PlanTarget, allowAll: boolean): Resolution {
  const res: Resolution = { taskIds: [], ambiguous: false, noFilter: false, notes: [] };
  const mails = new Map(data.mails.map((m) => [m.id, m]));
  let rows = data.tasks
    .map((t) => ({ t, m: mails.get(t.mail_id) }))
    .filter((x): x is { t: ProvisionalTask; m: ProvisionalMail } => x.m !== undefined && OPEN.has(x.t.status) && x.m.direction === 'received');
  let used = false;
  const ids = target.mail_ids.map(Number).filter(Number.isInteger);
  if (ids.length) {
    rows = rows.filter((x) => ids.includes(x.t.mail_id));
    used = true;
    res.notes.push(`선택한 메일 ${ids.length}통`);
  }
  if (target.sender) {
    const people = matchContacts(data.contacts, target.sender);
    used = true;
    if (!people.length) {
      res.notes.push(`'${target.sender}'에 맞는 연락처가 없어요`);
      return res;
    }
    res.ambiguous = people.length > 1;
    const emails = new Set(people.map((c) => c.email));
    rows = rows.filter((x) => emails.has(x.m.sender));
    res.notes.push(
      `'${target.sender}'을(를) ` +
        people.map((c) => `${c.name ?? c.email} ${c.position ?? ''}`.trim()).join(' · ') +
        (res.ambiguous ? '으로 (여러 명)' : '으로'),
    );
  }
  if (target.category) {
    const category = target.category;
    rows = rows.filter((x) => x.m.category === category);
    used = true;
    res.notes.push(`분류 '${category}'`);
  }
  if (target.keyword) {
    const k = target.keyword;
    rows = rows.filter((x) => x.t.text.includes(k) || x.m.subject.includes(k));
    used = true;
    res.notes.push(`'${k}'이(가) 들어간 업무`);
  }
  if (!used && !allowAll) {
    res.noFilter = true;
    return res;
  }
  if (!used) res.notes.push('미처리 업무 전체');
  rows.sort((a, b) => Date.parse(a.m.received_at) - Date.parse(b.m.received_at) || a.t.id - b.t.id);
  res.taskIds = rows.map((x) => x.t.id);
  return res;
}

function targetsOf(store: AgentStore, ids: readonly number[]): ProvisionalAgentTarget[] {
  const byId = new Map(store.data.tasks.map((t) => [t.id, t]));
  return ids.flatMap((id) => {
    const t = byId.get(id);
    return t ? [{ id, mail_id: t.mail_id, text: t.text, status: t.status, snoozed_until: store.toIso(store.snoozedUntilMs(id)) }] : [];
  });
}

// ── executor.py run ──

type Base = Pick<ProvisionalAgentResult, 'action' | 'action_name' | 'source'>;

function result(kind: string, title: string, base: Base, more: Partial<ProvisionalAgentResult> = {}): ProvisionalAgentResult {
  return { kind, title, ...base, targets: [], notes: [], action_id: null, preview_id: null, expires_at: null, ...more };
}

export function executePlan(plan: PlanResponse, store: AgentStore): ProvisionalAgentResult {
  const source = SOURCE[plan.source];
  const base: Base = { action: plan.action, action_name: plan.action_name, source };
  if (plan.action === null) {
    if (plan.reason === 'ambiguous') return result('ask', '무엇을 할지 조금 더 구체적으로 말해 주세요', base);
    return result('unsupported', '지원하지 않는 요청이에요', base);
  }
  const a = REGISTRY[plan.action];
  const params = plan.params;
  if (!a || !Object.keys(params).every((k) => a.params.includes(k))) return result('unsupported', '지원하지 않는 요청이에요', base);
  base.action_name = a.name;
  const missing = (a.required ?? []).filter((k) => params[k] === null || params[k] === undefined);
  if (missing.length) return result('ask', missing[0] === 'until' ? ASK_UNTIL : '필요한 값을 알려 주세요', base);
  let untilMs: number | null = null;
  if (params.until !== undefined && params.until !== null) {
    untilMs = parseKstNaive(String(params.until));
    if (untilMs === null) return result('ask', ASK_UNTIL, base);
    if (untilMs <= store.nowMs) return result('ask', ASK_UNTIL, base, { notes: [`${mdhm(untilMs)}은 이미 지난 시각이에요`] });
  }

  if (plan.action === 'T04') return undo(store, params.action_id ?? null, base);
  // FE 제안(모의만)
  if (plan.action === 'T01') return summary(store, base, typeof params.date === 'string' ? params.date : null);
  if (plan.action === 'T06') return awaiting(store, base, typeof params.min_days === 'number' ? params.min_days : 3);
  if (plan.action === 'T07') return draft(store, base, plan.target, params.tone === 'short' ? 'short' : 'polite');

  const res = resolve(store.data, plan.target, a.kind === 'query');
  if (res.noFilter) return result('ask', '어떤 업무인지 알려 주세요(보낸 사람 · 분류 · 기간 · 메일 선택)', base);
  if (!res.taskIds.length) return result('empty', '해당하는 미처리 업무가 없어요', base, { notes: res.notes });
  if (a.kind === 'query') {
    const targets = targetsOf(store, res.taskIds);
    const later = targets.filter((t) => t.status === 'snoozed').length;
    return result('query', `미처리 업무 ${targets.length}건이에요` + (later ? `(나중에 ${later}건 포함)` : ''), base, { targets, notes: res.notes });
  }

  const status = STATUS[plan.action]!;
  const n = res.taskIds.length;
  if (needsConfirm(a, n, res.ambiguous)) {
    const p = store.preview(res.taskIds, status, untilMs, plan.action);
    return result('confirm', `업무 ${n}건을 ${verb(status, untilMs, false)}`, base, {
      targets: targetsOf(store, res.taskIds),
      notes: res.notes,
      preview_id: p.preview_id,
      expires_at: p.expires_at,
    });
  }
  const actionId = store.change(res.taskIds, status, untilMs, plan.action);
  return result('done', `${n}건을 ${verb(status, untilMs, true)}`, base, {
    targets: targetsOf(store, res.taskIds),
    notes: res.notes,
    action_id: actionId,
  });
}

// T04: 지정한 행동, 없으면 방금 한 행동. 방금 한 행동이 되돌리기면 그 전 것을 조용히 되돌리지 않고 되묻는다(executor.py _undo)
function undo(store: AgentStore, targetId: PlanResponse['params'][string], base: Base): ProvisionalAgentResult {
  let id: number;
  if (targetId !== null && targetId !== undefined) {
    id = Number(targetId);
    if (!Number.isInteger(id)) return result('ask', '어떤 행동을 되돌릴지 알려 주세요', base);
    if (!store.findAction(id)) return result('empty', '되돌릴 행동이 없어요', base);
  } else {
    const latest = store.latestAction();
    if (!latest) return result('empty', '되돌릴 행동이 없어요', base);
    if (latest.action === 'undo') {
      return result('ask', '방금 되돌린 걸 다시 할까요, 그 전 것도 되돌릴까요?', base, {
        notes: [`방금 행동 #${latest.undoneId}을(를) 되돌렸어요`],
      });
    }
    id = latest.id;
  }
  try {
    const u = store.undo(id);
    return result('done', `${u.taskIds.length}건을 되돌렸어요`, base, {
      targets: targetsOf(store, u.taskIds),
      action_id: u.backId,
      notes: [`행동 #${u.undoneId}(${u.undoneAction})를 되돌림`],
    });
  } catch (e) {
    if (e instanceof HttpError) return result('empty', `되돌릴 수 없어요: ${e.message}`, base);
    throw e;
  }
}

// ── FE 제안(모의만) ──

function contactLabel(data: ProvisionalDashboardResponse, email: string): string {
  const c = data.contacts.find((x) => x.email === email);
  if (!c?.name) return email;
  return c.position ? `${c.name} ${c.position}` : c.name;
}

/** T01: 오늘(또는 내일) 챙길 업무. 오늘은 기한 지남 · 오늘 마감 · ASAP, 급한 순 5건까지 */
function summary(store: AgentStore, base: Base, date: string | null): ProvisionalAgentResult {
  const { data, nowMs } = store;
  const pending = data.tasks.filter((t) => t.status === 'pending');
  const today = kstDay(nowMs);
  const dateMs = date === null ? null : parseKstNaive(date);
  const item = (t: ProvisionalTask) => ({ task_id: t.id, mail_id: t.mail_id, text: t.text, due_at: t.due_at, due_raw: t.due_raw ?? null });
  const dueMs = (t: ProvisionalTask) => (t.due_at === null ? null : Date.parse(t.due_at));

  if (dateMs !== null && kstDay(dateMs) === today + 1) {
    const items = pending.filter((t) => {
      const d = dueMs(t);
      return d !== null && kstDay(d) === today + 1;
    });
    return result('summary', items.length ? `내일 마감 ${items.length}건이에요` : '내일 마감인 업무는 없어요', base, {
      notes: [`내일 마감 업무 ${items.length}건`],
      summary: { items: items.map(item), hint: `지금 미처리 ${pending.length}건` },
    });
  }
  // 0 = 기한 지남 · ASAP, 1 = 오늘 마감
  const rank = (t: ProvisionalTask): number | null => {
    const d = dueMs(t);
    if (d === null) return t.due_raw === 'ASAP' ? 0 : null;
    if (d < nowMs) return 0;
    return kstDay(d) === today ? 1 : null;
  };
  const urgent = pending.filter((t) => rank(t) !== null).sort((a, b) => rank(a)! - rank(b)!);
  const lanes = data.mails.some((m) => m.lane !== undefined);
  const checks = lanes ? data.mails.filter((m) => m.lane === '확인').length : null;
  const rest = pending.length - urgent.length;
  return result('summary', urgent.length ? `긴급 ${urgent.length}건이에요` : '오늘 급한 업무는 없어요', base, {
    notes: [`미처리 ${pending.length}건 중 기한 지남 · 오늘 마감 · ASAP`],
    summary: {
      // 브리핑 문장(text)은 T01 백엔드가 모델로 쓸 칸이다(조율 중, FE-15). 모의는 화면을 볼 수 있게 규칙으로 한 문장만 만든다
      text: urgent.length ? `오늘은 '${urgent[0]!.text}'부터 챙기세요. 급한 업무가 ${urgent.length}건 있어요.` : null,
      items: urgent.slice(0, 5).map(item),
      hint: `그 밖에 미처리 ${rest}건${checks === null ? '' : ` · 확인사항 ${checks}건`}${urgent.length > 5 ? ` · 긴급 ${urgent.length - 5}건 더 있음` : ''}`,
    },
  });
}

/** T06: 보낸 메일 중 min_days일 넘게 답이 없는 것. 응답 대기 자료가 없는 묶음(v1)은 실제 서버처럼 준비 중 */
function awaiting(store: AgentStore, base: Base, minDays: number): ProvisionalAgentResult {
  const all: ProvisionalAwaiting[] | undefined = store.data.awaiting;
  if (all === undefined) return result('unsupported', `'${base.action_name}'은(는) 아직 준비 중이에요`, base);
  const items = all.filter((a) => a.days >= minDays).sort((a, b) => b.days - a.days);
  return result(
    'awaiting',
    items.length ? `${minDays}일 이상 답장이 없는 메일 ${items.length}건이에요` : `${minDays}일 이상 답장이 없는 메일은 없어요`,
    base,
    { notes: [`보낸 메일 중 ${minDays}일 이상 답이 없는 것 ${items.length}건`], awaiting: items },
  );
}

/** T07: 고른 메일 1통의 회신 초안. 보내지 않는다 */
function draft(store: AgentStore, base: Base, target: PlanTarget, tone: 'polite' | 'short'): ProvisionalAgentResult {
  if (target.mail_ids.length !== 1) return result('ask', '회신 초안을 쓸 메일을 한 통 골라 주세요', base);
  const id = Number(target.mail_ids[0]);
  const mail = store.data.mails.find((m) => m.id === id);
  if (!mail) return result('empty', '고른 메일을 찾지 못했어요', base);
  const texts = store.data.tasks.filter((t) => t.mail_id === id && t.status === 'pending').map((t) => t.text);
  return result('draft', '회신 초안을 만들었어요', base, {
    notes: [`고른 메일 '${mail.subject}'`],
    draft: { mail_id: id, to: contactLabel(store.data, mail.sender), subject: mail.subject, text: mockReplyDraft(texts, tone) },
  });
}
