import assert from 'node:assert/strict';
import test from 'node:test';
import { startSession } from './session.ts';

test('세션 시작은 POST {base}/session을 같은 출처 쿠키와 함께 한 번 부른다(INF-11 11-25)', async () => {
  const calls: Array<[string, RequestInit | undefined]> = [];
  await startSession('/api', (async (url: string, init?: RequestInit) => {
    calls.push([url, init]);
    return new Response('{}');
  }) as typeof fetch);
  assert.equal(calls.length, 1);
  const [url, init] = calls[0]!;
  assert.equal(url, '/api/session');
  assert.equal(init?.method, 'POST');
  assert.equal(init?.credentials, 'same-origin');
});

test('연결이 안 돼도 화면을 띄울 수 있게 오류를 올리지 않는다', async () => {
  await startSession('/api', (async () => {
    throw new TypeError('fetch failed');
  }) as typeof fetch);
});
