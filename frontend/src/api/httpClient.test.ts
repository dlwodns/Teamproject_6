import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dashboardErrorText } from '../pages/dashboard/errorText.ts';
import { ConfigError, ContractError, HttpError, NetworkError } from './errors.ts';
import { createHttpApi } from './httpClient.ts';

async function withFetch(fake: typeof fetch, run: () => Promise<void>) {
  const original = globalThis.fetch;
  globalThis.fetch = fake;
  try {
    await run();
  } finally {
    globalThis.fetch = original;
  }
}

test('네트워크 실패(fetch가 TypeError로 거절) → NetworkError', async () => {
  await withFetch((async () => {
    throw new TypeError('Failed to fetch');
  }) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboardSource(), NetworkError);
  });
});

test('요청 취소는 NetworkError로 바꾸지 않는다', async () => {
  const controller = new AbortController();
  await withFetch((async () => {
    controller.abort();
    throw new DOMException('aborted', 'AbortError');
  }) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboardSource(controller.signal), (e: unknown) => !(e instanceof NetworkError));
  });
});

test('fetch 밖의 프로그래밍 오류(TypeError)는 네트워크 실패로 위장하지 않는다', async () => {
  const broken = {
    get ok(): boolean {
      throw new TypeError('코드 버그 흉내'); // fetch가 끝난 뒤 응답을 읽다가 나는 TypeError
    },
  };
  await withFetch((async () => broken as unknown as Response) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboardSource(), (e: unknown) => e instanceof TypeError && !(e instanceof NetworkError));
  });
});

test('HTTP 오류 응답 → HttpError(상태 코드 유지)', async () => {
  await withFetch((async () => new Response('', { status: 503 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboardSource(), (e: unknown) => e instanceof HttpError && e.status === 503);
  });
});

test('화면 안내: 네트워크 실패만 연결 문구, 원문 · 내부 진단은 내지 않음', () => {
  assert.equal(dashboardErrorText(new NetworkError('x')), '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
  const programming = dashboardErrorText(new TypeError("Cannot read properties of undefined (reading 'x')"));
  assert.notEqual(programming, dashboardErrorText(new NetworkError('x')));
  assert.doesNotMatch(programming, /Cannot read|undefined/);
  assert.doesNotMatch(dashboardErrorText(new ContractError('mails[3].received_at: 시간대가 붙은 ISO 시각이 아니다')), /mails|received_at/);
  assert.doesNotMatch(dashboardErrorText(new ConfigError('VITE_API_MODE는 mock 또는 http')), /VITE_/);
  assert.doesNotMatch(dashboardErrorText(new HttpError(404, '/api/dashboard 응답 404')), /\/api/);
  assert.match(dashboardErrorText(new HttpError(503, 'x')), /503/);
});
