// 리마인더 화면의 판단(FE-16): 업무당 하나 · 정렬 · 묶음 건수 · 조용히 둠 · 버튼 → 실행 계획 · ⋯ 메뉴
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ReminderAction, ReminderItem } from '../../api/contract.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import {
  channelCounts,
  channelItems,
  channelOf,
  drawableActions,
  hasOverdue,
  inChannel,
  menuKinds,
  onePerTask,
  planReminderAction,
  reminderResultText,
  sortItems,
  splitQuiet,
  visibleItems,
  type PlanContext,
  type ReminderPlan,
} from './reminderModel.ts';

const act = (id: string, action: string, primary = false, extra: Partial<ReminderAction> = {}): ReminderAction => ({ id, label: id, action, primary, ...extra });

function item(over: Partial<ReminderItem> & Pick<ReminderItem, 'key'>): ReminderItem {
  const taskId = (over.taskId ?? null) as TaskId | null;
  return {
    type: 'overdue',
    group: 'due',
    title: '업무',
    reason: '이유',
    evidence: null,
    taskIds: taskId === null ? [] : [taskId],
    taskType: '회신요청',
    mailId: null,
    commitmentId: null,
    dueAtMs: null,
    counterpart: null,
    createdAtMs: 0,
    state: 'active',
    notifyCount: 0,
    lastNotifiedAtMs: null,
    actions: [],
    ...over,
    taskId,
  };
}

const ctx: PlanContext = { mailTarget: (id) => (id === (1 as MailId) ? 'mail' : id === (1001 as MailId) ? 'waiting' : null) };

test('업무 하나에는 항목 하나: 정리 제안(끝난 것 같아요)이 기한 지남보다 앞선다. 업무 없는 항목은 그대로 둔다', () => {
  const list = [
    item({ key: 'overdue:task:1', type: 'overdue', taskId: 1 as TaskId }),
    item({ key: 'resolved:task:1', type: 'resolved', group: 'cleanup', taskId: 1 as TaskId }),
    item({ key: 'due_soon:task:2', type: 'due_soon', taskId: 2 as TaskId }),
    item({ key: 'due_cluster:day:2026-11-06', type: 'due_cluster', taskIds: [2, 3] as TaskId[] }),
  ];
  assert.deepEqual(onePerTask(list).map((i) => i.key), ['resolved:task:1', 'due_soon:task:2', 'due_cluster:day:2026-11-06']);
});

test('정렬: 기한 이른 순 → 기한 없는 것은 생긴 순으로 뒤에 → 같으면 키 순', () => {
  const list = [
    item({ key: 'c', createdAtMs: 5 }),
    item({ key: 'b', dueAtMs: 200 }),
    item({ key: 'a', dueAtMs: 100 }),
    item({ key: 'd', createdAtMs: 1 }),
    item({ key: 'e', dueAtMs: 100 }),
  ];
  assert.deepEqual(sortItems(list).map((i) => i.key), ['a', 'e', 'b', 'd', 'c']);
});

test('보이는 항목: 끝난(done · dismissed) 것은 빼고, 조용히 둔 것은 따로 접는다. 건수는 보이는 목록과 같다', () => {
  const list = visibleItems([
    item({ key: 'x1', taskId: 1 as TaskId, type: 'overdue' }),
    item({ key: 'x2', taskId: 2 as TaskId, type: 'no_reply', group: 'waiting', state: 'quiet' }),
    item({ key: 'x3', taskId: 3 as TaskId, state: 'done' }),
    item({ key: 'x4', taskId: 4 as TaskId, state: 'dismissed' }),
  ]);
  assert.deepEqual(list.map((i) => i.key), ['x1', 'x2']);
  const { active, quiet } = splitQuiet(list);
  assert.deepEqual([active.map((i) => i.key), quiet.map((i) => i.key)], [['x1'], ['x2']]);
});

test('리마인더 칸은 마감 · 참석 둘: 일정참석만 참석, 다른 업무 유형은 마감, 유형 없는 항목(보낸 메일 · 약속 · 기한 몰림)은 빠진다', () => {
  const list = channelItems([
    item({ key: 'r', taskId: 1 as TaskId }),
    item({ key: 's', taskId: 4 as TaskId, taskType: '조치요청' }),
    item({ key: 'm', taskId: 2 as TaskId, type: 'meeting_prep', taskType: '일정참석' }),
    item({ key: 'w', type: 'no_reply', group: 'waiting', taskType: null }),
    item({ key: 'd', taskId: 3 as TaskId, state: 'done' }),
  ]);
  assert.deepEqual(list.map((i) => i.key), ['m', 'r', 's']); // 기한 · 생긴 때가 같으면 키 순
  assert.equal(channelOf(list[0]!), 'meeting');
  assert.deepEqual(channelCounts(list), { deadline: 2, meeting: 1 });
  assert.deepEqual(inChannel(list, 'deadline').map((i) => i.key), ['r', 's']);
});

test('기한 지남 색은 활성 기한 지남 항목이 있을 때만', () => {
  assert.equal(hasOverdue([item({ key: 'a', type: 'due_soon' })]), false);
  assert.equal(hasOverdue([item({ key: 'a', type: 'overdue', state: 'quiet' })]), false);
  assert.equal(hasOverdue([item({ key: 'a', type: 'overdue' })]), true);
});

test('버튼 → 실행 계획: 완료 · 제외는 업무 하나일 때만, 미루기는 업무 여럿도, 초안은 메일이 있을 때, 메일 열기는 열 곳이 있을 때', () => {
  const one = item({ key: 'k', taskId: 7 as TaskId, mailId: 1 as MailId });
  assert.deepEqual(planReminderAction(one, act('done', 'T03'), ctx), { type: 'status', status: 'done', taskIds: [7] });
  assert.deepEqual(planReminderAction(one, act('x', 'T10'), ctx), { type: 'status', status: 'excluded', taskIds: [7] });
  assert.deepEqual(planReminderAction(one, act('draft', 'T07'), ctx), { type: 'route', to: '/mail/inbox/1?reply=1' }); // 11-15 바로 답장 쓰기
  assert.deepEqual(planReminderAction(one, act('open', 'open_mail'), ctx), { type: 'open_mail', mailId: 1 });
  const cluster = item({ key: 'c', taskIds: [2, 3] as TaskId[] });
  assert.equal(planReminderAction(cluster, act('done', 'T03'), ctx), null);
  assert.deepEqual(planReminderAction(cluster, act('snooze', 'T05'), ctx), { type: 'snooze', taskIds: [2, 3] });
  assert.equal(planReminderAction(cluster, act('draft', 'T07'), ctx), null);
  const sent = item({ key: 's', mailId: 1001 as MailId });
  assert.deepEqual(planReminderAction(sent, act('open', 'open_mail'), ctx), { type: 'open_waiting' });
  assert.equal(planReminderAction(item({ key: 'n', mailId: 9 as MailId }), act('open', 'open_mail'), ctx), null);
  assert.equal(planReminderAction(one, act('cal', 'T13'), ctx), null, '날짜 범위가 없는 T13은 그리지 않는다');
  assert.equal(planReminderAction(one, act('x', 'T99'), ctx), null, '모르는 행동은 그리지 않는다');
});

test('실제 모드: backend에 실행 경로가 없는 초안 · 그날 업무 · 응답 대기는 화면으로 보낸다(#60 리뷰와 같은 문제)', () => {
  const http: PlanContext = { ...ctx, mode: 'http' };
  const one = item({ key: 'k', taskId: 7 as TaskId, mailId: 1 as MailId });
  // 초안은 [메일 열기]로 그 메일만 연다(#60 2차 리뷰). 같은 줄에 [메일 열기]가 이미 있으면 그리지 않는다
  assert.deepEqual(planReminderAction(one, act('draft', 'T07'), http), { type: 'route', to: '/mail/inbox/1?reply=1' });
  const withOpen = item({ key: 'k2', taskId: 7 as TaskId, mailId: 1 as MailId, actions: [act('draft', 'T07'), act('open', 'open_mail')] });
  assert.deepEqual(planReminderAction(withOpen, act('draft', 'T07'), http), { type: 'route', to: '/mail/inbox/1?reply=1' });
  assert.deepEqual(planReminderAction(one, act('day', 'T01'), http), { type: 'command', text: '오늘 뭐 해야 돼?' }); // T01은 11-14 서버에 생겼다
  assert.deepEqual(planReminderAction(one, act('wait', 'T06'), http), { type: 'open_waiting' });
  assert.deepEqual(planReminderAction(one, act('done', 'T03'), http), { type: 'status', status: 'done', taskIds: [7] });
});

test('dismiss 이유: BE-12 params.reason → 버튼 id → hide 순서', () => {
  const it = item({ key: 'k' });
  assert.deepEqual(planReminderAction(it, act('stop', 'dismiss', false, { reason: 'stop_waiting' }), ctx), { type: 'dismiss', reason: 'stop_waiting' });
  assert.deepEqual(planReminderAction(it, act('keep', 'dismiss'), ctx), { type: 'dismiss', reason: 'keep' });
  assert.deepEqual(planReminderAction(it, act('later', 'dismiss'), ctx), { type: 'dismiss', reason: 'hide' });
});

test('그릴 버튼: 최대 3개, 주 버튼이 맨 오른쪽, 자리가 모자라면 주 버튼을 남긴다', () => {
  const it = item({
    key: 'k',
    taskId: 1 as TaskId,
    mailId: 1 as MailId,
    actions: [act('done', 'T03', true), act('draft', 'T07'), act('snooze', 'T05'), act('open', 'open_mail'), act('cal', 'T13')],
  });
  assert.deepEqual(drawableActions(it, ctx).map((d) => d.action.id), ['draft', 'snooze', 'done']);
  assert.deepEqual(drawableActions(it, ctx, 1).map((d) => d.action.id), ['done']);
});

test('⋯ 메뉴: 업무가 있으면 내 일 아님, 끈 유형이면 켜기, AI 신호 유형만 잘못 알아챘어요. 버튼에 있는 것은 메뉴에 두지 않는다', () => {
  const plain = item({ key: 'a', type: 'overdue', taskId: 1 as TaskId });
  assert.deepEqual(menuKinds(plain, false, []), ['not_mine', 'mute']);
  assert.deepEqual(menuKinds(plain, true, []), ['not_mine', 'unmute']);
  const ai = item({ key: 'b', type: 'my_promise', group: 'promise' });
  assert.deepEqual(menuKinds(ai, false, []), ['mute', 'wrong_signal']);
  const drawn: { plan: ReminderPlan }[] = [{ plan: { type: 'dismiss', reason: 'wrong_signal' } }];
  assert.deepEqual(menuKinds(ai, false, drawn), ['mute']);
  const excluded: { plan: ReminderPlan }[] = [{ plan: { type: 'status', status: 'excluded', taskIds: [1 as TaskId] } }];
  assert.deepEqual(menuKinds(plain, false, excluded), ['mute']);
});

test('결과 한 줄은 과거형이고, 긴 제목은 20자에서 줄인다', () => {
  const it = { title: '1팀 보안 점검 조치 계획 회신을 위한 아주 긴 업무 제목', type: 'overdue' as const };
  assert.equal(reminderResultText('done', it), "'1팀 보안 점검 조치 계획 회신을…' 완료 처리했습니다");
  assert.equal(reminderResultText('keep', { title: '짧은 일', type: 'resolved' }), "'짧은 일' 현행 유지했습니다");
  assert.equal(reminderResultText('muted', { title: 'x', type: 'stale' }), "'장기 미처리' 알림을 해제했습니다. 목록에는 계속 표시됩니다");
  assert.equal(reminderResultText('applied', { title: 'x', type: 'due_changed' }), "'x' 기한을 변경했습니다");
});

test('기한 몰림 [당일 업무 보기] T13: 그 하루를 캘린더에서 연다. 날짜가 없거나 틀리면 넓히지 않고 그리지 않는다', () => {
  const cluster = item({ key: 'due_cluster:day:20261113', type: 'due_cluster', taskType: null, taskIds: [4, 5, 6] as TaskId[] });
  const day = (start: unknown, end: unknown) => act('open_day', 'T13', true, { range: { start, end } as { start: string; end: string } });
  for (const mode of [undefined, 'mock', 'http'] as const) {
    const c: PlanContext = { ...ctx, mode };
    assert.deepEqual(planReminderAction(cluster, day('2026-11-13', '2026-11-13'), c), { type: 'route', to: '/calendar?day=2026-11-13' });
  }
  assert.equal(planReminderAction(cluster, act('open_day', 'T13', true), ctx), null, 'start · end 없음');
  assert.equal(planReminderAction(cluster, day('2026-11-13', '2026-11-14'), ctx), null, '여러 날: 캘린더는 하루씩 보여 줘 맞는 화면이 없다');
  assert.equal(planReminderAction(cluster, day('2026-11-14', '2026-11-13'), ctx), null, '거꾸로');
  assert.equal(planReminderAction(cluster, day('2026-11-6', '2026-11-6'), ctx), null, '형식');
  assert.equal(planReminderAction(cluster, day('2026-02-30', '2026-02-30'), ctx), null, '없는 날');
  assert.equal(planReminderAction(cluster, day('', ''), ctx), null, '빈 값');
  // 다른 버튼은 그대로
  const withSnooze = { ...cluster, actions: [act('snooze_one', 'T05'), day('2026-11-13', '2026-11-13')] };
  assert.deepEqual(drawableActions(withSnooze, ctx).map((d) => d.action.id), ['snooze_one', 'open_day']);
  const broken = { ...cluster, actions: [act('snooze_one', 'T05'), day('2026-11-13', 'x')] };
  assert.deepEqual(drawableActions(broken, ctx).map((d) => d.action.id), ['snooze_one'], '날짜가 틀린 T13만 빠진다');
});
