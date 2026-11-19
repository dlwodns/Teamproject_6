// 메일함 · 목록 판단 시험. 기준은 모의 데이터 v2(시안 cne_v31 시연 데이터, 기준 11/6(금) 10:42)와 wireframe 13-9 V-12 · V-21 · V-22.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toDashboardSource } from '../../api/adapter.ts';
import { createMockApi } from '../../api/mockClient.ts';
import type { DashboardSource, Mail, MailId, Task, TaskId } from '../../api/types.ts';
import {
  accountsOf,
  formatListTime,
  isUrgentTask,
  mailboxSections,
  mailboxShortcutLabel,
  mailContext,
  mailFlags,
  resolveBox,
  rowStatus,
  senderName,
  taskDue,
} from './mailboxes.ts';

const raw = JSON.parse(readFileSync(new URL('../../api/mock/dashboard.v2.json', import.meta.url), 'utf8')) as { response: unknown };
const load = (): DashboardSource => toDashboardSource(raw.response, { kind: 'mock', dataset: 'v2', version: 'v2' });

const count = (src: DashboardSource, slug: string) =>
  mailboxSections(src)
    .flatMap((s) => s.items)
    .find((i) => i.slug === slug)?.count;

test('V-12: 받은편지함 24 · 업무 12 · 확인사항 12 · 즐겨찾기 2 · 상급자 1', () => {
  const src = load();
  assert.deepEqual(
    ['inbox', 'tasks', 'checks', 'favorite', 'superior'].map((s) => count(src, s)),
    [24, 12, 12, 2, 1],
  );
  // 건수와 목록이 같은 필터를 쓴다
  for (const slug of ['inbox', 'tasks', 'checks', 'favorite', 'superior']) assert.equal(resolveBox(src, slug).mails.length, count(src, slug));
});

test('메일함 묶음: 첫 묶음 · 빠른 보기(상급자 → 즐겨찾기 → 마감 → 거래처 → 응답 대기) · 분류 5종 · 계정', () => {
  const sections = mailboxSections(load());
  assert.deepEqual(
    sections.map((s) => [s.title, s.items.map((i) => i.slug)]),
    [
      [null, ['inbox', 'tasks', 'checks']],
      ['빠른 보기', ['superior', 'favorite', 'due', 'client', 'waiting']],
      ['분류', ['cat-회신', 'cat-요청', 'cat-검토', 'cat-공지', 'cat-기타']],
      ['계정', ['acc-사내', 'acc-Outlook']],
    ],
  );
  assert.equal(sections[3]!.items[0]!.label, '사내 메일');
  assert.equal(count(load(), 'waiting'), 2);
});

test('V-22: 빠른 보기 상급자 · 즐겨찾기 · 마감 · 거래처는 각 조건 메일만', () => {
  const src = load();
  const ctx = mailContext(src);
  const contact = (m: Mail) => src.contacts.find((c) => c.email === m.sender)!;
  const superior = resolveBox(src, 'superior').mails;
  assert.ok(superior.length > 0 && superior.every((m) => contact(m).isSuperior));
  assert.deepEqual(superior.map((m) => senderName(ctx, m)), ['이서준']);
  const favorite = resolveBox(src, 'favorite').mails;
  assert.ok(favorite.every((m) => contact(m).isFavorite));
  assert.deepEqual([...new Set(favorite.map((m) => senderName(ctx, m)))], ['김민준']);
  const client = resolveBox(src, 'client').mails;
  assert.equal(client.length, 3);
  assert.ok(client.every((m) => contact(m).isClient === true));
  // 마감 = 미처리 업무 중 기한 지남 · ASAP · 오늘 마감이 있는 메일. 대시보드 긴급 칸(V-5, 5건)과 같은 조건
  const due = resolveBox(src, 'due').mails;
  assert.equal(due.length, 5);
  assert.ok(due.every((m) => src.tasks.some((t) => t.mailId === m.id && isUrgentTask(t, src.asOfMs))));
  const urgentTasks = src.tasks.filter((t) => isUrgentTask(t, src.asOfMs));
  assert.deepEqual(new Set(urgentTasks.map((t) => taskDue(t, src.asOfMs).text)), new Set(['D+2', 'D+1', 'ASAP', '오늘 17:00', '오늘 18:00']));
  // 완료된 업무는 마감이 아니다
  const done = src.tasks.find((t) => t.status === 'done')!;
  assert.equal(isUrgentTask(done, src.asOfMs), false);
});

test('분류 · 계정 메일함은 그 값의 메일만, 목록은 받은 시각 최근 순', () => {
  const src = load();
  const review = resolveBox(src, 'cat-검토').mails;
  assert.ok(review.length > 0 && review.every((m) => m.category === '검토'));
  const outlook = resolveBox(src, 'acc-Outlook').mails;
  assert.ok(outlook.length === 4 && outlook.every((m) => m.account === 'Outlook'));
  const inbox = resolveBox(src, 'inbox').mails;
  for (let i = 1; i < inbox.length; i++) assert.ok(inbox[i - 1]!.receivedAtMs >= inbox[i]!.receivedAtMs);
});

test('모르는 메일함 · 숨긴 메일함은 받은편지함으로', () => {
  const src = load();
  assert.equal(resolveBox(src, 'nope').slug, 'inbox');
  assert.equal(resolveBox(src, undefined).slug, 'inbox');
  assert.equal(resolveBox(src, 'cat-보고').slug, 'inbox');
  const noAwaiting: DashboardSource = { ...src };
  delete noAwaiting.awaiting;
  assert.equal(resolveBox(noAwaiting, 'waiting').slug, 'inbox');
  assert.equal(resolveBox(src, 'waiting').kind, 'waiting');
});

test('서버가 보내지 않은 칸의 메일함은 숨긴다(확인사항 · 거래처 · 응답 대기 · 계정), 업무는 업무가 나온 메일로', () => {
  const src = load();
  const bare: DashboardSource = {
    ...src,
    contacts: src.contacts.map(({ isClient: _c, org: _o, ...c }) => c),
    mails: src.mails.map(({ lane: _l, reasons: _r, account: _a, ...m }) => m),
  };
  delete bare.awaiting;
  const slugs = mailboxSections(bare).flatMap((s) => s.items.map((i) => i.slug));
  for (const hidden of ['checks', 'client', 'waiting', 'acc-사내']) assert.ok(!slugs.includes(hidden), hidden);
  const withTasks = new Set(src.tasks.map((t) => t.mailId)).size;
  assert.equal(count(bare, 'tasks'), withTasks);
  assert.deepEqual(accountsOf(bare.mails), []);
});

test('V-21: 상급자이자 즐겨찾기인 발신자는 칩 2개(상급자 → 즐겨찾기), 마감은 칩이 아니다', () => {
  const src = load();
  const lee = src.contacts.find((c) => c.name === '이서준')!;
  const both: DashboardSource = { ...src, contacts: src.contacts.map((c) => (c === lee ? { ...c, isFavorite: true } : c)) };
  const ctx = mailContext(both);
  const mail = both.mails.find((m) => m.sender === lee.email)!;
  assert.deepEqual(mailFlags(ctx, mail), ['superior', 'favorite']);
  const client = both.mails.find((m) => m.id === 2)!; // 박지호(협력사) — 기한 지난 업무가 있어도 칩은 거래처만
  assert.deepEqual(mailFlags(ctx, client), ['client']);
});

test('목록 줄 라벨: 업무 N + 가장 급한 기한 · 모두 완료면 완료 · 확인 사유 · 참고', () => {
  const src = load();
  const ctx = mailContext(src);
  const byId = (id: number) => src.mails.find((m) => m.id === id)!;
  assert.deepEqual(rowStatus(ctx, byId(3)), { kind: 'tasks', open: 2, due: { kind: 'today', text: '오늘 18:00', full: '2026. 11. 06. (금) 18:00' } });
  assert.deepEqual(rowStatus(ctx, byId(4)), { kind: 'tasks', open: 1, due: { kind: 'urgent', text: 'ASAP', full: null } });
  assert.deepEqual(rowStatus(ctx, byId(13)), { kind: 'reasons', reasons: ['완료 보고'] });
  assert.deepEqual(rowStatus(ctx, byId(18)), { kind: 'reference' });
  const doneAll: DashboardSource = { ...src, tasks: src.tasks.map((t) => (t.mailId === 3 ? { ...t, status: 'done' as const } : t)) };
  assert.deepEqual(rowStatus(mailContext(doneAll), byId(3)), { kind: 'done' });
});

test('기한 라벨: ASAP는 원문 기한이 ASAP일 때만, 지남은 D+N', () => {
  const asOf = Date.parse('2026-11-06T10:42:00+09:00');
  const t = (over: Partial<Task>): Task => ({ id: 1 as TaskId, mailId: 1 as MailId, text: '', dueAtMs: null, status: 'pending', seenAtMs: null, ...over });
  assert.equal(taskDue(t({ dueRaw: 'ASAP' }), asOf).text, 'ASAP');
  assert.equal(taskDue(t({}), asOf).text, '기한 없음');
  assert.equal(taskDue(t({ dueRaw: '다음 주' }), asOf).kind, 'none');
  assert.deepEqual(
    [taskDue(t({ dueAtMs: Date.parse('2026-11-04T18:00:00+09:00') }), asOf).text, taskDue(t({ dueAtMs: Date.parse('2026-11-04T18:00:00+09:00') }), asOf).kind],
    ['D+2', 'urgent'],
  );
});

test('목록 시각 · 단축키 표시', () => {
  const asOf = Date.parse('2026-11-06T10:42:00+09:00');
  assert.equal(formatListTime(Date.parse('2026-11-06T09:05:00+09:00'), asOf), '09:05');
  assert.equal(formatListTime(Date.parse('2026-11-05T16:40:00+09:00'), asOf), '11/5 16:40');
  assert.equal(mailboxShortcutLabel('MacIntel'), '⌘B');
  assert.equal(mailboxShortcutLabel('Win32'), 'Ctrl B');
});

test('BE-7 보관함 · 지운 편지함(모의): 옮기면 대시보드에서 빠지고 숨긴 메일 목록에 보이며, 받은 편지함으로 되돌릴 수 있다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const d0 = await api.getDashboard();
  assert.equal(mailboxSections(d0).flatMap((s) => s.items).some((i) => i.slug === 'archive'), false); // 숨긴 목록을 못 받으면 숨김
  const [a, b] = d0.mails.filter((m) => m.direction === 'received');
  assert.equal((await api.moveMail(a!.id, 'archive')).folder, 'archive');
  await api.moveMail(b!.id, 'deleteditems');
  const d1 = await api.getDashboard();
  const hidden = await api.getHiddenMails();
  assert.equal(d1.mails.length, d0.mails.length - 2);
  assert.ok(d1.tasks.every((t) => t.mailId !== a!.id && t.mailId !== b!.id)); // 그 업무도 뺀다
  const main = mailboxSections(d1, mailContext(d1), hidden)[0]!.items.map((i) => [i.slug, i.count]);
  assert.deepEqual(main.slice(-2), [['archive', 1], ['deleted', 1]]);
  assert.deepEqual(resolveBox(d1, 'deleted', mailContext(d1), hidden).mails.map((m) => m.id), [b!.id]);
  await api.moveMail(a!.id, 'inbox');
  assert.ok((await api.getDashboard()).mails.some((m) => m.id === a!.id));
  assert.deepEqual((await api.getHiddenMails()).map((m) => m.id), [b!.id]);
});
