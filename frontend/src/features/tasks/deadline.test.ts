import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  dueLabel,
  dueState,
  formatKstDay,
  formatKstFull,
  isAsap,
  kstDayNumber,
  kstDayStartMs,
  kstMondayOf,
  kstWeekday,
  taskDueBadge,
} from './deadline.ts';

const t = (iso: string) => Date.parse(iso);
const ASOF = t('2026-10-20T09:00:00+09:00');

test('기한 경계: 기준 시각 정각은 오늘 마감(남음), 1ms 전은 기한 지남', () => {
  assert.equal(dueState(ASOF, ASOF), 'today');
  assert.equal(dueState(ASOF - 1, ASOF), 'overdue');
  assert.equal(dueState(t('2026-10-20T08:30:00+09:00'), ASOF), 'overdue');
});

test('KST 날짜 경계: 23:59:59는 오늘, 다음 날 00:00은 내일', () => {
  assert.equal(dueState(t('2026-10-20T23:59:59+09:00'), ASOF), 'today');
  assert.equal(dueState(t('2026-10-21T00:00:00+09:00'), ASOF), 'tomorrow');
  assert.equal(dueState(t('2026-10-21T23:59:59+09:00'), ASOF), 'tomorrow');
  assert.equal(dueState(t('2026-10-22T00:00:00+09:00'), ASOF), 'later');
});

test('UTC 날짜와 KST 날짜가 다른 시각도 KST로 판정한다', () => {
  // 2026-10-21T00:30 KST = 2026-10-20T15:30Z — UTC로는 기준 시각과 같은 날이지만 KST로는 내일
  assert.equal(dueState(t('2026-10-20T15:30:00Z'), ASOF), 'tomorrow');
  // 기준 시각이 KST 새벽이면 UTC로는 전날이다
  const earlyAsOf = t('2026-10-20T01:00:00+09:00'); // 2026-10-19T16:00Z
  assert.equal(dueState(t('2026-10-20T18:00:00+09:00'), earlyAsOf), 'today');
  assert.equal(kstDayNumber(earlyAsOf), kstDayNumber(t('2026-10-20T23:00:00+09:00')));
});

test('기한 없음은 due_at이 없을 때만', () => {
  assert.equal(dueState(null, ASOF), 'none');
});

test('표시용 시각은 실행 환경 시간대와 무관하게 KST', () => {
  assert.match(formatKstFull(ASOF), /2026.*10.*20.*09:00/);
});

test('기한 라벨(UX-D10): 짧은 글자만, ⚠ · \'기한 지남\' 글자 없음', () => {
  const text = (iso: string | null) => dueLabel(iso === null ? null : t(iso), ASOF).text;
  assert.equal(text('2026-10-18T18:00:00+09:00'), 'D+2');
  assert.equal(text('2026-10-20T08:30:00+09:00'), 'D+0'); // 같은 날 이미 지남
  assert.equal(text('2026-10-20T18:00:00+09:00'), '오늘 18:00');
  assert.equal(text('2026-10-21T12:00:00+09:00'), '내일 12:00');
  assert.equal(text('2026-10-23T09:00:00+09:00'), '10/23(금)');
  assert.equal(text(null), '기한 없음');
  for (const iso of ['2026-10-18T18:00:00+09:00', '2026-10-20T18:00:00+09:00']) {
    assert.doesNotMatch(text(iso), /⚠|기한 지남|마감/);
  }
});

test('기한 라벨 상태 · 전체 시각', () => {
  const l = dueLabel(t('2026-10-18T18:00:00+09:00'), ASOF);
  assert.equal(l.state, 'overdue');
  assert.match(l.full!, /2026.*10.*18.*18:00/);
  assert.equal(dueLabel(null, ASOF).full, null);
});

// ── v3.1 업무 줄 기한 라벨(taskDueBadge) · 날짜 도우미 ──

const NOW = t('2026-11-06T10:42:00+09:00'); // 금요일

test('taskDueBadge: D+N은 KST 달력 날짜 차이(같은 날 지나면 D+0) · 검정', () => {
  assert.deepEqual(
    [t('2026-11-04T18:00:00+09:00'), t('2026-11-05T23:59:00+09:00'), t('2026-11-06T09:00:00+09:00')].map((d) => taskDueBadge(d, undefined, NOW).text),
    ['D+2', 'D+1', 'D+0'],
  );
  const b = taskDueBadge(t('2026-11-04T18:00:00+09:00'), null, NOW);
  assert.equal(b.kind, 'urgent');
  assert.match(b.srText ?? '', /^기한 지남 · /);
  assert.ok(b.fullTime);
});

test('taskDueBadge: 오늘 파랑 · 내일과 그 뒤 초록 · 없음 회색', () => {
  assert.deepEqual(
    [t('2026-11-06T17:00:00+09:00'), t('2026-11-07T12:00:00+09:00'), t('2026-11-10T18:00:00+09:00'), null].map((d) => {
      const b = taskDueBadge(d, undefined, NOW);
      return [b.text, b.kind];
    }),
    [
      ['오늘 17:00', 'today'],
      ['내일 12:00', 'later'],
      ['11/10(화)', 'later'],
      ['기한 없음', 'none'],
    ],
  );
});

test('ASAP는 due_at이 없고 원문 기한이 ASAP일 때만(검정). 원문만 있으면 원문을 회색으로', () => {
  assert.equal(isAsap(null, 'ASAP'), true);
  assert.equal(isAsap(null, ' asap '), true);
  assert.equal(isAsap(null, undefined), false); // 서버가 원문 기한을 안 보내면 지어내지 않는다
  assert.equal(isAsap(NOW, 'ASAP'), false);
  assert.deepEqual(
    [taskDueBadge(null, 'ASAP', NOW).text, taskDueBadge(null, 'ASAP', NOW).kind],
    ['ASAP', 'urgent'],
  );
  const raw = taskDueBadge(null, '미팅 전에', NOW);
  assert.deepEqual([raw.state, raw.kind, raw.text], ['raw', 'none', '미팅 전에']);
  assert.equal(taskDueBadge(null, '  ', NOW).text, '기한 없음');
});

test('KST 날짜 도우미: 요일 · 그 주 월요일 · 0시 · 짧은 날짜', () => {
  const fri = kstDayNumber(NOW);
  assert.equal(kstWeekday(fri), 5);
  assert.equal(formatKstDay(kstMondayOf(fri)), '11/2(월)');
  assert.equal(kstMondayOf(kstMondayOf(fri)), kstMondayOf(fri));
  assert.equal(kstDayStartMs(fri), t('2026-11-06T00:00:00+09:00'));
  assert.equal(formatKstDay(fri - 1), '11/5(목)');
  // 일요일은 그 주(월요일 시작)의 마지막 날
  assert.equal(formatKstDay(kstMondayOf(kstDayNumber(t('2026-11-08T23:00:00+09:00')))), '11/2(월)');
});
