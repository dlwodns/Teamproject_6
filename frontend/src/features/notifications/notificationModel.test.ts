// 알림 센터 🔔의 판단(FE-10 · FE-16): 리마인더 알림 가르기 · 배지 수 · 묶음 칩 · 최대 5줄 · 누르면 갈 곳 · 새 알림 토스트
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AppNotification, NotificationId } from '../../api/contract.ts';
import {
  bellLabel,
  groupChips,
  isReminderNotification,
  newReminderNotifications,
  notificationTarget,
  popoverRows,
  splitNotifications,
  unreadReminderCount,
} from './notificationModel.ts';

function n(id: number, over: Partial<AppNotification> = {}): AppNotification {
  return {
    id: id as NotificationId,
    kind: 'reminder',
    title: `알림 ${id}`,
    body: null,
    taskIds: [],
    rule: null,
    scheduledAtMs: null,
    readAtMs: null,
    answeredAtMs: null,
    createdAtMs: id,
    ...over,
  };
}

test('리마인더 알림: 묶음 칸이 있거나 리마인더 · 묶음 · 답장 확인 종류. 새 업무 알림은 아니다', () => {
  assert.equal(isReminderNotification(n(1)), true);
  assert.equal(isReminderNotification(n(2, { kind: 'digest' })), true);
  assert.equal(isReminderNotification(n(3, { kind: 'reply_confirm' })), true);
  assert.equal(isReminderNotification(n(4, { kind: 'new_tasks' })), false);
  assert.equal(isReminderNotification(n(5, { kind: 'new_tasks', group: 'due' })), true);
});

test('탭 나누기는 최근 것부터, 배지는 안 읽은 리마인더 알림만 센다', () => {
  const list = [n(1), n(3, { readAtMs: 10 }), n(2, { kind: 'new_tasks' }), n(4, { kind: 'digest' })];
  const { reminders, others } = splitNotifications(list);
  assert.deepEqual(reminders.map((x) => x.id), [4, 3, 1]);
  assert.deepEqual(others.map((x) => x.id), [2]);
  assert.equal(unreadReminderCount(list), 2);
  assert.equal(bellLabel(2), '알림 센터 열기, 읽지 않은 리마인더 2개');
  assert.equal(bellLabel(0), '알림 센터 열기');
  assert.equal(bellLabel(null), '알림 센터 열기');
});

test('묶음 칩: 건수가 있는 묶음만 정해진 순서로, 넘치면 앞 3개 + 전체 보기', () => {
  const rows = [{ group: 'cleanup' as const }, { group: 'due' as const }, { group: 'due' as const }, { group: null }];
  assert.deepEqual(groupChips(rows), { chips: [{ group: 'due', count: 2 }, { group: 'cleanup', count: 1 }], overflow: false });
  const many = (['due', 'waiting', 'promise', 'revisit', 'prepare'] as const).map((group) => ({ group }));
  const r = groupChips(many);
  assert.equal(r.overflow, true);
  assert.deepEqual(r.chips.map((c) => c.group), ['due', 'waiting', 'promise']);
});

test('줄은 최대 5개, 숨은 수는 따로', () => {
  const rows = Array.from({ length: 7 }, (_, i) => ({ id: i, group: i < 6 ? ('due' as const) : ('waiting' as const) }));
  assert.deepEqual(popoverRows(rows, 'all').more, 2);
  assert.equal(popoverRows(rows, 'all').rows.length, 5);
  assert.deepEqual(popoverRows(rows, 'waiting'), { rows: [{ id: 6, group: 'waiting' }], more: 0 });
  assert.equal(popoverRows(rows, 'due').more, 1);
});

test('누르면 갈 곳: 항목 키 → 그 항목, 아침 묶음 → 브리핑, 그 밖 → 리마인더 전체', () => {
  assert.deepEqual(notificationTarget({ reminderKey: 'overdue:task:1', group: 'due', rule: 'R-기한', kind: 'reminder' }), { kind: 'reminder', key: 'overdue:task:1' });
  assert.deepEqual(notificationTarget({ reminderKey: null, group: null, rule: 'R-아침', kind: 'reminder' }), { kind: 'briefing' });
  assert.deepEqual(notificationTarget({ reminderKey: null, group: null, rule: null, kind: 'digest' }), { kind: 'briefing' });
  assert.deepEqual(notificationTarget({ reminderKey: null, group: 'due', rule: null, kind: 'reminder' }), { kind: 'reminders' });
});

test('새 리마인더 토스트: 처음 받은 목록은 띄우지 않고, 그 뒤 새로 온 안 읽은 리마인더 알림만', () => {
  const list = [n(1), n(2), n(3, { kind: 'new_tasks' }), n(4, { readAtMs: 1 })];
  assert.deepEqual(newReminderNotifications(null, list), []);
  assert.deepEqual(newReminderNotifications(new Set([1]), list).map((x) => x.id), [2]);
});
