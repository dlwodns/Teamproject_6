import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dashboardErrorText } from '../pages/dashboard/errorText.ts';
import { ConfigError, ContractError, HttpError, NetworkError } from './errors.ts';
import { createHttpApi, REQUEST_TIMEOUT_MS } from './httpClient.ts';

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

/** 신호가 끊기면 신호의 reason으로 거절하는 약속(실제 fetch · res.json()이 끊길 때처럼). */
function rejectOnAbort(signal: AbortSignal | null | undefined): Promise<never> {
  return new Promise((_, reject) => {
    signal?.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
}

test('제한 시간 초과(응답이 오지 않음) → NetworkError, 화면 문구는 연결 실패', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  await withFetch(((_url: unknown, init?: RequestInit) => rejectOnAbort(init?.signal)) as typeof fetch, async () => {
    const pending = createHttpApi('/api').getDashboardSource(new AbortController().signal);
    t.mock.timers.tick(REQUEST_TIMEOUT_MS - 1);
    let settled = false;
    void pending.then(
      () => (settled = true),
      () => (settled = true),
    );
    await Promise.resolve();
    assert.equal(settled, false, '제한 시간 전에는 끝나지 않는다');
    t.mock.timers.tick(1);
    await assert.rejects(pending, (e: unknown) => {
      assert.ok(e instanceof NetworkError);
      assert.equal(dashboardErrorText(e), '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
      return true;
    });
  });
});

test('본문(res.json()) 읽기 도중 제한 시간 초과 → NetworkError(계약 오류로 위장하지 않는다)', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let jsonStarted!: () => void;
  const reading = new Promise<void>((resolve) => (jsonStarted = resolve));
  await withFetch((async (_url: unknown, init?: RequestInit) =>
    ({
      ok: true,
      status: 200,
      json: () => {
        jsonStarted();
        return rejectOnAbort(init?.signal);
      },
    }) as unknown as Response) as typeof fetch, async () => {
    const pending = createHttpApi('/api').getDashboardSource();
    await reading; // 헤더는 받았고 본문을 읽는 중
    t.mock.timers.tick(REQUEST_TIMEOUT_MS);
    await assert.rejects(pending, (e: unknown) => e instanceof NetworkError && !(e instanceof ContractError));
  });
});

test('본문 읽기 도중 화면이 취소하면 그대로 올린다(NetworkError · 계약 오류 아님)', async () => {
  const controller = new AbortController();
  let jsonStarted!: () => void;
  const reading = new Promise<void>((resolve) => (jsonStarted = resolve));
  await withFetch((async (_url: unknown, init?: RequestInit) =>
    ({
      ok: true,
      status: 200,
      json: () => {
        jsonStarted();
        return rejectOnAbort(init?.signal);
      },
    }) as unknown as Response) as typeof fetch, async () => {
    const pending = createHttpApi('/api').getDashboardSource(controller.signal);
    await reading;
    controller.abort();
    await assert.rejects(pending, (e: unknown) => !(e instanceof NetworkError) && !(e instanceof ContractError));
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
