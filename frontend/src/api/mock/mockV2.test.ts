// 모의 데이터 v2(dashboard.v2.json)를 원본 JSON에서 다시 계산해 화면 합의 테스트(wireframe.md 13-9) 숫자를 확인한다.
// 기준 숫자는 시안 cne_v31.html이 실제로 계산하는 값이다. wireframe 13-9 표는 메일 22통 · 업무 21건(영어 메일 m12 ·
// 프랑스어 메일 r7과 그 업무 t22 · t23이 들어가기 전)으로 적혀 있어 V-3 · V-4 · V-6 · V-9 · V-12가 시안과 다르다.
// 아래 주석의 '표'가 13-9 표의 숫자다.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

interface Contact { email: string; is_superior: boolean; is_favorite: boolean }
interface Mail { id: number; sender: string; received_at: string; direction: string; lane?: string }
interface Task {
  id: number;
  mail_id: number;
  text: string;
  due_at: string | null;
  status: string;
  seen_at: string | null;
  due_raw?: string | null;
  type?: string;
  evidence_text?: string | null;
}
interface Dashboard { response: { as_of: string; contacts: Contact[]; mails: Mail[]; tasks: Task[] } }

const here = dirname(fileURLToPath(import.meta.url));
const read = <T>(name: string): T => JSON.parse(readFileSync(resolve(here, name), 'utf8')) as T;
const { response: R } = read<Dashboard>('dashboard.v2.json');

const KST = 9 * 3600 * 1000;
// KST 날짜(YYYY-MM-DD) · 시각(HH:MM). 한국은 서머타임이 없어 UTC + 9시간이면 된다
const kstDay = (isoText: string) => new Date(Date.parse(isoText) + KST).toISOString().slice(0, 10);
const kstTime = (isoText: string) => new Date(Date.parse(isoText) + KST).toISOString().slice(11, 16);
const dayNum = (day: string) => Date.parse(`${day}T00:00:00Z`) / 86400000;

const now = Date.parse(R.as_of);
const today = kstDay(R.as_of);
const mailById = new Map(R.mails.map((m) => [m.id, m]));
const recvDay = (t: Task) => {
  const m = mailById.get(t.mail_id);
  assert.ok(m, `업무 ${t.id}의 메일 ${t.mail_id}가 없다`);
  return kstDay(m.received_at);
};

// N1: 받은 날 범위의 업무 수 · 처리 · 미처리(= 전체 - 처리, 나중에 포함 · 제외는 전체에서 뺌)
function counts(from: string, to: string) {
  const list = R.tasks.filter((t) => t.status !== 'excluded' && recvDay(t) >= from && recvDay(t) <= to);
  const done = list.filter((t) => t.status === 'done').length;
  return { total: list.length, done, open: list.length - done };
}

// 긴급 · 유형 칸은 status pending만(시안 isOpen)
const isOpen = (t: Task) => t.status === 'pending';
const overdue = (t: Task) => t.due_at !== null && Date.parse(t.due_at) < now;
const dueToday = (t: Task) => t.due_at !== null && !overdue(t) && kstDay(t.due_at) === today;
const asap = (t: Task) => t.due_raw === 'ASAP';
const urgentRank = (t: Task) => (overdue(t) ? 0 : asap(t) ? 1 : 2);
function label(t: Task) {
  if (asap(t)) return 'ASAP';
  assert.ok(t.due_at);
  if (overdue(t)) return `D+${dayNum(today) - dayNum(kstDay(t.due_at))}`;
  return `오늘 ${kstTime(t.due_at)}`;
}

test('기준: as_of 11/6(금) 10:42 KST, 메일은 모두 받은 메일, 업무 메일 id가 모두 있다', () => {
  assert.equal(R.as_of, '2026-11-06T10:42:00+09:00');
  assert.equal(today, '2026-11-06');
  assert.ok(R.mails.every((m) => m.direction === 'received'));
  for (const t of R.tasks) recvDay(t);
  assert.equal(R.mails.length, 24); // 표 22
  assert.equal(R.tasks.length, 23); // 표 21
});

test('V-2: 오늘 받은 업무 8 · 처리 3 · 미처리 5', () => {
  assert.deepEqual(counts('2026-11-06', '2026-11-06'), { total: 8, done: 3, open: 5 });
});

test('V-3: 이번 주(11/2~11/6) 23 · 처리 8 · 미처리 15 (표 21 · 8 · 13)', () => {
  assert.deepEqual(counts('2026-11-02', '2026-11-06'), { total: 23, done: 8, open: 15 });
});

test('V-4: 11/5 8건(표 6) → 11/4 3건', () => {
  assert.equal(counts('2026-11-05', '2026-11-05').total, 8);
  assert.equal(counts('2026-11-04', '2026-11-04').total, 3);
});

test('V-5: 긴급 5건, D+2 → D+1 → ASAP → 오늘 17:00 → 오늘 18:00', () => {
  const urgent = R.tasks
    .filter((t) => isOpen(t) && (asap(t) || overdue(t) || dueToday(t)))
    .sort((a, b) => {
      const r = urgentRank(a) - urgentRank(b);
      if (r) return r;
      if (urgentRank(a) === 0) return Date.parse(a.due_at ?? '') - Date.parse(b.due_at ?? ''); // 기한 지남: 오래된 것 먼저
      return (a.due_at ? kstTime(a.due_at) : '').localeCompare(b.due_at ? kstTime(b.due_at) : '');
    });
  assert.deepEqual(urgent.map(label), ['D+2', 'D+1', 'ASAP', '오늘 17:00', '오늘 18:00']);
});

test('V-6: 유형 칸 미처리 회신 5 · 요청 6 · 검토 2 · 기타 1 (표 4 · 5 · 2 · 1)', () => {
  const by = (ty: string) => R.tasks.filter((t) => isOpen(t) && t.type === ty).length;
  assert.deepEqual([by('회신'), by('요청'), by('검토'), by('기타')], [5, 6, 2, 1]);
});

test('V-9 · V-12: 메일함 업무 12 · 확인사항 12(확인 5 · 참고 7) · 즐겨찾기 2 · 상급자 1 · 전체 24 (표 11 · 11(5 · 6) · 2 · 1 · 22)', () => {
  const contact = new Map(R.contacts.map((c) => [c.email, c]));
  const inbox = R.mails.filter((m) => m.direction === 'received');
  const n = (f: (m: Mail) => boolean) => inbox.filter(f).length;
  assert.equal(inbox.length, 24);
  assert.equal(n((m) => m.lane === '할 일'), 12);
  assert.equal(n((m) => m.lane === '확인' || m.lane === '참고'), 12);
  assert.equal(n((m) => m.lane === '확인'), 5);
  assert.equal(n((m) => m.lane === '참고'), 7);
  assert.equal(n((m) => contact.get(m.sender)?.is_favorite === true), 2);
  assert.equal(n((m) => contact.get(m.sender)?.is_superior === true), 1);
});

test('새 업무 점: 오늘 받은 미처리 5건만 seen_at null', () => {
  assert.deepEqual(R.tasks.filter((t) => t.seen_at === null).map((t) => t.id), [4, 5, 6, 8, 9]);
});

test('V-25: 업무 2건 메일(계약서 수정본)은 근거 문장 2개', () => {
  const two = R.tasks.filter((t) => t.mail_id === 3 && t.evidence_text);
  assert.equal(two.length, 2);
});

test('V-18: 리마인더 3건(모두 미처리 업무)', () => {
  const n = read<{ items: { kind: string; rule: string | null; task_ids: number[] }[] }>('notifications.v1.json');
  const rem = n.items.filter((i) => i.kind === 'reminder' && i.rule === 'R-기한');
  assert.equal(rem.length, 3);
  const byId = new Map(R.tasks.map((t) => [t.id, t]));
  assert.ok(rem.every((i) => i.task_ids.every((id) => byId.get(id)?.status === 'pending')));
});
