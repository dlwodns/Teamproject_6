import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dashboardErrorText } from '../pages/dashboard/errorText.ts';
import { AGENT_UNAVAILABLE_TEXT, AgentUnavailableError, ConfigError, ContractError, HttpError, NetworkError, NotAvailableError } from './errors.ts';
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

test('에이전트 명령(BE-11 #50): 요청은 snake_case 메일 id, 응답 AgentResult를 화면 모델로. 실행은 task_ids를 함께 보낸다', async () => {
  const calls: { url: string; body: unknown }[] = [];
  const confirm = {
    kind: 'confirm',
    action: 'T03',
    action_name: '일괄_완료',
    source: 'agent_rule',
    title: '업무 3건을 완료로 바꿀까요?',
    targets: [{ id: 3, mail_id: 3, text: '계약서 수정본 검토 · 승인', status: 'pending', snoozed_until: null }],
    notes: ["'김 팀장'을(를) 김민준 팀장으로"],
    action_id: null,
    preview_id: 'p-1',
    expires_at: '2026-11-06T10:47:00+09:00',
  };
  await withFetch((async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), body: init.body ? JSON.parse(String(init.body)) : undefined });
    if (String(url).endsWith('/agent/command')) return new Response(JSON.stringify(confirm), { status: 200 });
    return new Response(JSON.stringify({ action_id: 9, tasks: [] }), { status: 200 });
  }) as unknown as typeof fetch, async () => {
    const api = createHttpApi('/api');
    const r = await api.runAgentCommand({ text: '김 팀장님 건 다 처리했어', selectedMailIds: [5 as MailId], lastResultIds: [3 as MailId] });
    assert.equal(r.kind, 'confirm');
    assert.equal(r.previewId, 'p-1');
    assert.equal(r.actionName, '일괄_완료');
    assert.equal(r.expiresAtMs, Date.parse('2026-11-06T10:47:00+09:00'));
    assert.deepEqual(r.targets, [{ id: 3, mailId: 3, text: '계약서 수정본 검토 · 승인', status: 'pending', snoozedUntilMs: null }]);
    await api.executeAction('p-1', [3 as TaskId]);
    await api.executeAction('p-1');
  });
  assert.deepEqual(calls[0], { url: '/api/agent/command', body: { text: '김 팀장님 건 다 처리했어', selected_mail_ids: [5], last_result_ids: [3] } });
  assert.deepEqual(calls[1]?.body, { preview_id: 'p-1', task_ids: [3] });
  assert.deepEqual(calls[2]?.body, { preview_id: 'p-1' }); // 기존 호출(체크 목록 없음)은 그대로
});

test('에이전트 명령 503 → AgentUnavailableError(화면 문구 고정), 422 · 500은 그대로 HttpError, 모르는 kind는 ContractError', async () => {
  await withFetch((async () => new Response('{"detail":"지금은 명령을 처리할 수 없어요"}', { status: 503 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').runAgentCommand({ text: '오늘 뭐 해야 돼?' }), (e: unknown) =>
      e instanceof AgentUnavailableError && e.status === 503 && e.message === AGENT_UNAVAILABLE_TEXT,
    );
  });
  for (const status of [422, 500]) {
    await withFetch((async () => new Response('', { status })) as typeof fetch, async () => {
      await assert.rejects(createHttpApi('/api').runAgentCommand({ text: 'x' }), (e: unknown) => e instanceof HttpError && !(e instanceof AgentUnavailableError) && e.status === status);
    });
  }
  await withFetch((async () => new Response(JSON.stringify({ kind: 'weird', title: 'x' }), { status: 200 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').runAgentCommand({ text: 'x' }), ContractError);
  });
});

test('실제 서버는 T01을 unsupported(준비 중)로 답한다 → 그대로 받는다. FE 제안 kind는 그 칸이 있어야 한다', async () => {
  const notReady = { kind: 'unsupported', action: 'T01', action_name: '오늘_요약', source: 'agent_rule', title: "'오늘_요약'은(는) 아직 준비 중이에요", targets: [], notes: [], action_id: null, preview_id: null, expires_at: null };
  await withFetch((async () => new Response(JSON.stringify(notReady), { status: 200 })) as typeof fetch, async () => {
    const r = await createHttpApi('/api').runAgentCommand({ text: '오늘 뭐 해야 돼?' });
    assert.equal(r.kind, 'unsupported');
    assert.equal(r.summary, undefined);
  });
  await withFetch((async () => new Response(JSON.stringify({ ...notReady, kind: 'summary' }), { status: 200 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').runAgentCommand({ text: '오늘 뭐 해야 돼?' }), ContractError);
  });
});

test('답장 보내기(FE 제안): POST /api/mails/{id}/reply, 서버에 없으면(404) NotAvailableError', async () => {
  const draft = { account: 'Outlook', subject: 'RE: 견적', content: '보냅니다', templateKey: null };
  const calls: { url: string; method: string; body: unknown }[] = [];
  await withFetch((async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), method: String(init.method), body: JSON.parse(String(init.body)) });
    return new Response(JSON.stringify({ id: 9, sent_at: '2026-11-06T11:00:00+09:00' }), { status: 200 });
  }) as unknown as typeof fetch, async () => {
    const r = await createHttpApi('/api').sendReply(2 as MailId, draft);
    assert.deepEqual(r, { id: 9, sentAtMs: Date.parse('2026-11-06T11:00:00+09:00') });
  });
  assert.deepEqual(calls[0], {
    url: '/api/mails/2/reply',
    method: 'POST',
    body: { account: 'Outlook', subject: 'RE: 견적', content: '보냅니다', template_key: null },
  });
  await withFetch((async () => new Response('', { status: 404 })) as typeof fetch, async () => {
    await assert.rejects(createHttpApi('/api').sendReply(2 as MailId, draft), NotAvailableError);
  });
});
