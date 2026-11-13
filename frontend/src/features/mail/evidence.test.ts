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
