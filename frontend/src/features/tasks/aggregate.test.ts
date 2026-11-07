// 실행: npm test (TZ=Asia/Seoul · TZ=UTC 어느 쪽에서도 같은 결과여야 한다)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toDashboardSource } from '../../api/adapter.ts';
import { ContractError } from '../../api/errors.ts';
import type { Category, Contact, DashboardSource, Mail, MailId, Task, TaskId } from '../../api/types.ts';
import { buildDashboard, NOTICE_TASK_POLICY, type TaskView, type TaskWithMail } from './aggregate.ts';

const mockFile = JSON.parse(readFileSync(new URL('../../api/mock/dashboard.v1.json', import.meta.url), 'utf8'));
const mockSource = () => toDashboardSource(mockFile.response, { kind: 'mock', dataset: 'test', version: 'v1' });

// 검증용 기대값 (backend/scripts/demo_expected.py 후보 B와 같은 조건: 2026-10-20T09:00 KST)
const EXPECTED = {
  mails: 100,
  tasks: 62,
  dueTodayRemaining: 13,
  overdue: 10,
  kimTeamLeadPending: 3,
  kimTeamLeadMailIds: ['M-0026', 'M-0040', 'M-0089'],
};

test('모의 데이터 v1 · 기준 시각이 맞다', () => {
  assert.equal(mockFile.meta.version, 'v1');
  assert.equal(mockFile.response.as_of, '2026-10-20T09:00:00+09:00');
});

test('집계가 기대값과 같다 (메일 · 업무 · 오늘 마감 남음 · 기한 지남)', () => {
  const view = buildDashboard(mockSource());
  assert.equal(view.mailCount, EXPECTED.mails);
  assert.equal(view.taskCount, EXPECTED.tasks);
  assert.equal(view.due.todayRemaining, EXPECTED.dueTodayRemaining);
  assert.equal(view.due.overdue, EXPECTED.overdue);
});

test('시연 ② 확인: 김 팀장(성 김 + 직급 팀장) 미처리 업무', () => {
  const view = buildDashboard(mockSource());
  // 화면 위젯이 아니라 검증 항목이다. 칸 목록에서 미처리 업무를 다시 모은다.
  const pending = new Map<number, TaskView>();
  for (const col of [...view.priority, ...view.nature]) for (const v of col.items) pending.set(v.task.id, v);
  const kim = [...pending.values()].filter(
    (v): v is TaskWithMail => v.mailState === 'found' && v.sender?.name?.startsWith('김') === true && v.sender.position === '팀장',
  );
  assert.equal(kim.length, EXPECTED.kimTeamLeadPending);
  assert.deepEqual([...new Set(kim.map((v) => v.mail.sourceId))].sort(), EXPECTED.kimTeamLeadMailIds);
});

test('오른쪽 칸에 모든 미처리 업무가 정확히 한 번씩 들어간다 (공지 정책 other)', () => {
  const view = buildDashboard(mockSource());
  const ids = view.nature.flatMap((c) => c.items.map((v) => v.task.id));
  assert.equal(new Set(ids).size, ids.length);
  if (NOTICE_TASK_POLICY === 'other') assert.equal(ids.length, view.status.pending);
});

test('기한 칸 = 기한 지남 + 오늘 + 내일, 지난 업무가 맨 위', () => {
  const view = buildDashboard(mockSource());
  const dueCol = view.priority.find((c) => c.key === 'due')!;
  assert.equal(dueCol.items.length, view.due.overdue + view.due.todayRemaining + view.due.tomorrow);
  assert.equal(dueCol.overdue, view.due.overdue);
  const firstNonOverdue = dueCol.items.findIndex((v) => v.due !== 'overdue');
  assert.ok(dueCol.items.slice(firstNonOverdue).every((v) => v.due !== 'overdue'));
});

// ── 작은 합성 데이터 ──
const t = (iso: string) => Date.parse(iso);
const ASOF = t('2026-10-20T09:00:00+09:00');

function synth(
  mails: Array<{ id: number; sender: string; category: Category | null }>,
  tasks: Array<{ id: number; mailId: number; due: string | null; status?: Task['status'] }>,
  contacts: Contact[] = [],
): DashboardSource {
  return {
    origin: { kind: 'mock', dataset: 'synthetic', version: 'test' },
    asOfMs: ASOF,
    contacts,
    mails: mails.map(
      (m): Mail => ({ id: m.id as MailId, sourceId: `S-${m.id}`, direction: 'received', sender: m.sender, subject: '', receivedAtMs: ASOF - 1, category: m.category }),
    ),
    tasks: tasks.map(
      (x): Task => ({ id: x.id as TaskId, mailId: x.mailId as MailId, text: `업무 ${x.id}`, dueAtMs: x.due ? t(x.due) : null, status: x.status ?? 'pending', seenAtMs: null }),
    ),
  };
}

test('같은 업무가 여러 칸에 있어도 전체 업무 수는 고유 레코드 수다', () => {
  const boss: Contact = { email: 'boss@example.com', name: '가', position: '상무', isSuperior: true, isFavorite: true };
  const view = buildDashboard(
    synth([{ id: 1, sender: boss.email, category: '요청' }, { id: 2, sender: 'x@example.com', category: null }], [
      { id: 10, mailId: 1, due: '2026-10-20T18:00:00+09:00' },
      { id: 11, mailId: 1, due: null },
    ], [boss]),
  );
  const columnSum = [...view.priority, ...view.nature].reduce((s, c) => s + c.items.length, 0);
  assert.equal(view.taskCount, 2);
  assert.equal(view.mailCount, 2);
  assert.equal(view.mailsWithoutTask, 1);
  assert.equal(columnSum, 7); // 기한 1 + 상급자 2 + 즐겨찾기 2 + 요청 2
  assert.notEqual(columnSum, view.taskCount);
});

test('공지 메일의 업무: 레코드 · 전체 수에서 빠지지 않고 정책대로 칸 배정', () => {
  const view = buildDashboard(synth([{ id: 1, sender: 'n@example.com', category: '공지' }], [{ id: 1, mailId: 1, due: null }]));
  assert.equal(view.taskCount, 1);
  assert.equal(view.notice.pendingTasks, 1);
  const other = view.nature.find((c) => c.key === '기타')!;
  assert.equal(other.items.length, NOTICE_TASK_POLICY === 'other' ? 1 : 0);
});

test('상태별 집계와 완료율 분모 (제외는 빼고 나중에는 넣는다)', () => {
  const view = buildDashboard(
    synth([{ id: 1, sender: 'a@example.com', category: '회신' }], [
      { id: 1, mailId: 1, due: null, status: 'pending' },
      { id: 2, mailId: 1, due: null, status: 'done' },
      { id: 3, mailId: 1, due: null, status: 'excluded' },
      { id: 4, mailId: 1, due: '2026-10-19T09:00:00+09:00', status: 'snoozed' },
    ]),
  );
  assert.deepEqual(view.status, { pending: 1, done: 1, excluded: 1, snoozed: 1 });
  assert.deepEqual(view.completion, { done: 1, denominator: 3, percent: 33 });
  assert.equal(view.due.overdue, 0); // 나중에 업무는 기한 지남 수에 넣지 않는다(미처리만)
  assert.equal(view.nature.find((c) => c.key === '회신')!.items.length, 1);
});

test('업무가 없으면 완료율은 비어 있다', () => {
  const view = buildDashboard(synth([], []));
  assert.equal(view.completion.percent, null);
  assert.equal(view.taskCount, 0);
});

test('정상 데이터: 메일 정보 없음 목록이 비어 있다', () => {
  assert.equal(buildDashboard(mockSource()).missingMail.tasks.length, 0);
});

test('업무 id · 메일 id 중복은 ContractError', () => {
  assert.throws(() => buildDashboard(synth([{ id: 1, sender: 'a', category: '요청' }], [{ id: 1, mailId: 1, due: null }, { id: 1, mailId: 1, due: null }])), ContractError);
  assert.throws(() => buildDashboard(synth([{ id: 1, sender: 'a', category: '요청' }, { id: 1, sender: 'b', category: '회신' }], [{ id: 1, mailId: 1, due: null }])), ContractError);
});

test('참조 메일 누락: 전체 실패 없이 업무 유지, 분류 · 발신자 칸에는 넣지 않고 따로 모은다', () => {
  const boss: Contact = { email: 'boss@example.com', name: '가', position: '상무', isSuperior: true, isFavorite: true };
  const src = synth(
    [{ id: 1, sender: boss.email, category: '요청' }],
    [
      { id: 10, mailId: 1, due: '2026-10-20T18:00:00+09:00' }, // 정상
      { id: 11, mailId: 99, due: '2026-10-19T09:00:00+09:00' }, // 메일 99 없음 · 기한 지남
      { id: 12, mailId: 99, due: null, status: 'done' }, // 메일 99 없음 · 완료
      { id: 13, mailId: 98, due: null, status: 'excluded' }, // 메일 98 없음 · 제외(화면에 안 보임)
    ],
    [boss],
  );
  const view = buildDashboard(src);
  // 업무 자체 값으로 세는 집계는 그대로
  assert.equal(view.taskCount, 4);
  assert.deepEqual(view.status, { pending: 2, done: 1, excluded: 1, snoozed: 0 });
  assert.deepEqual(view.completion, { done: 1, denominator: 3, percent: 33 });
  assert.equal(view.due.overdue, 1);
  // 기한 칸은 업무 기한만으로 정해지므로 메일 없는 업무도 들어간다
  const dueCol = view.priority.find((c) => c.key === 'due')!;
  assert.deepEqual(dueCol.items.map((v) => [v.task.id, v.mailState]), [[11, 'missing'], [10, 'found']]);
  // 메일이 필요한 칸에는 넣지 않는다(분류 · 발신자를 지어내지 않음, '기타'에도 넣지 않음)
  for (const col of [...view.priority.filter((c) => c.key !== 'due'), ...view.nature]) {
    assert.ok(col.items.every((v) => v.mailState === 'found'), col.key);
  }
  assert.deepEqual(view.nature.find((c) => c.key === '기타')!.items, []);
  // 따로 모은 목록: 영향받은 고유 업무 수(제외 상태 빼고), 메일 · 발신자는 null
  assert.deepEqual(view.missingMail.tasks.map((v) => v.task.id), [11, 12]);
  assert.ok(view.missingMail.tasks.every((v) => v.mail === null && v.sender === null));
  // 따로 모은 목록 때문에 전체 업무 수가 늘지 않는다
  assert.equal(view.taskCount, src.tasks.length);
});
