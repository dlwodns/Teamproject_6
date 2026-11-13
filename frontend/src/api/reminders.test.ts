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
  type_label: '답 없음',
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
    { id: 'stop_waiting', label: '그만 기다리기', action: 'dismiss', primary: false, params: { reason: 'stop_waiting' } },
    { id: 'draft', label: '재촉 초안', action: 'T07', primary: true, params: { mail_id: 31, tone: 'polite' } },
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
    title: '아침 브리핑',
    summary: '오늘 기한인 업무가 1건 있어요.',
    total: 1,
    sections: [{ id: 'due_today', label: '오늘 기한', count: 1, items: [{ task_id: 5, mail_id: 5, commitment_id: null, reminder_key: null, title: '주간 보고', reason: '최유진 책임', due_at: null, action_id: null, actions: [] }] }],
  });
  assert.equal(b.text, '오늘 기한인 업무가 1건 있어요.');
  assert.equal(b.generatedAtMs, Date.parse('2026-11-06T08:30:00+09:00'));
  assert.equal(b.scheduledAtMs, null);
  assert.equal(b.sections[0]!.title, '오늘 기한');
  assert.equal(b.sections[0]!.items[0]!.detail, '최유진 책임');
  assert.throws(() => toBriefing({ kind: 'morning', date: '11/6', as_of: '2026-11-06T08:30:00+09:00', sections: [] }), ContractError);
});

test('알림의 리마인더 칸: 모르는 유형(digest의 evening 등)은 null, 칸이 없으면 키도 없다', () => {
  const base = { id: 1, kind: 'digest', title: '퇴근 회고', body: null, task_ids: [], rule: 'R-퇴근', scheduled_at: null, read_at: null, answered_at: null, created_at: '2026-11-06T17:30:00+09:00' };
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

test('모의: 모두 읽음은 읽은 수를 돌려주고, 다시 하면 0', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const first = await api.readAllNotifications();
  assert.ok(first > 0);
  assert.equal(await api.readAllNotifications(), 0);
});
