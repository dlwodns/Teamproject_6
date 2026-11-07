import assert from 'node:assert/strict';
import { test } from 'node:test';
import { routeFromHash } from '../app/router.ts';
import { HttpError } from './errors.ts';
import { readMockPreview } from './mockClient.ts';
import { selectDashboardApi } from './selectApi.ts';

test('mock 쿼리: 일반 쿼리 · 해시 안 쿼리 모두 읽고, 둘 다 있으면 해시 안 값을 우선', () => {
  assert.equal(readMockPreview('?mock=error', '#/dashboard'), 'error'); // /?mock=error#/dashboard
  assert.equal(readMockPreview('', '#/dashboard?mock=error'), 'error'); // /#/dashboard?mock=error
  assert.equal(readMockPreview('?mock=empty', '#/dashboard?mock=loading'), 'loading');
  assert.equal(readMockPreview('?mock=error', '#/dashboard?mock=wrong'), null); // 해시 값 우선, 잘못된 값은 무시
  assert.equal(readMockPreview('?mock=wrong', ''), null);
  assert.equal(readMockPreview('', ''), null);
});

test('라우터: 해시 뒤 쿼리를 떼고 경로로 맞춘다, 모르는 경로는 대시보드', () => {
  assert.equal(routeFromHash('#/settings?mock=error'), 'settings');
  assert.equal(routeFromHash('#/mail'), 'mail');
  assert.equal(routeFromHash('#/dashboard?mock=error&x=1'), 'dashboard');
  assert.equal(routeFromHash('#/unknown?mock=error'), 'dashboard');
  assert.equal(routeFromHash(''), 'dashboard');
});

test('모의 모드: 해시 안 mock=error로 오류 상태', async () => {
  const api = selectDashboardApi({ VITE_API_MODE: 'mock' }, { search: '', hash: '#/dashboard?mock=error' });
  await assert.rejects(api.getDashboardSource(), HttpError);
});

test('http 모드: 주소의 mock 쿼리가 데이터 소스를 바꾸지 않는다', async () => {
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (url: string) => {
    calls.push(String(url));
    return new Response('{}', { status: 404 });
  }) as typeof fetch;
  try {
    const api = selectDashboardApi({ VITE_API_MODE: 'http' }, { search: '?mock=empty', hash: '#/dashboard?mock=error' });
    await assert.rejects(api.getDashboardSource(), (e: unknown) => e instanceof HttpError && e.status === 404);
    assert.deepEqual(calls, ['/api/dashboard']);
  } finally {
    globalThis.fetch = original;
  }
});
