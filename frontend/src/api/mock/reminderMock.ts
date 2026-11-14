// 리마인더 모의 (FE-16 · BE-12 계약 흉내). mockClient가 상태 접근 함수를 넘겨 만든다.
// 고정 자료(reminders.v1.json)를 바탕으로 하되, 지금 업무 상태에 맞춰 목록을 다시 거른다 — 완료 · 제외한 업무,
// 숨기거나 끝낸 항목은 빠지고, 미룬 업무는 '연기 업무' 항목만 남는다. 그래서 화면에서 버튼을 누르면 목록이 실제처럼 줄어든다.
// 적용 · 숨김은 기록을 남기고 되돌릴 수 있다(명세 7.2절 'action_log 한 줄 + 되돌리기').
import { toBriefing, toKstIso, toReminderChange, toReminderList, toReminderTypeNotify, toReadAllCount } from '../adapter.ts';
import {
  BRIEFING_KINDS,
  DISMISS_REASONS,
  REMINDER_GROUPS,
  REMINDER_TYPES,
  type ApiClient,
  type BriefingKind,
  type DismissReason,
} from '../contract.ts';
import { HttpError } from '../errors.ts';
import type {
  ProvisionalBriefing,
  ProvisionalDashboardResponse,
  ProvisionalNotification,
  ProvisionalReminderItem,
  ProvisionalRemindersResponse,
} from '../provisional.ts';
import type { TaskStatus } from '../types.ts';

type MockItem = ProvisionalReminderItem & { mock_new_due_at?: string };

export interface ReminderFixture {
  items: MockItem[];
  muted_types: string[];
  notification_links: Record<string, Pick<ProvisionalNotification, 'type' | 'group' | 'reminder_key'>>;
  notifications: ProvisionalNotification[];
  briefings: Partial<Record<BriefingKind, Record<string, ProvisionalBriefing>>>;
}

export async function loadReminderFixture(): Promise<ReminderFixture> {
  // mockClient.loadMockFixtures와 같은 이유로 개발 서버에서만 JSON 형식 표시를 뺀다
  const json = import.meta.env?.DEV ? undefined : ({ with: { type: 'json' } } as const);
  const mod = await import('./reminders.v1.json', json);
  return mod.default as unknown as ReminderFixture;
}

export interface ReminderMockDeps<S extends object> {
  begin(signal?: AbortSignal): Promise<S>;
  now(s: S): number;
  dashboard(s: S): ProvisionalDashboardResponse;
  snoozedUntil(s: S, taskId: number): number | null;
  /** 업무 상태 바꾸기(BE-4 흉내). 기록 id(바뀐 것이 없으면 null) */
  changeTasks(s: S, ids: number[], status: TaskStatus, action: string, via: string): number | null;
  /** 업무 상태가 아닌 것을 바꾼 기록. 되돌리면 undo를 부른다. 기록 id */
  recordOther(s: S, action: string, undo: () => void, text: string, via: string): number;
  /** 모의 상태의 알림 목록(직접 고친다: 칸 붙이기 · 더하기) */
  notifications(s: S): ProvisionalNotification[];
  empty: boolean;
  fixture?: ReminderFixture;
}

interface ReminderMockState {
  items: MockItem[];
  dismissed: Set<string>;
  doneCommitments: Set<number>;
  muted: Set<string>;
  briefings: ReminderFixture['briefings'];
}

type ReminderMethods = Pick<
  ApiClient,
  'getReminders' | 'dismissReminder' | 'applyReminder' | 'setReminderTypeNotify' | 'getBriefing' | 'readAllNotifications'
>;

const DAY_MS = 86_400_000;
const KST_MS = 9 * 3_600_000;
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** YYYY-MM-DD(KST)가 든 주의 금요일 날짜(주간 회고는 금요일에 만든다) */
export function fridayOf(date: string): string {
  const ms = Date.parse(`${date}T00:00:00+09:00`);
  const wd = new Date(ms + KST_MS).getUTCDay(); // 0 일 … 6 토
  const toFri = wd === 0 ? -2 : 5 - wd; // 토 → 그 전 금요일, 일 → 이틀 전 금요일
  return new Date(ms + KST_MS + toFri * DAY_MS).toISOString().slice(0, 10);
}

/** 모의 항목을 지금 상태로 거른다(순수 함수, 시험 대상) */
export function liveItems(
  items: readonly MockItem[],
  ctx: {
    taskStatus: (id: number) => string | undefined;
    snoozedUntil: (id: number) => number | null;
    nowMs: number;
    dismissed: ReadonlySet<string>;
    doneCommitments: ReadonlySet<number>;
  },
): MockItem[] {
  const out: MockItem[] = [];
  for (const it of items) {
    if (ctx.dismissed.has(it.key)) continue;
    if (it.commitment_id != null && ctx.doneCommitments.has(it.commitment_id)) continue;
    if (it.type === 'due_cluster') {
      // 그날 기한 = 남은 업무 + 오늘까지인 내 약속(모의 commitment 1). 3건 아래로 줄면 몰림이 아니다
      const open = (it.task_ids ?? []).filter((id) => ctx.taskStatus(id) === 'pending');
      if (open.length + (ctx.doneCommitments.has(1) ? 0 : 1) < 3) continue;
      out.push({ ...it, task_ids: open });
      continue;
    }
    if (it.task_id != null) {
      const status = ctx.taskStatus(it.task_id);
      if (status === undefined || status === 'done' || status === 'excluded') continue;
      if (it.type === 'snooze_due') {
        // 미룬 시각이 된 일. 다시 미뤄 그 시각이 아직 오지 않았으면 뺀다(처음 자료는 미룬 시각을 모른다 → 보인다)
        const until = ctx.snoozedUntil(it.task_id);
        if (status === 'snoozed' && until !== null && until > ctx.nowMs) continue;
      } else if (status === 'snoozed') continue;
    }
    out.push(it);
  }
  return out;
}

const short = (t: string) => (t.length > 24 ? `${t.slice(0, 23)}…` : t);

const strip = ({ mock_new_due_at: _drop, ...it }: MockItem): ProvisionalReminderItem => it;

export function createReminderMock<S extends object>(deps: ReminderMockDeps<S>): ReminderMethods & {
  /** 알림 목록(모의 시계가 예약 시각을 지난 것만). 처음 부를 때 리마인더 칸 · 알림을 붙인다 */
  visibleNotifications(s: S): Promise<ProvisionalNotification[]>;
} {
  const states = new WeakMap<S, Promise<ReminderMockState>>();

  function ensure(s: S): Promise<ReminderMockState> {
    let p = states.get(s);
    if (!p) {
      p = (deps.fixture ? Promise.resolve(deps.fixture) : loadReminderFixture()).then((f) => {
        const list = deps.notifications(s);
        for (const n of list) Object.assign(n, f.notification_links[String(n.id)] ?? {});
        const known = new Set(list.map((n) => n.id));
        for (const n of f.notifications) if (!known.has(n.id)) list.push(structuredClone(n));
        return {
          items: structuredClone(f.items),
          dismissed: new Set(),
          doneCommitments: new Set(),
          muted: new Set(f.muted_types),
          briefings: f.briefings,
        };
      });
      states.set(s, p);
    }
    return p;
  }

  async function load(signal?: AbortSignal) {
    const s = await deps.begin(signal);
    return { s, r: await ensure(s) };
  }

  function current(s: S, r: ReminderMockState): MockItem[] {
    const tasks = new Map(deps.dashboard(s).tasks.map((t) => [t.id, t]));
    return liveItems(r.items, {
      taskStatus: (id) => tasks.get(id)?.status,
      snoozedUntil: (id) => deps.snoozedUntil(s, id),
      nowMs: deps.now(s),
      dismissed: r.dismissed,
      doneCommitments: r.doneCommitments,
    }).map((it) => (it.task_id != null && it.due_at !== undefined ? { ...it, due_at: tasks.get(it.task_id)?.due_at ?? it.due_at } : it));
  }

  function find(s: S, r: ReminderMockState, key: string): MockItem {
    const it = current(s, r).find((x) => x.key === key);
    if (!it) throw new HttpError(404, `없는 리마인더: ${key}`);
    return it;
  }

  /** 항목을 끝난 것으로(숨김 · 적용) 표시하고 되돌릴 수 있게 */
  const close = (r: ReminderMockState, key: string) => {
    r.dismissed.add(key);
    return () => r.dismissed.delete(key);
  };

  return {
    async visibleNotifications(s) {
      await ensure(s);
      if (deps.empty) return [];
      const now = deps.now(s);
      return deps.notifications(s).filter((n) => n.scheduled_at == null || Date.parse(n.scheduled_at) <= now);
    },

    async getReminders(group, signal) {
      const { s, r } = await load(signal);
      if (group !== 'all' && !(REMINDER_GROUPS as readonly string[]).includes(group)) throw new HttpError(422, `모르는 묶음: ${String(group)}`);
      const all = deps.empty ? [] : current(s, r);
      const counts: Record<string, number> = { all: all.length };
      for (const g of REMINDER_GROUPS) counts[g] = all.filter((i) => i.group === g).length;
      const body: ProvisionalRemindersResponse = {
        as_of: toKstIso(deps.now(s)),
        counts,
        items: all.filter((i) => group === 'all' || i.group === group).map(strip),
        muted_types: [...r.muted],
      };
      return toReminderList(body);
    },

    async dismissReminder(key, reason: DismissReason) {
      const { s, r } = await load();
      if (!(DISMISS_REASONS as readonly string[]).includes(reason)) throw new HttpError(422, `모르는 이유: ${String(reason)}`);
      const it = find(s, r, key);
      let actionId: number | null;
      if (reason === 'not_mine') {
        if (it.task_id == null) throw new HttpError(422, '업무가 아닌 항목은 내 일 아님으로 뺄 수 없어요');
        // T10(업무 제외). 업무가 빠지면 항목도 목록에서 빠진다 → 되돌리면 함께 돌아온다
        actionId = deps.changeTasks(s, [it.task_id], 'excluded', 'T10', `reminder:${it.type}`);
      } else {
        const undo = close(r, key);
        const text = reason === 'stop_waiting' ? `'${short(it.title)}' 답을 그만 기다려요` : reason === 'wrong_signal' ? `'${short(it.title)}' 잘못 알아챈 신호를 지웠어요` : `'${short(it.title)}' 리마인더를 숨겼어요`;
        actionId = deps.recordOther(s, `reminder_${reason}`, undo, text, `reminder:${it.type}`);
      }
      return toReminderChange({ key, state: 'dismissed', action_id: actionId });
    },

    async applyReminder(key) {
      const { s, r } = await load();
      const it = find(s, r, key);
      let actionId: number | null;
      if (it.type === 'due_changed') {
        const task = deps.dashboard(s).tasks.find((t) => t.id === it.task_id);
        if (!task || !it.mock_new_due_at) throw new HttpError(422, '바꿀 기한이 없어요');
        const before = task.due_at;
        task.due_at = it.mock_new_due_at;
        task.due_source = 'mail';
        const undoClose = close(r, key);
        actionId = deps.recordOther(
          s,
          'T16',
          () => {
            task.due_at = before;
            undoClose();
          },
          `'${short(task.text)}' 업무 기한을 바꿨어요`,
          `reminder:${it.type}`,
        );
      } else if (it.type === 'resolved' || it.type === 'reply_confirm') {
        if (it.task_id == null) throw new HttpError(422, '완료할 업무가 없어요');
        actionId = deps.changeTasks(s, [it.task_id], 'done', 'T03', `reminder:${it.type}`);
      } else if (it.type === 'their_promise' || it.type === 'my_promise') {
        const id = it.commitment_id;
        if (id == null) throw new HttpError(422, '약속이 없어요');
        r.doneCommitments.add(id);
        const text = it.type === 'my_promise' ? `'${short(it.title)}' 약속을 지켰어요` : `'${short(it.title)}' 받았어요`;
        actionId = deps.recordOther(s, 'commitment_done', () => r.doneCommitments.delete(id), text, `reminder:${it.type}`);
      } else {
        throw new HttpError(422, `적용할 수 없는 유형: ${it.type}`);
      }
      return toReminderChange({ key, state: 'done', action_id: actionId });
    },

    async setReminderTypeNotify(type, notify) {
      const { r } = await load();
      if (!(REMINDER_TYPES as readonly string[]).includes(type)) throw new HttpError(422, `모르는 유형: ${String(type)}`);
      if (notify) r.muted.delete(type);
      else r.muted.add(type);
      return toReminderTypeNotify({ type, notify });
    },

    async getBriefing(kind, date, signal) {
      const { s, r } = await load(signal);
      if (!(BRIEFING_KINDS as readonly string[]).includes(kind)) throw new HttpError(422, `모르는 브리핑: ${String(kind)}`);
      if (!DATE_ONLY.test(date)) throw new HttpError(422, 'date는 YYYY-MM-DD');
      const day = kind === 'weekly' ? fridayOf(date) : date;
      const hit = deps.empty ? undefined : r.briefings[kind]?.[day];
      const at = kind === 'morning' ? '08:30' : '17:30';
      const scheduled = hit?.scheduled_at ?? `${day}T${at}:00+09:00`;
      // 아직 만들 시각이 아니면 내용 없이 예정 시각만(무엇이 있는지만 알리고, 미리 꾸며 보이지 않는다)
      const notYet = Date.parse(scheduled) > deps.now(s);
      // BE-12처럼 답한 시각(as_of)과 예정 시각(scheduled_at)을 늘 보낸다
      const as_of = toKstIso(deps.now(s));
      const body: ProvisionalBriefing =
        hit && !notYet
          ? { ...hit, as_of, scheduled_at: scheduled }
          : { kind, date: day, as_of, scheduled_at: scheduled, generated_at: null, text: null, sections: [] };
      return toBriefing(body);
    },

    async readAllNotifications() {
      const s = await deps.begin();
      await ensure(s);
      const at = toKstIso(deps.now(s));
      let n = 0;
      for (const x of deps.notifications(s)) {
        if (x.read_at === null && (x.scheduled_at == null || Date.parse(x.scheduled_at) <= deps.now(s))) {
          x.read_at = at;
          n++;
        }
      }
      return toReadAllCount({ updated: n });
    },
  };
}

/** 고른 리마인더의 업무로 명령 대상을 좁힌다(모의). 고른 메일 안의 다른 업무는 빼고, 다른 메일 업무는 그대로 둔다 */
export function narrowToTasks(data: ProvisionalDashboardResponse, mailIds: readonly number[], taskIds: readonly number[] | undefined): ProvisionalDashboardResponse {
  if (!taskIds || taskIds.length === 0) return data;
  const mails = new Set(mailIds);
  return { ...data, tasks: data.tasks.filter((t) => !mails.has(t.mail_id) || taskIds.includes(t.id)) };
}

