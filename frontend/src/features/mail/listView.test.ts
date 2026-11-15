// FE-5d 메일 관리 판단 시험: 날짜 묶음 · 고정 차례 · 여러 통 고르기 · 단축키 · 메일함 안 읽음 수 · 읽음/고정 요청(모의 · 실제).
// 기준은 모의 데이터 v2(기준 11/6(금) 10:42 KST).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toDashboardSource } from '../../api/adapter.ts';
import { NotAvailableError } from '../../api/errors.ts';
import { createHttpApi } from '../../api/httpClient.ts';
import { createMockApi } from '../../api/mockClient.ts';
import type { DashboardSource, Mail, MailId } from '../../api/types.ts';
import {
  bulkPinTarget,
  dateGroupOf,
  EMPTY_SELECTION,
  flattenGroups,
  groupMails,
  pruneSelection,
  restoreMails,
  stepMail,
  toggleSelect,
  unreadCount,
  withMailPatch,
} from './listView.ts';
import { mailboxSections, resolveBox } from './mailboxes.ts';
import { MAIL_SHORTCUT_HELP, mailShortcutOf } from './mailShortcuts.ts';

const raw = JSON.parse(readFileSync(new URL('../../api/mock/dashboard.v2.json', import.meta.url), 'utf8')) as { response: unknown };
const load = (): DashboardSource => toDashboardSource(raw.response, { kind: 'mock', dataset: 'v2', version: 'v2' });
const kst = (s: string) => Date.parse(`${s}+09:00`);
const M = (n: number) => n as MailId;
const AS_OF = kst('2026-11-06T10:42:00'); // 금요일

const mail = (id: number, at: string, extra: Partial<Mail> = {}): Mail => ({
  id: M(id),
  sourceId: `M-${id}`,
  direction: 'received',
  sender: 'a@x',
  subject: `메일 ${id}`,
  receivedAtMs: kst(at),
  category: null,
  ...extra,
});

test('날짜 묶음: 오늘 · 어제 · 이번 주(월요일 시작) · 지난주 · 이전, KST 자정 경계', () => {
  assert.equal(dateGroupOf(kst('2026-11-06T00:00:00'), AS_OF), 'today');
  assert.equal(dateGroupOf(kst('2026-11-06T23:00:00'), AS_OF), 'today'); // 기준보다 뒤(미래)도 오늘
  assert.equal(dateGroupOf(kst('2026-11-05T23:59:00'), AS_OF), 'yesterday');
  assert.equal(dateGroupOf(kst('2026-11-03T09:00:00'), AS_OF), 'thisWeek'); // 화
  assert.equal(dateGroupOf(kst('2026-11-02T00:00:00'), AS_OF), 'thisWeek'); // 월 0시
  assert.equal(dateGroupOf(kst('2026-11-01T23:59:00'), AS_OF), 'lastWeek'); // 일
  assert.equal(dateGroupOf(kst('2026-10-26T00:00:00'), AS_OF), 'lastWeek'); // 지난주 월
  assert.equal(dateGroupOf(kst('2026-10-25T23:59:00'), AS_OF), 'older');
  // 기준일이 월요일이면 어제(일요일)는 지난주보다 '어제'가 먼저
  const monday = kst('2026-11-09T09:00:00');
  assert.equal(dateGroupOf(kst('2026-11-08T12:00:00'), monday), 'yesterday');
  assert.equal(dateGroupOf(kst('2026-11-07T12:00:00'), monday), 'lastWeek');
  // UTC로는 같은 날이지만 KST로는 다른 날(KST 00:30 = UTC 전날 15:30)
  assert.equal(dateGroupOf(Date.parse('2026-11-05T15:30:00Z'), AS_OF), 'today');
});

test('목록 묶음: 고정됨이 맨 위, 빈 묶음은 빼고, 각 묶음은 최근 순. 편 차례가 키보드 · 다음 메일의 차례', () => {
  const mails = [
    mail(1, '2026-11-06T09:00:00'),
    mail(2, '2026-11-05T09:00:00', { pinnedAtMs: kst('2026-11-06T10:00:00') }),
    mail(3, '2026-11-06T10:00:00'),
    mail(4, '2026-10-01T09:00:00', { pinnedAtMs: kst('2026-11-06T10:30:00') }),
    mail(5, '2026-10-01T09:00:00', { pinnedAtMs: null }),
  ];
  const groups = groupMails(mails, AS_OF);
  assert.deepEqual(
    groups.map((g) => [g.label, g.mails.map((m) => m.id)]),
    [
      ['고정됨', [2, 4]], // 고정한 차례가 아니라 받은 시각 최근 순
      ['오늘', [3, 1]],
      ['이전', [5]],
    ],
  );
  const order = flattenGroups(groups);
  assert.deepEqual(order.map((m) => m.id), [2, 4, 3, 1, 5]);
  assert.equal(stepMail(order, M(4), 1)?.id, 3);
  assert.equal(stepMail(order, M(4), -1)?.id, 2);
  assert.equal(stepMail(order, M(5), 1)?.id, 5); // 끝에서는 그대로
  assert.equal(stepMail(order, null, 1)?.id, 2);
  assert.equal(stepMail([], null, 1), null);
});

test('모의 v2 받은편지함: 오늘 · 어제 · 이번 주 묶음, 메일 수는 그대로', () => {
  const src = load();
  const box = resolveBox(src, 'inbox');
  const groups = groupMails(box.mails, src.asOfMs);
  assert.equal(groups[0]?.label, '오늘');
  assert.equal(flattenGroups(groups).length, box.mails.length);
  assert.ok(groups.every((g) => g.mails.length > 0));
});

test('읽음 · 고정 화면 먼저 바꾸기: 칸이 없는 메일은 건드리지 않고, 실패하면 그 메일만 되돌린다', () => {
  const src: DashboardSource = {
    origin: { kind: 'mock', dataset: 't', version: 't' },
    asOfMs: AS_OF,
    contacts: [],
    tasks: [],
    mails: [mail(1, '2026-11-06T09:00:00', { readAtMs: null, pinnedAtMs: null }), mail(2, '2026-11-06T09:00:00'), mail(3, '2026-11-06T09:00:00', { readAtMs: 5 })],
  };
  const read = withMailPatch(src, [M(1), M(2), M(3)], { read: true }, 100);
  assert.deepEqual(read.mails.map((m) => m.readAtMs), [100, undefined, 5]); // 이미 읽은 메일은 처음 읽은 시각 유지
  assert.equal(read.mails[1], src.mails[1]); // 칸 없는 메일은 같은 객체
  const pinned = withMailPatch(read, [M(1)], { pinned: true, read: false }, 200);
  assert.deepEqual([pinned.mails[0]!.pinnedAtMs, pinned.mails[0]!.readAtMs], [200, null]);
  assert.equal(withMailPatch(src, [M(2)], { pinned: true }, 1), src); // 바뀐 게 없으면 원자료 그대로
  const back = restoreMails(pinned, src, [M(1)]);
  assert.deepEqual([back.mails[0]!.pinnedAtMs, back.mails[0]!.readAtMs, back.mails[2]!.readAtMs], [null, null, 5]);
});

test('여러 통 고르기: 하나씩 넣고 빼기 · Shift 범위(보이는 차례, 기존 것 유지) · 목록에서 빠지면 정리', () => {
  const order = [1, 2, 3, 4, 5, 6].map(M);
  let s = toggleSelect(EMPTY_SELECTION, order, M(2));
  assert.deepEqual([[...s.ids], s.anchor], [[2], 2]);
  s = toggleSelect(s, order, M(5), { range: true });
  assert.deepEqual([...s.ids].sort(), [2, 3, 4, 5]);
  assert.equal(s.anchor, 2); // 범위는 기준점을 옮기지 않는다
  s = toggleSelect(s, order, M(3)); // 하나 빼기
  assert.deepEqual([...s.ids].sort(), [2, 4, 5]);
  s = toggleSelect(s, order, M(1), { range: true }); // 거꾸로 범위(기준점 3부터 1까지)
  assert.deepEqual([...s.ids].sort(), [1, 2, 3, 4, 5]);
  // 기준점 없이 Shift면 하나만
  assert.deepEqual([...toggleSelect(EMPTY_SELECTION, order, M(4), { range: true }).ids], [4]);
  const pruned = pruneSelection(s, [M(1), M(2)]);
  assert.deepEqual([[...pruned.ids].sort(), pruned.anchor], [[1, 2], null]);
  assert.equal(pruneSelection(pruned, [M(1), M(2), M(9)]), pruned); // 바뀐 게 없으면 같은 객체
  // 묶음 [고정]: 모두 고정이면 해제, 하나라도 아니면 고정
  assert.equal(bulkPinTarget([mail(1, '2026-11-06T09:00:00', { pinnedAtMs: 1 }), mail(2, '2026-11-06T09:00:00', { pinnedAtMs: null })]), true);
  assert.equal(bulkPinTarget([mail(1, '2026-11-06T09:00:00', { pinnedAtMs: 1 })]), false);
});

const key = (k: string, mods: Partial<{ ctrlKey: boolean; shiftKey: boolean; altKey: boolean; metaKey: boolean; code: string; target: unknown; isComposing: boolean }> = {}) => ({
  key: k,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
  metaKey: false,
  target: { tagName: 'BUTTON' },
  ...mods,
});

test('단축키(Outlook 호환): Ctrl+R · R 답장, Ctrl+Q · U 읽음, Insert 고정, Delete 제외, Ctrl+. , 다음 · 이전, ? 도움말', () => {
  assert.equal(mailShortcutOf(key('r', { ctrlKey: true })), 'reply');
  assert.equal(mailShortcutOf(key('ㄱ', { code: 'KeyR' })), 'reply'); // 한글 자판
  assert.equal(mailShortcutOf(key('q', { ctrlKey: true })), 'read');
  assert.equal(mailShortcutOf(key('u', { ctrlKey: true })), 'unread');
  assert.equal(mailShortcutOf(key('Insert')), 'pin');
  assert.equal(mailShortcutOf(key('Delete')), 'exclude');
  assert.equal(mailShortcutOf(key('.', { ctrlKey: true })), 'next');
  assert.equal(mailShortcutOf(key('>', { ctrlKey: true, code: 'Period' })), 'next');
  assert.equal(mailShortcutOf(key(',', { ctrlKey: true })), 'prev');
  assert.equal(mailShortcutOf(key('?', { shiftKey: true })), 'help');
  assert.equal(mailShortcutOf(key('Escape')), 'clear');
  // 그 밖 · 막는 경우
  assert.equal(mailShortcutOf(key('q')), null); // Ctrl 없는 Q는 아무것도 아님
  assert.equal(mailShortcutOf(key('r', { ctrlKey: true, shiftKey: true })), null);
  assert.equal(mailShortcutOf(key('r', { metaKey: true })), null);
  assert.equal(mailShortcutOf(key('r', { altKey: true })), null);
  assert.equal(mailShortcutOf(key('r', { target: { tagName: 'TEXTAREA' } })), null); // 입력 중
  assert.equal(mailShortcutOf(key('Delete', { target: { tagName: 'INPUT', type: 'text' } })), null);
  assert.equal(mailShortcutOf(key('r', { isComposing: true })), null); // 한글 조합 중
  // 도움말에 모든 단축키가 있다
  const help = MAIL_SHORTCUT_HELP.flatMap((r) => r.keys).join(' ');
  for (const k of ['Ctrl R', 'Ctrl Q', 'Ctrl U', 'Insert', 'Delete', 'Ctrl .', 'Ctrl ,', 'Ctrl B', 'Enter', '?']) assert.ok(help.includes(k), k);
});

test('메일함 안 읽음 수: 읽음 칸이 있으면 메일함마다 세고, 읽으면 줄어든다. 칸이 없으면 숨김', () => {
  const src = load();
  const unread = (s: DashboardSource, slug: string) =>
    mailboxSections(s)
      .flatMap((x) => x.items)
      .find((i) => i.slug === slug)?.unread;
  const inbox = unread(src, 'inbox')!;
  assert.equal(inbox, src.mails.filter((m) => m.direction === 'received' && m.readAtMs === null).length);
  assert.ok(inbox > 0);
  const first = resolveBox(src, 'inbox').mails.find((m) => m.readAtMs === null)!;
  const after = withMailPatch(src, [first.id], { read: true }, src.asOfMs);
  assert.equal(unread(after, 'inbox'), inbox - 1);
  assert.equal(unread(src, 'waiting'), undefined); // 응답 대기는 세지 않는다
  const noRead = { ...src, mails: src.mails.map(({ readAtMs: _r, ...m }) => m as Mail) };
  assert.equal(unread(noRead, 'inbox'), undefined);
  assert.equal(unreadCount([]), undefined);
});

test('모의 PATCH /mails/{id}: 읽음 · 안 읽음 · 고정, 다시 불러와도 남는다. 처음엔 아무것도 고정 안 함', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const d0 = await api.getDashboard();
  assert.ok(d0.mails.every((m) => m.pinnedAtMs === null));
  const target = d0.mails.find((m) => m.readAtMs === null)!;
  const read = await api.patchMail(target.id, { read: true });
  assert.equal(typeof read.readAtMs, 'number');
  const again = await api.patchMail(target.id, { read: true });
  assert.equal(again.readAtMs, read.readAtMs); // 처음 읽은 시각 유지
  const pinned = await api.patchMail(target.id, { pinned: true, read: false });
  assert.deepEqual([typeof pinned.pinnedAtMs, pinned.readAtMs], ['number', null]);
  const d1 = await api.getDashboard();
  assert.equal(d1.mails.find((m) => m.id === target.id)!.pinnedAtMs, pinned.pinnedAtMs);
  await assert.rejects(api.patchMail(M(9999), { read: true }), /없는 메일/);
});

test('실제 모드 PATCH /api/mails/{id}: snake_case 본문, 404 · 405 · 501은 NotAvailableError(화면이 숨김)', async () => {
  const original = globalThis.fetch;
  const calls: { url: string; method: string; body: unknown }[] = [];
  try {
    globalThis.fetch = (async (url: string, init: RequestInit) => {
      calls.push({ url: String(url), method: String(init.method), body: JSON.parse(String(init.body)) });
      const body = { id: 7, source_id: 'M-7', direction: 'received', sender: 'a@x', subject: 's', received_at: '2026-11-06T09:00:00+09:00', read_at: null, pinned_at: '2026-11-06T10:00:00+09:00' };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as unknown as typeof fetch;
    const m = await createHttpApi('/api').patchMail(M(7), { pinned: true, read: false });
    assert.deepEqual([m.readAtMs, m.pinnedAtMs], [null, kst('2026-11-06T10:00:00')]);
    assert.deepEqual(calls[0], { url: '/api/mails/7', method: 'PATCH', body: { read: false, pinned: true } });
    for (const status of [404, 405, 501]) {
      globalThis.fetch = (async () => new Response('', { status })) as typeof fetch;
      await assert.rejects(createHttpApi('/api').patchMail(M(7), { read: true }), NotAvailableError);
    }
  } finally {
    globalThis.fetch = original;
  }
});
