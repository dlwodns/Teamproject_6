// 근거 형광펜(FE-5b · UX-D16) 시험. 입력 → 기대 결과.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toDashboardSource } from '../../api/adapter.ts';
import type { Task, TaskId } from '../../api/types.ts';
import { locateEvidence, orderByEvidence, segmentParagraph } from './evidence.ts';

const t = (id: number, evidenceText: string | null | undefined) => ({ id: id as TaskId, evidenceText });

test('근거 문장을 문단에서 찾아 칠할 자리를 돌려준다', () => {
  const body = ['안녕하세요.', '견적서를 11/5까지 보내 주세요. 감사합니다.'];
  const map = locateEvidence(body, [t(1, '견적서를 11/5까지 보내 주세요.')]);
  assert.equal(map.marks.length, 1);
  const m = map.byTask.get(1 as TaskId)!;
  assert.deepEqual([m.paragraph, body[1]!.slice(m.start, m.end)], [1, '견적서를 11/5까지 보내 주세요.']);
});

test('근거가 없거나(null · 빈 글) 본문에 없으면 칠하지 않는다', () => {
  const map = locateEvidence(['회의는 내일입니다.'], [t(1, null), t(2, ''), t(3, undefined), t(4, '보고서를 보내 주세요.')]);
  assert.equal(map.marks.length, 0);
  assert.equal(map.byTask.size, 0);
});

test('줄바꿈 · 겹친 공백 차이만 같은 문장으로 본다(다른 글자는 맞추지 않는다)', () => {
  const body = ['자료를\n  금요일까지   주세요.'];
  const map = locateEvidence(body, [t(1, '자료를 금요일까지 주세요.'), t(2, '자료를 금요일까지 주세요!')]);
  const m = map.byTask.get(1 as TaskId)!;
  assert.equal(body[0]!.slice(m.start, m.end), '자료를\n  금요일까지   주세요.');
  assert.equal(map.byTask.has(2 as TaskId), false);
});

test('같은 문장을 근거로 쓴 업무 둘은 형광펜 하나를 함께 쓴다', () => {
  const map = locateEvidence(['A를 하고 B도 해 주세요.'], [t(1, 'A를 하고 B도 해 주세요.'), t(2, 'A를 하고 B도 해 주세요.')]);
  assert.equal(map.marks.length, 1);
  assert.deepEqual(map.marks[0]!.taskIds, [1, 2]);
});

test('여러 줄 근거(AI-D14)는 줄마다 따로 찾아 칠한다 — 기한 문장이 다음 문단에 있어도(#73 리뷰)', () => {
  // ai evidence.attach 실제 출력: 업무 '주간 보고 자료 정리', 기한 '수요일'
  const body = '안녕하세요, 팀장님.\n주간 보고 자료 정리를 부탁드립니다.\n수요일까지 필요합니다.\n감사합니다.'.split('\n');
  const map = locateEvidence(body, [t(1, '주간 보고 자료 정리를 부탁드립니다.\n수요일까지 필요합니다.')]);
  const lines = map.linesByTask.get(1 as TaskId)!;
  assert.deepEqual(lines.map((m) => [m.paragraph, body[m.paragraph]!.slice(m.start, m.end)]), [
    [1, '주간 보고 자료 정리를 부탁드립니다.'],
    [2, '수요일까지 필요합니다.'],
  ]);
  assert.equal(map.byTask.get(1 as TaskId), lines[0]); // 업무 줄을 누르면 첫 줄로
  // 한 줄만 찾으면 찾은 줄만, 하나도 못 찾으면 '근거 문장 없음'
  const part = locateEvidence(body, [t(2, '주간 보고 자료 정리를 부탁드립니다.\n금요일까지 필요합니다.'), t(3, '없는 줄.\n또 없는 줄.')]);
  assert.equal(part.linesByTask.get(2 as TaskId)!.length, 1);
  assert.equal(part.byTask.has(3 as TaskId), false);
  // 한 문단에 그대로 이어져 있으면 한 자리로
  const one = locateEvidence(['자료를 부탁드립니다. 수요일까지 필요합니다.'], [t(4, '자료를 부탁드립니다.\n수요일까지 필요합니다.')]);
  assert.equal(one.marks.length, 1);
});

test('일부만 겹치는 근거는 다른 문장의 형광펜을 함께 쓰지 않는다', () => {
  const body = ['자료를 보내 주세요. 회의는 내일입니다. 자료를 보내 주세요.'];
  const map = locateEvidence(body, [t(1, '자료를 보내 주세요. 회의는'), t(2, '자료를 보내 주세요.')]);
  const a = map.byTask.get(1 as TaskId)!;
  const b = map.byTask.get(2 as TaskId)!;
  assert.notEqual(a, b);
  assert.ok(b.start >= a.end); // 겹치지 않는 다음 자리
  assert.deepEqual(b.taskIds, [2]);
});

test('문단을 칠한 조각 · 안 칠한 조각으로 나누고, 이어 붙이면 원문 그대로다', () => {
  const text = '첫 문장. 둘째 문장을 해 주세요. 셋째 문장.';
  const map = locateEvidence([text], [t(1, '둘째 문장을 해 주세요.')]);
  const segs = segmentParagraph(text, 0, map.marks);
  assert.deepEqual(
    segs.map((s) => [s.text, Boolean(s.mark)]),
    [
      ['첫 문장. ', false],
      ['둘째 문장을 해 주세요.', true],
      [' 셋째 문장.', false],
    ],
  );
  assert.equal(segs.map((s) => s.text).join(''), text);
  assert.deepEqual(segmentParagraph('', 0, []), [{ text: '' }]);
});

test('업무 줄 순서 = 본문 형광펜 순서, 근거 없는 업무는 원래 순서로 뒤에', () => {
  const body = ['먼저 B를 해 주세요.', '그다음 A를 해 주세요.'];
  const tasks = [t(10, '그다음 A를 해 주세요.'), t(20, null), t(30, '먼저 B를 해 주세요.'), t(40, '없는 문장')];
  const ordered = orderByEvidence(tasks, locateEvidence(body, tasks)).map((x) => x.id);
  assert.deepEqual(ordered, [30, 10, 20, 40]);
});

test('모의 데이터 v2: 근거가 있는 업무 14건은 모두 그 메일 본문에서 찾는다', () => {
  const dash = JSON.parse(readFileSync(new URL('../../api/mock/dashboard.v2.json', import.meta.url), 'utf8')) as { response: unknown };
  const mails = JSON.parse(readFileSync(new URL('../../api/mock/mails.v2.json', import.meta.url), 'utf8')) as Record<string, { body: string[] }>;
  const src = toDashboardSource(dash.response, { kind: 'mock', dataset: 'v2', version: 'v2' });
  const withEvidence = src.tasks.filter((x: Task) => x.evidenceText);
  assert.equal(withEvidence.length, 14);
  const missing = withEvidence.filter((x) => !locateEvidence(mails[String(x.mailId)]?.body ?? [], [x]).byTask.has(x.id));
  assert.deepEqual(missing.map((x) => x.id), []);
});

test('AI-42 HTML 글 조각에 걸친 근거도 조각마다 칠할 자리를 찾는다(공백은 접어 비교)', async () => {
  const { locateInPieces } = await import('./evidence.ts');
  // "<b>목요일까지</b> 의견 주세요" → 글 조각 두 개
  assert.deepEqual(locateInPieces(['안녕하세요. ', '목요일까지', '  의견\n주세요.'], '목요일까지 의견 주세요'), [
    { piece: 1, start: 0, end: 5 },
    { piece: 2, start: 0, end: 8 }, // 마침표 앞까지
  ]);
  assert.equal(locateInPieces(['다른 글'], '목요일까지'), null);
  assert.equal(locateInPieces(['아무 글'], '   '), null);
});

test('AI-42 이전 메일 카드 제목: 아웃룩 한국어 · 영문 머리에서 보낸 사람(이름만) · 보낸 날짜', async () => {
  const { parseQuoteHead, startsQuoteHead, ORIGINAL_MARK } = await import('./quote.ts');
  assert.deepEqual(parseQuoteHead('보낸 사람: 문 규남 <me@example.com>\n보낸 날짜: 2026년 11월 20일 금요일 오후 1:03\n받는 사람: 김 <k@example.com>'), {
    from: '문 규남',
    sent: '2026년 11월 20일 금요일 오후 1:03',
  });
  assert.deepEqual(parseQuoteHead('From: Kim <k@example.com> Sent: Friday, 20 November 2026 03:35:10 To: Lee'), { from: 'Kim', sent: 'Friday, 20 November 2026 03:35:10' });
  assert.equal(startsQuoteHead('  보낸 사람: 누구'), true);
  assert.equal(startsQuoteHead('안녕하세요'), false);
  assert.equal(ORIGINAL_MARK.test('-----Original Message-----'), true);
});
