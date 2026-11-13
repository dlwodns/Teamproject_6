// 대시보드 v3.1 집계를 모의 데이터 v2(dashboard.v2.json)로 확인한다 — wireframe 13-9 V-2 ~ V-7 · V-9.
// 기대 숫자는 mockV2.test.ts(원본 JSON에서 따로 계산)와 13-9 표(v3.2 갱신)와 같다.
// 실행: npm test (TZ=Asia/Seoul · TZ=UTC 어느 쪽에서도 같은 결과여야 한다)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toDashboardSource } from '../../api/adapter.ts';
import { ContractError } from '../../api/errors.ts';
import type { DashboardSource, Mail, MailId, Task, TaskId } from '../../api/types.ts';
import {
  buildDashboard,
  countReceived,
  defaultPickedDay,
  doneRatioPercent,
  periodLabel,
  periodRange,
  stepDay,
  TYPE_COLUMNS,
  TYPE_LIMIT,
  typeColumnOf,
  URGENT_LIMIT,
  type DashboardModel,
} from './aggregate.ts';
import { kstDayNumber } from './deadline.ts';
import { withTaskStatuses } from './useTaskActions.ts';

const mockFile = JSON.parse(readFileSync(new URL('../../api/mock/dashboard.v2.json', import.meta.url), 'utf8'));
const source = (): DashboardSource => toDashboardSource(mockFile.response, { kind: 'mock', dataset: 'test', version: 'v2' });
const day = (iso: string) => kstDayNumber(Date.parse(`${iso}T12:00:00+09:00`));

function counts(model: DashboardModel, period: 'today' | 'week' | 'day', picked = model.today) {
  return countReceived(model, periodRange(period, model.today, picked));
}

function typeCounts(model: DashboardModel) {
  return TYPE_COLUMNS.map((k) => model.types[k].length);
}

const WEEKLY_REPORT = '주간 보고 자료 제출';

test('기준: 11/6(금) 10:42 KST가 오늘', () => {
  const m = buildDashboard(source());
  assert.equal(m.today, day('2026-11-06'));
  assert.equal(periodLabel('today', periodRange('today', m.today, m.today)), '오늘 11/6(금)');
});

test('V-2: N1 오늘 받은 업무 8건 · 처리 3 · 미처리 5', () => {
  assert.deepEqual(counts(buildDashboard(source()), 'today'), { total: 8, done: 3, open: 5 });
});

test('V-3: N1 이번 주(11/2 월 ~ 11/6 금) 23건 · 처리 8 · 미처리 15 (나중에 포함, 제외 빼기)', () => {
  const m = buildDashboard(source());
  const range = periodRange('week', m.today, m.today);
  assert.deepEqual(range, { from: day('2026-11-02'), to: day('2026-11-06') });
  assert.equal(periodLabel('week', range), '11/2(월) ~ 11/6(금)');
  assert.deepEqual(counts(m, 'week'), { total: 23, done: 8, open: 15 });
});

test('V-4: N1 날짜 → 11/5(목) 8건, ◀ → 11/4(수) 3건, ▶는 기준일 뒤로 가지 않는다', () => {
  const m = buildDashboard(source());
  const first = defaultPickedDay(m.today);
  assert.equal(periodLabel('day', periodRange('day', m.today, first)), '11/5(목)');
  assert.equal(counts(m, 'day', first).total, 8);
  const prev = stepDay(first, -1, m.today);
  assert.equal(periodLabel('day', periodRange('day', m.today, prev)), '11/4(수)');
  assert.equal(counts(m, 'day', prev).total, 3);
  assert.equal(stepDay(m.today, 1, m.today), m.today);
});

test('N1 기간을 바꿔도 2열(긴급 · 유형)은 그대로', () => {
  const m = buildDashboard(source());
  const before = [m.urgent.length, ...typeCounts(m)];
  counts(m, 'week');
  counts(m, 'day', day('2026-11-04'));
  assert.deepEqual([m.urgent.length, ...typeCounts(m)], before);
});

test('V-5: 긴급 5건, 라벨 D+2 → D+1 → ASAP → 오늘 17:00 → 오늘 18:00 (검정 · 검정 · 검정 · 파랑 · 파랑)', () => {
  const m = buildDashboard(source());
  assert.equal(m.urgent.length, 5);
  assert.ok(m.urgent.length <= URGENT_LIMIT);
  assert.deepEqual(
    m.urgent.map((r) => r.due.text),
    ['D+2', 'D+1', 'ASAP', '오늘 17:00', '오늘 18:00'],
  );
  assert.deepEqual(
    m.urgent.map((r) => r.due.kind),
    ['urgent', 'urgent', 'urgent', 'today', 'today'],
  );
  assert.equal(m.urgent[0]!.text, '1팀 보안 점검 조치 계획 회신');
  assert.equal(m.urgent[0]!.sender, '이서준 책임');
});

test('V-6: 유형 칸 회신 5 · 요청 6 · 검토 2 · 기타 1, 초록 11/10(화) · 11/11(수) · 11/12(목), 회색 기한 없음', () => {
  const m = buildDashboard(source());
  assert.deepEqual(typeCounts(m), [5, 6, 2, 1]);
  const labels = TYPE_COLUMNS.flatMap((k) => m.types[k].map((r) => r.due));
  for (const text of ['11/10(화)', '11/11(수)', '11/12(목)']) {
    assert.ok(labels.some((d) => d.text === text && d.kind === 'later'), `${text} 초록 라벨`);
  }
  assert.ok(labels.some((d) => d.text === '기한 없음' && d.kind === 'none'));
  // 긴급 업무도 유형 칸에 같이 보인다(중복 허용)
  for (const r of m.urgent) assert.ok(r.type && m.types[r.type].some((x) => x.id === r.id));
  // 칸 안 순서: 기한 지남 → ASAP → 기한 이른 순 → 기한 없음
  assert.deepEqual(
    m.types.요청.map((r) => r.due.text),
    ['D+1', 'ASAP', '오늘 17:00', '11/9(월)', '11/12(목)', '기한 없음'],
  );
  // 기본 3건이 보이고 나머지는 '+N건 더보기'
  assert.equal(m.types.요청.length - TYPE_LIMIT, 3);
  assert.equal(m.types.회신.length - TYPE_LIMIT, 2);
});

test('유형 칸은 미처리만 · 업무 유형이 메일 분류보다 앞선다(t12 · t23)', () => {
  const src = source();
  const m = buildDashboard(src);
  const all = TYPE_COLUMNS.flatMap((k) => m.types[k]);
  const pending = src.tasks.filter((t) => t.status === 'pending');
  assert.equal(all.length, pending.length); // 미처리는 모두 정확히 한 칸
  assert.equal(new Set(all.map((r) => r.id)).size, all.length);
  assert.ok(m.types.요청.some((r) => r.id === 12)); // 메일 분류는 검토, 업무 유형은 요청
  assert.ok(m.types.회신.some((r) => r.id === 23)); // 메일 분류는 요청, 업무 유형은 회신
});

test('V-7: \'주간 보고 자료 제출\' 완료 → 긴급 · 요청 두 줄 모두 빠지고 긴급 4 · 요청 5 · 처리 4 · 미처리 4', () => {
  const src = source();
  const target = src.tasks.find((t) => t.text === WEEKLY_REPORT);
  assert.ok(target);
  const before = buildDashboard(src);
  assert.ok(before.urgent.some((r) => r.id === target.id));
  assert.ok(before.types.요청.some((r) => r.id === target.id));

  const after = buildDashboard(withTaskStatuses(src, [target.id], 'done'));
  assert.equal(after.urgent.length, 4);
  assert.equal(after.types.요청.length, 5);
  assert.ok(!after.urgent.some((r) => r.id === target.id));
  assert.ok(!after.types.요청.some((r) => r.id === target.id));
  assert.deepEqual(counts(after, 'today'), { total: 8, done: 4, open: 4 });
  assert.equal(doneRatioPercent(counts(after, 'today')), 50);

  // V-8: 되돌리면(원래 상태) 모든 숫자가 원래대로
  const undone = buildDashboard(withTaskStatuses(withTaskStatuses(src, [target.id], 'done'), [target.id], 'pending'));
  assert.deepEqual([undone.urgent.length, ...typeCounts(undone)], [before.urgent.length, ...typeCounts(before)]);
  assert.deepEqual(counts(undone, 'today'), counts(before, 'today'));
});

test('V-9: 더보기 — 요청 6줄 / 확인사항 12건(확인 5 · 참고 7) / 응답 대기 2건', () => {
  const m = buildDashboard(source());
  assert.equal(m.types.요청.length, 6);
  assert.ok(m.checks);
  assert.equal(m.checks.확인.length, 5);
  assert.equal(m.checks.참고.length, 7);
  assert.ok(m.awaiting);
  assert.deepEqual(
    m.awaiting.map((w) => [w.subject, w.days]),
    [
      ['서버 증설 견적 요청드립니다', 4],
      ['통합 테스트 일정 회신 부탁드립니다', 3],
    ],
  );
});

test('확인사항: 확인은 사유 칩, 참고는 공지 · 공유, 최근에 받은 것부터, 오늘 받으면 시각만', () => {
  const m = buildDashboard(source());
  assert.ok(m.checks);
  const first = m.checks.확인[0]!;
  assert.equal(first.subject, '[보고] 고객 포털 로그인 오류 수정 반영 완료');
  assert.equal(first.chip, '완료 보고');
  assert.equal(first.whenText, '09:12');
  assert.ok(m.checks.확인.every((c, i, a) => i === 0 || a[i - 1]!.receivedAtMs >= c.receivedAtMs));
  assert.ok(m.checks.참고.every((c) => c.chip === '공지' || c.chip === '공유'));
  assert.equal(m.checks.참고.find((c) => c.subject.startsWith('[공지] 연말'))?.whenText, '11/2(월)');
});

test('새 업무 점: 오늘 받은 미처리 업무 중 seen_at 없는 것만', () => {
  const m = buildDashboard(source());
  const fresh = TYPE_COLUMNS.flatMap((k) => m.types[k]).filter((r) => r.isNew).map((r) => r.id).sort((a, b) => a - b);
  assert.deepEqual(fresh, [4, 5, 6, 8, 9]);
});

test('선택 칸이 없으면(BE-3 응답) 응답 대기 · 확인사항은 숨김(null), ASAP는 지어내지 않는다', () => {
  const src = source();
  const bare: DashboardSource = {
    ...src,
    awaiting: undefined,
    mails: src.mails.map(({ lane: _lane, ...m }) => m as Mail),
    tasks: src.tasks.map(({ dueRaw: _raw, type: _type, ...t }) => t as Task),
  };
  delete bare.awaiting;
  const m = buildDashboard(bare);
  assert.equal(m.awaiting, null);
  assert.equal(m.checks, null);
  assert.ok(!m.urgent.some((r) => r.due.text === 'ASAP'));
  // 업무 유형이 없으면 메일 분류로: 공지 · 분류 전은 기타
  assert.deepEqual(counts(m, 'week'), { total: 23, done: 8, open: 15 });
});

test('유형 칸 정하기: 업무 유형 우선, 공지 · 분류 전은 기타, 정할 수 없으면 null', () => {
  assert.equal(typeColumnOf({ type: '검토' }, { category: '요청' }), '검토');
  assert.equal(typeColumnOf({ type: '공지' }, { category: '요청' }), '기타');
  assert.equal(typeColumnOf({}, { category: '공지' }), '기타');
  assert.equal(typeColumnOf({ type: null }, { category: null }), '기타');
  assert.equal(typeColumnOf({}, { category: '회신' }), '회신');
  assert.equal(typeColumnOf({}, undefined), null);
});

// ── 응답 정합성 (v1 집계에서 이어 온 계약 방어) ──

const ASOF = Date.parse('2026-11-06T10:42:00+09:00');
function synth(tasks: Partial<Task>[], mails: Partial<Mail>[] = [{}]): DashboardSource {
  return {
    origin: { kind: 'mock', dataset: 'test', version: 'synth' },
    asOfMs: ASOF,
    contacts: [],
    mails: mails.map((m, i) => ({
      id: (i + 1) as MailId,
      sourceId: `M-${i + 1}`,
      direction: 'received',
      sender: 'a@example.com',
      subject: '제목',
      receivedAtMs: ASOF - 3600_000,
      category: '요청',
      ...m,
    })),
    tasks: tasks.map((t, i) => ({
      id: (i + 1) as TaskId,
      mailId: 1 as MailId,
      text: `업무 ${i + 1}`,
      dueAtMs: null,
      status: 'pending',
      seenAtMs: null,
      ...t,
    })),
  };
}

test('메일 id 중복 · 업무 id 중복은 ContractError, mail.id = 1과 task.id = 1은 함께 있어도 된다', () => {
  assert.doesNotThrow(() => buildDashboard(synth([{}])));
  assert.throws(() => buildDashboard(synth([{}], [{}, { id: 1 as MailId }])), ContractError);
  assert.throws(() => buildDashboard(synth([{}, { id: 1 as TaskId }])), ContractError);
});

test('업무의 메일이 없으면: 긴급에는 남고(발신자 null), 받은 날을 몰라 N1에서 빠지고, 유형은 업무 유형이 있을 때만', () => {
  const overdue = ASOF - 86400_000;
  const m = buildDashboard(synth([{ mailId: 99 as MailId, dueAtMs: overdue }, { mailId: 98 as MailId, type: '검토' }, {}]));
  assert.deepEqual(
    m.urgent.map((r) => [r.id, r.sender]),
    [[1, null]],
  );
  assert.deepEqual(counts(m, 'today'), { total: 1, done: 0, open: 1 });
  assert.deepEqual(typeCounts(m), [0, 1, 1, 0]); // t2 업무 유형 검토 · t3 메일 분류 요청, t1은 유형을 정할 수 없어 빠짐
});

test('제외 업무는 N1 전체에서 빠지고, 나중에는 미처리로 센다', () => {
  const m = buildDashboard(synth([{ status: 'excluded' }, { status: 'snoozed' }, { status: 'done' }, {}]));
  assert.deepEqual(counts(m, 'today'), { total: 3, done: 1, open: 2 });
  assert.deepEqual(typeCounts(m), [0, 1, 0, 0]); // 칸은 미처리만
});

test('같은 날 지난 기한은 D+0, 기한 정각은 오늘(파랑)', () => {
  const m = buildDashboard(synth([{ dueAtMs: ASOF - 60_000 }, { dueAtMs: ASOF }]));
  assert.deepEqual(
    m.urgent.map((r) => [r.due.text, r.due.kind]),
    [
      ['D+0', 'urgent'],
      ['오늘 10:42', 'today'],
    ],
  );
});

test('빈 받은편지함: 확인사항은 숨기지 않고 비어 있다, 응답 대기는 서버가 보낸 대로', () => {
  const m = buildDashboard({ ...synth([], []), awaiting: [] });
  assert.deepEqual(m.checks, { 확인: [], 참고: [] });
  assert.deepEqual(m.awaiting, []);
  assert.deepEqual(counts(m, 'week'), { total: 0, done: 0, open: 0 });
  assert.equal(doneRatioPercent(counts(m, 'week')), 0);
});
