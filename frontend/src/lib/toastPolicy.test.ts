import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ConfigError, ContractError, HttpError, NetworkError, NotAvailableError } from '../api/errors.ts';
import { changedToast, countTasks, failureToast, UNDONE_TITLE } from './toastPolicy.ts';

test('바뀐 업무가 있으면 되돌리기 토스트, 문구는 건수와 동작을 말한다(wireframe 13-6)', () => {
  assert.deepEqual(changedToast('done', 1, 7), { title: '업무 1건을 완료로 바꿨어요', undoable: true });
  assert.deepEqual(changedToast('done', 3, 8), { title: '업무 3건을 완료로 바꿨어요', undoable: true });
  assert.equal(changedToast('snoozed', 2, 9).title, '업무 2건을 나중으로 미뤘어요');
  assert.equal(changedToast('excluded', 2, 9).title, '업무 2건을 제외했어요');
});

test('이미 그 상태라 바뀐 것이 없으면(actionId null) 되돌릴 것이 없으니 정보 토스트', () => {
  assert.deepEqual(changedToast('done', 1, null), { title: '이미 완료된 업무예요', undoable: false });
  assert.deepEqual(changedToast('done', 3, null), { title: '업무 3건 모두 이미 완료된 상태예요', undoable: false }); // 여러 건이면 건수(#76 리뷰)
  assert.equal(changedToast('snoozed', 1, null).undoable, false);
  assert.equal(changedToast('excluded', 1, null).undoable, false);
});

test('건수는 같은 업무를 한 번으로 센다', () => {
  assert.equal(countTasks([1, 2, 2, 3]), 3);
  assert.equal(countTasks([5]), 1);
});

test('실패 문구는 \'~해요\' 체로 무엇을 못 했는지 먼저 말한다', () => {
  assert.equal(failureToast('done', new NetworkError('x')).title, '완료로 바꾸지 못했어요');
  assert.equal(failureToast('snoozed', new NetworkError('x')).title, '나중으로 미루지 못했어요');
  assert.equal(failureToast('excluded', new NetworkError('x')).title, '제외하지 못했어요');
  assert.equal(failureToast('undo', new NetworkError('x')).title, '되돌리지 못했어요');
  assert.equal(UNDONE_TITLE, '되돌렸어요');
});

test('다시 해 볼 만한 실패에만 [다시 시도]: 연결 · 시간 초과 · 서버 오류', () => {
  assert.equal(failureToast('done', new NetworkError('서버가 15초 안에 응답하지 않았다')).retry, true);
  assert.equal(failureToast('done', new HttpError(500, 'x')).retry, true);
  assert.equal(failureToast('done', new HttpError(503, 'x')).retry, true);
  assert.equal(failureToast('done', new Error('알 수 없음')).retry, true);
});

test('다시 보내도 같은 실패에는 [다시 시도]를 붙이지 않는다', () => {
  for (const status of [401, 404, 409, 422]) assert.equal(failureToast('done', new HttpError(status, 'x')).retry, false, String(status));
  assert.equal(failureToast('done', new ContractError('x')).retry, false);
  assert.equal(failureToast('done', new ConfigError('x')).retry, false);
  assert.equal(failureToast('done', new NotAvailableError('/x', 404)).retry, false);
});

test('409는 화면을 서버 값으로 다시 맞췄다고 알린다(실패해도 다시 불러온다)', () => {
  assert.match(failureToast('undo', new HttpError(409, 'x')).description ?? '', /이미 다른 곳에서 바뀌었어요/);
});

test('오류 원문 · 주소를 화면에 보이지 않는다', () => {
  const copy = failureToast('done', new HttpError(500, 'PATCH /api/tasks/3 응답 500'));
  assert.doesNotMatch(`${copy.title} ${copy.description}`, /\/api|PATCH/);
  assert.match(copy.description ?? '', /오류 코드 500/);
});
