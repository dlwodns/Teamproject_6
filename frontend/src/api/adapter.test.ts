import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseOffsetTime, toDashboardSource } from './adapter.ts';
import { readApiConfig } from './config.ts';
import { ContractError } from './errors.ts';

test('시간대가 붙은 시각만 받는다 (+09:00 · Z)', () => {
  assert.equal(parseOffsetTime('2026-10-20T09:00:00+09:00', 'x'), parseOffsetTime('2026-10-20T00:00:00Z', 'x'));
  assert.throws(() => parseOffsetTime('2026-10-20T09:00', 'x'), ContractError);
  assert.throws(() => parseOffsetTime('2026-10-20T09:00:00', 'x'), ContractError);
  assert.throws(() => parseOffsetTime(null, 'x'), ContractError);
});

test('형식이 다른 응답은 ContractError (고쳐 쓰지 않는다)', () => {
  const origin = { kind: 'http', baseUrl: '/api' } as const;
  const ok = { as_of: '2026-10-20T09:00:00+09:00', contacts: [], mails: [], tasks: [] };
  assert.equal(toDashboardSource(ok, origin).tasks.length, 0);
  assert.throws(() => toDashboardSource({ ...ok, as_of: '2026-10-20T09:00' }, origin), ContractError);
  assert.throws(() => toDashboardSource({ ...ok, tasks: {} }, origin), ContractError);
  const mail = { id: 1, source_id: 'M-1', direction: 'received', sender: 'a', subject: '', received_at: '2026-10-20T08:00:00+09:00', category: '보고' };
  assert.throws(() => toDashboardSource({ ...ok, mails: [mail] }, origin), ContractError); // 구버전 분류명
});

test('VITE_API_MODE: 기본 mock, 잘못된 값은 설정 오류', () => {
  assert.deepEqual(readApiConfig({}), { mode: 'mock', baseUrl: '/api' });
  assert.deepEqual(readApiConfig({ VITE_API_MODE: 'http', VITE_API_BASE: '/api/' }), { mode: 'http', baseUrl: '/api' });
  assert.throws(() => readApiConfig({ VITE_API_MODE: 'real' }));
});

test('category: null · 생략은 미분류(null), 5분류는 그대로, 그 밖의 값은 ContractError', () => {
  const origin = { kind: 'http', baseUrl: '/api' } as const;
  const base = { id: 1, source_id: 'M-1', direction: 'received', sender: 'a', subject: '', received_at: '2026-10-20T08:00:00+09:00' };
  const one = (mail: object) => toDashboardSource({ as_of: '2026-10-20T09:00:00+09:00', contacts: [], mails: [mail], tasks: [] }, origin).mails[0]!.category;
  assert.equal(one({ ...base, category: null }), null);
  assert.equal(one(base), null); // 필드 생략
  assert.equal(one({ ...base, category: '검토' }), '검토');
  assert.throws(() => one({ ...base, category: '보고' }), ContractError);
  assert.throws(() => one({ ...base, category: 3 }), ContractError);
  assert.throws(() => one({ ...base, category: '' }), ContractError);
});

test('category 외 필수 필드는 그대로 필수(생략하면 ContractError)', () => {
  const origin = { kind: 'http', baseUrl: '/api' } as const;
  const mail = { id: 1, source_id: 'M-1', direction: 'received', sender: 'a', received_at: '2026-10-20T08:00:00+09:00' }; // subject 생략
  assert.throws(() => toDashboardSource({ as_of: '2026-10-20T09:00:00+09:00', contacts: [], mails: [mail], tasks: [] }, origin), ContractError);
});
