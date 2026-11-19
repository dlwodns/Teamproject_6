// 리마인더 계약(FE-16 · BE-12): BE-12 응답 모양을 읽는 어댑터 + 모의 서버의 목록 · 숨김 · 적용 · 되돌리기 · 브리핑 · 모두 읽음
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { agentCommandBody, toBriefing, toNotification, toReminderChange, toReminderList } from './adapter.ts';
import { ContractError } from './errors.ts';
import { createMockApi } from './mockClient.ts';
import type { TaskId } from './types.ts';

/** BE-12 schemas/reminders.py ReminderItem 그대로(type_label · notify · counterpart.email/label · actions[].params) */
const beItem = {
  key: 'no_reply:sent_mail:31',
  type: 'no_reply',
  type_label: '회신 미수신',
  group: 'waiting',
  title: '견적 회신 요청',
  reason: '보낸 지 3일, 답이 없어요.',
  evidence: null,
  task_id: null,
  task_ids: [],
  mail_id: 31,
  commitment_id: null,
  due_at: null,
  counterpart: { email: 'kim@example.com', name: '김민준', position: '팀장', label: '김민준 팀장님' },
  created_at: '2026-11-06T09:00:00+09:00',
  state: 'active',
  notify_count: 1,
  notify: true,
  actions: [
    { id: 'stop_waiting', label: '회신 대기 종료', action: 'dismiss', primary: false, params: { reason: 'stop_waiting' } },
    { id: 'draft', label: '회신 요청 작성', action: 'T07', primary: true, params: { mail_id: 31, tone: 'polite' } },
  ],
};

test('BE-12 목록: 더 보낸 칸은 무시하고, dismiss 이유는 params.reason에서 읽는다. 모르는 유형 항목만 뺀다', () => {
  const list = toReminderList({
    as_of: '2026-11-06T10:42:00+09:00',
    counts: { due: 0, waiting: 1, promise: 0, revisit: 0, prepare: 0, cleanup: 0, all: 1 },
    muted_types: ['stale'],
    items: [beItem, { ...beItem, key: 'x', type: 'future_type' }],
  });
  assert.equal(list.items.length, 1);
  const it = list.items[0]!;
  assert.deepEqual(it.counterpart, { name: '김민준', position: '팀장' });
  assert.equal(it.lastNotifiedAtMs, null);
  assert.equal(it.actions[0]!.reason, 'stop_waiting');
  assert.equal(it.actions[1]!.reason, undefined);
  assert.deepEqual(list.mutedTypes, ['stale']);
  assert.equal(list.counts.waiting, 1);
});

test('BE-12 dismiss · apply 응답에는 state가 없어도 된다', () => {
  assert.deepEqual(toReminderChange({ key: 'k', reason: 'hide', hidden_until: null, action_id: null }), { key: 'k', actionId: null });
  assert.deepEqual(toReminderChange({ key: 'k', action_id: 3, task: null, due_at: null, commitment_id: null }), { key: 'k', actionId: 3 });
});

test('BE-12 브리핑: summary · label · reason을 읽고, 만든 시각은 as_of. 날짜 형식이 틀리면 계약 오류', () => {
  const b = toBriefing({
    kind: 'morning',
    date: '2026-11-06',
    as_of: '2026-11-06T08:30:00+09:00',
    title: '일일 업무 요약',
    summary: '오늘 기한인 업무가 1건 있어요.',
    total: 1,
    sections: [{ id: 'due_today', label: '금일 마감 업무', count: 1, items: [{ task_id: 5, mail_id: 5, commitment_id: null, reminder_key: null, title: '주간 보고', reason: '최유진 책임', due_at: null, action_id: null, actions: [] }] }],
  });
  assert.equal(b.text, '오늘 기한인 업무가 1건 있어요.');
  assert.equal(b.generatedAtMs, Date.parse('2026-11-06T08:30:00+09:00'));
  assert.equal(b.scheduledAtMs, null);
  assert.equal(b.sections[0]!.title, '금일 마감 업무');
  assert.equal(b.sections[0]!.items[0]!.detail, '최유진 책임');
  assert.throws(() => toBriefing({ kind: 'morning', date: '11/6', as_of: '2026-11-06T08:30:00+09:00', sections: [] }), ContractError);
});

test('알림의 리마인더 칸: 모르는 유형(digest의 evening 등)은 null, 칸이 없으면 키도 없다', () => {
  const base = { id: 1, kind: 'digest', title: '일일 업무 회고', body: null, task_ids: [], rule: 'R-퇴근', scheduled_at: null, read_at: null, answered_at: null, created_at: '2026-11-06T17:30:00+09:00' };
  const a = toNotification({ ...base, type: 'evening', group: null, reminder_key: null, reminder_keys: [] });
  assert.equal(a.type, null);
  assert.equal(a.reminderKey, null);
  assert.equal('group' in toNotification(base), false);
});

test('고른 리마인더는 명령 본문에 task_ids · reminder_key로 붙고, 없으면 칸을 보내지 않는다', () => {
  assert.deepEqual(agentCommandBody({ text: '이거 미뤄 줘', taskIds: [3 as TaskId], reminderKey: 'overdue:task:3' }), {
    text: '이거 미뤄 줘', selected_mail_ids: [], last_result_ids: [], task_ids: [3], reminder_key: 'overdue:task:3',
  });
  assert.equal('task_ids' in agentCommandBody({ text: 'x' }), false);
});

test('모의: 이번 단계 유형 15가지가 모두 있고, 업무 하나에 항목 하나, 건수는 항목 수와 같다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const list = await api.getReminders('all');
  const types = new Set(list.items.map((i) => i.type));
  for (const t of ['overdue', 'due_soon', 'due_changed', 'due_cluster', 'no_reply', 'their_promise', 'my_promise', 'snooze_due', 'priority_sender', 'cc_mention', 'stale', 'stalled_thread', 'meeting_prep', 'resolved', 'reply_confirm'] as const) {
    assert.ok(types.has(t), `${t} 없음`);
  }
  const tasks = list.items.filter((i) => i.taskId !== null).map((i) => i.taskId);
  assert.equal(new Set(tasks).size, tasks.length);
  assert.equal(list.counts.all, list.items.length);
  const due = await api.getReminders('due');
  assert.ok(due.items.every((i) => i.group === 'due'));
  assert.equal(due.counts.all, list.counts.all);
});

test('모의: 숨기면 목록에서 빠지고 되돌리면 돌아온다. 기한 바꾸기 적용도 되돌릴 수 있다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const before = (await api.getReminders('all')).items.length;
  const hidden = await api.dismissReminder('stale:task:10', 'hide');
  assert.equal((await api.getReminders('all')).items.length, before - 1);
  await api.undoAction(hidden.actionId!);
  assert.equal((await api.getReminders('all')).items.length, before);

  const changed = await api.applyReminder('due_changed:task:11');
  assert.ok(changed.actionId !== null);
  assert.ok(!(await api.getReminders('all')).items.some((i) => i.key === 'due_changed:task:11'));
  await api.undoAction(changed.actionId!);
  assert.ok((await api.getReminders('all')).items.some((i) => i.key === 'due_changed:task:11'));
  await assert.rejects(api.dismissReminder('stale:task:10', 'nope' as never));
});

test('모의: 유형 알림 끄기는 목록에 남기고 muted_types에만 더한다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const n = (await api.getReminders('all')).items.length;
  assert.deepEqual(await api.setReminderTypeNotify('stale', false), { type: 'stale', notify: false });
  const after = await api.getReminders('all');
  assert.ok(after.mutedTypes?.includes('stale'));
  assert.equal(after.items.length, n);
});

test('모의 브리핑: 지난 아침은 내용이 있고, 아직 오지 않은 퇴근 회고는 예정 시각만. 권하는 문장이 없다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const morning = await api.getBriefing('morning', '2026-11-06');
  assert.ok(morning.sections.length > 0 && morning.text);
  assert.doesNotMatch(JSON.stringify(morning), /챙기세요|하세요/);
  const evening = await api.getBriefing('evening', '2026-11-06');
  assert.equal(evening.generatedAtMs, null);
  assert.equal(evening.sections.length, 0);
  assert.ok(evening.scheduledAtMs !== null);
});

test('BE-12 브리핑 시각: as_of는 asOfMs로 읽고, 예정 시각(scheduled_at)보다 이르면 아직 만든 것이 아니다', () => {
  const base = { kind: 'evening', date: '2026-11-06', title: '일일 업무 회고', summary: '남은 일이 2건 있어요.', total: 2, sections: [] };
  const early = toBriefing({ ...base, as_of: '2026-11-06T10:42:00+09:00', scheduled_at: '2026-11-06T17:30:00+09:00' });
  assert.equal(early.asOfMs, Date.parse('2026-11-06T10:42:00+09:00'));
  assert.equal(early.scheduledAtMs, Date.parse('2026-11-06T17:30:00+09:00'));
  assert.equal(early.generatedAtMs, null);
  const late = toBriefing({ ...base, as_of: '2026-11-06T17:31:00+09:00', scheduled_at: '2026-11-06T17:30:00+09:00' });
  assert.equal(late.generatedAtMs, Date.parse('2026-11-06T17:31:00+09:00'));
  // 옛 응답(scheduled_at 없음)은 예전처럼 as_of를 만든 시각으로
  assert.equal(toBriefing({ ...base, as_of: '2026-11-06T10:42:00+09:00' }).generatedAtMs, Date.parse('2026-11-06T10:42:00+09:00'));
});

test('BE-12 항목의 마지막 알림 시각(last_notified_at, 선택): 있으면 읽고 없으면 null', () => {
  const withLast = toReminderList({ as_of: '2026-11-06T10:42:00+09:00', counts: {}, items: [{ ...beItem, last_notified_at: '2026-11-06T08:30:00+09:00' }] });
  assert.equal(withLast.items[0]!.lastNotifiedAtMs, Date.parse('2026-11-06T08:30:00+09:00'));
  const without = toReminderList({ as_of: '2026-11-06T10:42:00+09:00', counts: {}, items: [beItem] });
  assert.equal(without.items[0]!.lastNotifiedAtMs, null);
});

test('모의 브리핑도 BE-12처럼 as_of · scheduled_at을 보낸다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const evening = await api.getBriefing('evening', '2026-11-06');
  assert.equal(evening.asOfMs, Date.parse('2026-11-06T10:42:00+09:00'));
  assert.ok(evening.scheduledAtMs !== null && evening.asOfMs !== null && evening.asOfMs < evening.scheduledAtMs);
  const morning = await api.getBriefing('morning', '2026-11-06');
  assert.ok(morning.asOfMs !== null && morning.generatedAtMs !== null);
});

test('모의: 모두 읽음은 읽은 수를 돌려주고, 다시 하면 0', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const first = await api.readAllNotifications();
  assert.ok(first > 0);
  assert.equal(await api.readAllNotifications(), 0);
});

// ── 기한 몰림 [당일 업무 보기] (T13): BE rules._due_cluster가 보내는 모양 그대로 ──
// backend/app/reminders/rules.py: _act("open_day", "당일 업무 보기", "T13", primary=True, start=day.isoformat(), end=day.isoformat())
const beCluster = {
  ...beItem,
  key: 'due_cluster:day:20261113',
  type: 'due_cluster',
  type_label: '마감 집중',
  group: 'due',
  title: '11/13(금) 기한 3건',
  reason: '하루에 기한이 3건 집중되어 있습니다',
  task_ids: [4, 5, 6],
  mail_id: null,
  due_at: '2026-11-13T15:00:00+09:00',
  counterpart: null,
  actions: [
    { id: 'open_day', label: '당일 업무 보기', action: 'T13', primary: true, params: { start: '2026-11-13', end: '2026-11-13' } },
    { id: 'snooze_one', label: '1건 연기', action: 'T05', primary: false, params: { until: null } },
  ],
};

test('기한 몰림 T13: 어댑터가 params.start · end를 옮기고, [당일 업무 보기]가 그 날짜 캘린더로 가는 버튼으로 남는다', async () => {
  const { drawableActions } = await import('../features/reminders/reminderModel.ts');
  const list = toReminderList({ as_of: '2026-11-11T14:00:00+09:00', counts: {}, items: [beCluster] });
  const it = list.items[0]!;
  assert.deepEqual(it.actions[0], { id: 'open_day', label: '당일 업무 보기', action: 'T13', primary: true, range: { start: '2026-11-13', end: '2026-11-13' } });
  assert.equal(it.actions[1]!.range, undefined, 'start · end가 없는 버튼에는 칸을 두지 않는다');
  for (const mode of ['mock', 'http'] as const) {
    const drawn = drawableActions(it, { mailTarget: () => null, mode });
    assert.deepEqual(
      drawn.map((d) => [d.action.id, d.plan]),
      [
        ['snooze_one', { type: 'snooze', taskIds: [4, 5, 6] }],
        ['open_day', { type: 'route', to: '/calendar?day=2026-11-13' }],
      ],
      `${mode}: 하나 미루기는 그대로, 당일 업무 보기는 지워지지 않는다`,
    );
  }
});

test('기한 몰림 T13: start · end가 문자열이 아니면 칸을 두지 않는다(목록 전체를 버리지 않는다)', () => {
  const bad = { ...beCluster, actions: [{ ...beCluster.actions[0]!, params: { start: 20261113, end: null } }] };
  const list = toReminderList({ as_of: '2026-11-11T14:00:00+09:00', counts: {}, items: [bad] });
  assert.equal(list.items[0]!.actions[0]!.range, undefined);
});

test('narrowToTasks: 고른 리마인더 업무는 서버(executor.run)와 같은 규칙으로 대상이 된다(BE-18)', async () => {
  const { narrowToTasks } = await import('./mock/reminderMock.ts');
  const base = { sender: null, category: null, date_range: { start: '2026-11-20T00:00:00', end: '2026-11-20T23:59:59' }, keyword: null, mail_ids: ['9'], awaiting_reply: true };
  const data = { tasks: [{ id: 1, mail_id: 10 }, { id: 2, mail_id: 10 }, { id: 3, mail_id: 11 }] } as never;
  // 말에 다른 대상이 없으면: 고른 업무의 메일만, 기간 · 응답 대기 조건은 버린다, 그 메일의 고르지 않은 업무는 뺀다
  const a = narrowToTasks(data, base, [1]);
  assert.deepEqual(a.target, { ...base, date_range: null, awaiting_reply: false, mail_ids: ['10'] });
  assert.deepEqual((a.data as { tasks: { id: number }[] }).tasks.map((t) => t.id), [1, 3]);
  // 보낸 사람을 대면 고른 업무는 쓰지 않는다
  const b = narrowToTasks(data, { ...base, sender: '김 팀장' }, [1]);
  assert.equal(b.data, data);
  assert.equal(b.target.mail_ids[0], '9');
  // 고른 업무가 없으면 그대로
  assert.equal(narrowToTasks(data, base, []).data, data);
});
