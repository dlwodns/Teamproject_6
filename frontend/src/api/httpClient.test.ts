import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dashboardErrorText } from '../pages/dashboard/errorText.ts';
import { ConfigError, ContractError, HttpError, NetworkError, NotAvailableError } from './errors.ts';
import type { MailId, TaskId } from './types.ts';
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
    await assert.rejects(createHttpApi('/api').getDashboard(), NetworkError);
  });
});

test('요청 취소는 NetworkError로 바꾸지 않는다', async () => {
  const controller = new AbortController();
  await withFetch((async () => {
    controller.abort();
    throw new DOMException('aborted', 'AbortError');
  }) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboard(controller.signal), (e: unknown) => !(e instanceof NetworkError));
  });
});

test('fetch 밖의 프로그래밍 오류(TypeError)는 네트워크 실패로 위장하지 않는다', async () => {
  const broken = {
    get ok(): boolean {
      throw new TypeError('코드 버그 흉내'); // fetch가 끝난 뒤 응답을 읽다가 나는 TypeError
    },
  };
  await withFetch((async () => broken as unknown as Response) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboard(), (e: unknown) => e instanceof TypeError && !(e instanceof NetworkError));
  });
});

test('HTTP 오류 응답 → HttpError(상태 코드 유지)', async () => {
  await withFetch((async () => new Response('', { status: 503 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getDashboard(), (e: unknown) => e instanceof HttpError && e.status === 503);
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

test('BE-4 요청 · 응답을 backend 스키마 그대로 바꾼다(+09:00 ISO 보내고, epoch ms로 받는다)', async () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  await withFetch((async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), method: String(init.method), body: init.body ? JSON.parse(String(init.body)) : undefined });
    const state = { id: 3, status: 'snoozed', done_at: null, snoozed_until: '2026-11-07T09:00:00+09:00', status_changed_at: '2026-11-06T10:42:00+09:00' };
    return new Response(JSON.stringify({ action_id: 7, undone_action_id: 6, tasks: [state] }), { status: 200 });
  }) as unknown as typeof fetch, async () => {
    const api = createHttpApi('/api');
    const until = Date.parse('2026-11-07T09:00:00+09:00');
    const r = await api.patchTaskStatus(3 as TaskId, { status: 'snoozed', snoozedUntilMs: until, source: 'button' });
    assert.deepEqual(r, { actionId: 7, tasks: [{ id: 3, status: 'snoozed', doneAtMs: null, snoozedUntilMs: until, statusChangedAtMs: Date.parse('2026-11-06T10:42:00+09:00') }] });
    const u = await api.undoAction(6);
    assert.equal(u.undoneActionId, 6);
  });
  assert.deepEqual(calls[0], { url: '/api/tasks/3', method: 'PATCH', body: { status: 'snoozed', snoozed_until: '2026-11-07T09:00:00+09:00' } });
  assert.deepEqual(calls[1], { url: '/api/actions/6/undo', method: 'POST', body: undefined });
});

test('FE 제안 요청의 404 · 405 · 501은 NotAvailableError, 있는 요청의 404는 HttpError(모의로 바꾸지 않음)', async () => {
  for (const status of [404, 405, 501]) {
    await withFetch((async () => new Response('{"detail":"Not Found"}', { status })) as typeof fetch, async () => {
      const api = createHttpApi('/api');
      await assert.rejects(api.getAwaiting(), NotAvailableError);
      await assert.rejects(api.getNotifications(), NotAvailableError);
      await assert.rejects(api.getMail(1 as MailId), NotAvailableError);
      await assert.rejects(api.summarizeMail(1 as MailId), NotAvailableError);
    });
  }
  await withFetch((async () => new Response('', { status: 404 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').patchTaskStatus(1 as TaskId, { status: 'done' }), (e: unknown) => e instanceof HttpError && e.status === 404);
  });
  await withFetch((async () => new Response('', { status: 500 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').getSettings(), (e: unknown) => e instanceof HttpError && e.status === 500);
  });
});
