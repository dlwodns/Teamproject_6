import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseOffsetTime, toConnectUrl, toDashboardSource, toKstIso, toMailAccounts } from './adapter.ts';
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
  assert.deepEqual(readApiConfig({}), { mode: 'mock', baseUrl: '/api', userId: '1' });
  assert.deepEqual(readApiConfig({ VITE_API_MODE: 'http', VITE_API_BASE: '/api/' }), { mode: 'http', baseUrl: '/api', userId: '1' });
  assert.equal(readApiConfig({ VITE_USER_ID: ' 7 ' }).userId, '7');
  assert.throws(() => readApiConfig({ VITE_USER_ID: 'abc' }));
  assert.throws(() => readApiConfig({ VITE_USER_ID: '0' }));
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

test('선택 칸: BE-3 모양(칸 없음)은 undefined로 남고, 모의 v2 모양은 그대로 읽힌다', () => {
  const origin = { kind: 'http', baseUrl: '/api' } as const;
  const mail = { id: 1, source_id: 'M-1', direction: 'received', sender: 'a', subject: 's', received_at: '2026-10-20T08:00:00+09:00', category: null };
  const task = { id: 1, mail_id: 1, text: 't', due_at: null, due_source: 'none', status: 'pending', seen_at: null };
  const contact = { email: 'a', name: null, position: null, is_superior: false, is_favorite: false };
  const be3 = toDashboardSource({ as_of: '2026-10-20T09:00:00+09:00', contacts: [contact], mails: [mail], tasks: [task] }, origin);
  assert.equal('awaiting' in be3, false);
  assert.equal('lane' in be3.mails[0]!, false);
  assert.equal('dueRaw' in be3.tasks[0]!, false);
  assert.equal('isClient' in be3.contacts[0]!, false);

  const v2 = toDashboardSource(
    {
      as_of: '2026-10-20T09:00:00+09:00',
      contacts: [{ ...contact, org: 'Harborline', is_client: true }],
      mails: [{ ...mail, lane: '확인', reasons: ['외부'], to: ['이준호'], account: 'Outlook', lang: 'en', read_at: null }],
      tasks: [{ ...task, due_raw: 'ASAP', type: '회신', evidence_text: '근거' }],
      awaiting: [{ mail_id: 1001, subject: 'x', to: '박지호', sent_at: '2026-10-18T10:00:00+09:00', days: 2 }],
    },
    origin,
  );
  assert.deepEqual(
    { lane: v2.mails[0]!.lane, reasons: v2.mails[0]!.reasons, to: v2.mails[0]!.to, account: v2.mails[0]!.account, lang: v2.mails[0]!.lang, readAtMs: v2.mails[0]!.readAtMs },
    { lane: '확인', reasons: ['외부'], to: ['이준호'], account: 'Outlook', lang: 'en', readAtMs: null },
  );
  assert.deepEqual([v2.tasks[0]!.dueRaw, v2.tasks[0]!.type, v2.tasks[0]!.evidenceText], ['ASAP', '회신', '근거']);
  assert.deepEqual([v2.contacts[0]!.org, v2.contacts[0]!.isClient], ['Harborline', true]);
  assert.equal(v2.awaiting?.length, 1);
  assert.equal(v2.awaiting?.[0]!.days, 2);
  assert.deepEqual(toDashboardSource({ ...be3Raw(), awaiting: [] }, origin).awaiting, []); // [] = 없음(숨김과 다름)

  function be3Raw() {
    return { as_of: '2026-10-20T09:00:00+09:00', contacts: [], mails: [], tasks: [] };
  }
});

test('선택 칸은 모양이 틀려도 던지지 않는다: 모르는 값 → null, 틀린 목록 · 응답 대기 → 숨김', () => {
  const origin = { kind: 'http', baseUrl: '/api' } as const;
  const src = toDashboardSource(
    {
      as_of: '2026-10-20T09:00:00+09:00',
      contacts: [],
      mails: [{ id: 1, source_id: 'M-1', direction: 'received', sender: 'a', subject: '', received_at: '2026-10-20T08:00:00+09:00', lane: '긴급', reasons: 'x', read_at: '2026-10-20T08:00', lang: 3 }],
      tasks: [{ id: 1, mail_id: 1, text: 't', due_at: null, due_source: 'none', status: 'pending', seen_at: null, type: '보고', due_raw: null }],
      awaiting: [{ mail_id: 1001, subject: 'x', to: '박지호', sent_at: '2026-10-18T10:00', days: 2 }],
    },
    origin,
  );
  const m = src.mails[0]!;
  assert.equal(m.lane, null);
  assert.equal(m.reasons, undefined);
  assert.equal(m.readAtMs, null);
  assert.equal(m.lang, null);
  assert.equal(src.tasks[0]!.type, null);
  assert.equal(src.tasks[0]!.dueRaw, null);
  assert.equal(src.awaiting, undefined); // 한 줄이라도 틀리면 통째로 숨김(일부만 세지 않는다)
});

test('요청 시각은 +09:00 ISO로 보낸다', () => {
  assert.equal(toKstIso(Date.parse('2026-11-06T01:42:00Z')), '2026-11-06T10:42:00+09:00');
  assert.equal(parseOffsetTime(toKstIso(1_762_000_000_000), 'x'), 1_762_000_000_000);
});

test('설정 reply_confirm_skip_until: 없으면 undefined(숨김) · null은 꺼짐 · 시각은 epoch ms, 바꿀 때는 +09:00 ISO로', async () => {
  const { toSettings, settingsPatchToRaw } = await import('./adapter.ts');
  const base = { remind_time: '08:30', awaiting_reply_days: 3, quiet_start: null, quiet_end: null, reduce_motion: false, stt_mode: 'browser' };
  assert.equal('replyConfirmSkipUntilMs' in toSettings(base), false);
  assert.equal(toSettings({ ...base, reply_confirm_skip_until: null }).replyConfirmSkipUntilMs, null);
  const at = '2026-11-07T08:30:00+09:00';
  assert.equal(toSettings({ ...base, reply_confirm_skip_until: at }).replyConfirmSkipUntilMs, Date.parse(at));
  assert.throws(() => toSettings({ ...base, reply_confirm_skip_until: '2026-11-07T08:30' }), ContractError);
  assert.deepEqual(settingsPatchToRaw({ replyConfirmSkipUntilMs: Date.parse(at) }), { reply_confirm_skip_until: at });
  assert.deepEqual(settingsPatchToRaw({ replyConfirmSkipUntilMs: null }), { reply_confirm_skip_until: null });
});

test('답장 보내기: 요청은 snake_case, 응답 {id, sent_at}은 화면 모델로', async () => {
  const { replyBody, toSentReply } = await import('./adapter.ts');
  assert.deepEqual(replyBody({ account: '사내', subject: 'RE: 가', content: '본문', templateKey: 'basic' }), {
    account: '사내',
    subject: 'RE: 가',
    content: '본문',
    template_key: 'basic',
    cc: [],
    bcc: [],
    attachments: [],
  });
  // 전체 답장에서 원 메일 참조를 아직 못 받았으면(null) cc를 싣지 않는다 → 서버가 원 메일의 참조를 쓴다
  assert.equal('cc' in replyBody({ account: null, subject: 's', content: 'c', templateKey: null, cc: null }, 'replyAll'), false);
  // BE-7 단계 2: 첨부 · 예약 시각(+09:00), 예약 응답(202)은 ScheduledSend로
  const at = Date.parse('2099-01-01T09:00:00+09:00');
  const body = replyBody({ account: null, subject: 's', content: 'c', templateKey: null, attachments: [{ name: 'a.txt', contentType: 'text/plain', contentB64: 'aGk=' }], sendAtMs: at });
  assert.deepEqual(body.attachments, [{ name: 'a.txt', content_type: 'text/plain', content_b64: 'aGk=' }]);
  assert.equal(body.send_at, '2099-01-01T09:00:00+09:00');
  const { toSendResult, toSearchHits } = await import('./adapter.ts');
  const r = toSendResult({ scheduled_id: 3, kind: 'new', mail_id: null, subject: 's', to: 'a@b.c', send_at: '2099-01-01T09:00:00+09:00', status: 'pending', error: null, sent_mail_id: null });
  assert.ok('scheduledId' in r && r.scheduledId === 3 && r.sendAtMs === at);
  // 검색 결과의 링크는 https만(javascript: 등은 버린다)
  const hits = toSearchHits([{ mail_id: null, subject: 'x', sender: 'a@b.c', received_at: null, web_link: 'javascript:alert(1)' }]);
  assert.equal(hits[0]!.webLink, null);
  assert.deepEqual(toSentReply({ id: 2001, sent_at: '2026-11-06T10:42:00+09:00' }), { id: 2001, sentAtMs: Date.parse('2026-11-06T10:42:00+09:00') });
  assert.throws(() => toSentReply({ id: '2001', sent_at: '2026-11-06T10:42:00+09:00' }), ContractError);
});

// ── 에이전트 패널(PL-16, 계약 3.1 · 3.2 · 3.3 예시 그대로) ──

test('제안 카드 응답(계약 3.1 예시) → 화면 모델, 업무 변경 본문에 via', async () => {
  const { toSuggestionList, toHistoryList, toAgentMemory, statusChangeBody, memoryPersonPatchBody } = await import('./adapter.ts');
  const t = { task_ids: [1], mail_ids: [1] };
  const list = toSuggestionList({
    suggestions: [{
      key: 'due_soon:task:1', rule: 'due_soon', via: 'suggestion:due_soon', created_at: '2026-11-10T18:00:00+09:00',
      title: '김민준 팀장님 …', detail: [], task_ids: [1], mail_ids: [1],
      buttons: [{ label: '회신 작성', kind: 'action', action: 'T07', primary: true, params: { tone: 'polite' }, target: t }],
      menu: [{ label: '이 제안 숨기기', kind: 'hide', action: 'hide', primary: false, params: {}, target: { task_ids: [], mail_ids: [] } }],
    }],
    more: 0, total: 1, generated_at: '2026-11-11T14:00:00+09:00',
  });
  assert.equal(list.suggestions[0]!.buttons[0]!.target.mailIds[0], 1);
  assert.equal(list.suggestions[0]!.menu[0]!.kind, 'hide');
  assert.deepEqual(statusChangeBody({ status: 'done', via: 'suggestion:due_soon' }), { status: 'done', via: 'suggestion:due_soon' });
  assert.deepEqual(statusChangeBody({ status: 'done' }), { status: 'done' });
  // 기록: 확인 기다림 줄에는 redo_action_id가 없을 수 있다(계약 예시)
  const h = toHistoryList({ days: 7, items: [{ id: 'preview:9', state: 'waiting', action: 'bulk_status', action_id: null, preview_id: '9', text: 'x', via: 'ui', via_label: '화면 버튼', auto: false, at: '2026-11-11T14:00:00+09:00', expires_at: '2026-11-11T14:05:00+09:00', can_undo: false }] });
  assert.equal(h.items[0]!.redoActionId, null);
  // 기억: 계약 예시에는 facts가 없다 → 빈 목록
  const m = toAgentMemory({
    learn_from_mail: true,
    me: { name: '문규남', department: 'AX팀', position: '책임', mailing_lists: [{ address: 'ax-team@cne.com', kind: 'team' }], uses: 'u', used_by: ['메일 분류'], origin: { at: null, text: '처음 설정에서 넣었어요' } },
    people: [{ contact_id: 5, name: '박서연', email: 'park@cne.com', position: '상무', is_superior: true, is_favorite: false, uses: 'u', used_by: ['제안 카드'], origin: { at: '2026-11-11T14:05:00+09:00', text: '11/11 화면에서 바꿨어요' } }],
  });
  assert.deepEqual(m.people[0]!.facts, []);
  assert.deepEqual(memoryPersonPatchBody({ isSuperior: false, facts: { org: null } }), { is_superior: false, facts: { org: null } });
});

test('오늘 요약(T01) 조율 칸: text · refreshing은 있으면 옮기고, 없거나 형식이 다르면 없는 것으로 본다', async () => {
  const { toAgentResult } = await import('./adapter.ts');
  const base = { kind: 'summary', action: 'T01', action_name: '오늘_요약', source: 'agent_rule', title: '긴급 1건이에요', targets: [], notes: [], action_id: null, preview_id: null, expires_at: null };
  const item = { task_id: 1, mail_id: 2, text: '견적서 회신', due_at: null, due_raw: 'ASAP' };
  const old = toAgentResult({ ...base, summary: { items: [item], hint: '그 밖에 미처리 3건' } });
  assert.deepEqual(Object.keys(old.summary!).sort(), ['hint', 'items']); // 지금 서버 응답은 그대로
  const next = toAgentResult({ ...base, summary: { items: [item], hint: null, text: '오늘은 견적서 회신이 가장 급해요.', refreshing: true } });
  assert.equal(next.summary!.text, '오늘은 견적서 회신이 가장 급해요.');
  assert.equal(next.summary!.refreshing, true);
  const nulls = toAgentResult({ ...base, summary: { items: [], hint: null, text: null, refreshing: false } });
  assert.equal(nulls.summary!.text, null);
  assert.equal(nulls.summary!.refreshing, false);
  const odd = toAgentResult({ ...base, summary: { items: [], hint: null, text: 3, refreshing: 'yes' } });
  assert.equal(odd.summary!.text, undefined);
  assert.equal(odd.summary!.refreshing, undefined);
  assert.equal(toAgentResult({ ...base, summary: { items: [], hint: null, text: '  ' } }).summary!.text, null);
  assert.equal(old.summary!.items[0]!.section, null); // section 없는 응답은 null
  const done = toAgentResult({ ...base, summary: { items: [{ ...item, section: 'done_today' }], hint: null } });
  assert.equal(done.summary!.items[0]!.section, 'done_today');
});

test('답장 다듬기 응답(#95 PolishView): text · changed · source · fallback, 모르는 source는 계약 오류', async () => {
  const { toPolishedReply } = await import('./adapter.ts');
  const raw = { text: '내일까지 송부드리겠습니다.', style: 'polite', changed: true, source: 'exaone', fallback: null };
  assert.deepEqual(toPolishedReply(raw), { text: '내일까지 송부드리겠습니다.', changed: true, source: 'exaone', fallback: null });
  assert.equal(toPolishedReply({ ...raw, changed: false, source: 'none', fallback: '모델 실패' }).fallback, '모델 실패');
  assert.throws(() => toPolishedReply({ ...raw, source: 'template' }), ContractError);
});

test('사람 조회(T17): person 칸을 옮기고, 메일 내용 분석이 꺼져 있으면 facts가 비어 온다', async () => {
  const { toAgentResult } = await import('./adapter.ts');
  const base = { kind: 'person', action: 'T17', action_name: '사람_조회', source: 'agent_model', title: '김민준 팀장님이 보낸 메일 3건입니다', targets: [], notes: [], action_id: null, preview_id: null, expires_at: null };
  const person = {
    contact_id: 1, name: '김민준', email: 'lead@example.com', position: '팀장', is_superior: true, is_favorite: false,
    facts: [{ kind: 'org', label: '소속', value: '한빛은행 IT기획부', evidence: '저는 한빛은행 IT기획부입니다.', mail_id: 1 }],
    learn_off: false, mails: [{ mail_id: 3, subject: '견적 회신', received_at: '2026-11-02T12:00:00+09:00' }], mail_total: 3,
  };
  const r = toAgentResult({ ...base, person });
  assert.equal(r.person!.isSuperior, true);
  assert.deepEqual(r.person!.facts, [{ label: '소속', value: '한빛은행 IT기획부', evidence: '저는 한빛은행 IT기획부입니다.', mailId: 1 }]);
  assert.equal(r.person!.mails[0]!.mailId, 3);
  const off = toAgentResult({ ...base, person: { ...person, facts: [], learn_off: true } });
  assert.equal(off.person!.learnOff, true);
  assert.deepEqual(off.person!.facts, []);
});

test('BE-7 메일 계정: 목록을 읽고, 연결 주소는 Microsoft 로그인만 받는다', () => {
  const list = toMailAccounts({ outlook_enabled: true, items: [{ id: 2, provider: 'outlook_graph', email: 'me@example.com', connected: false, last_synced_at: '2026-11-19T10:00:00+09:00' }] });
  const [a] = list.items;
  assert.equal(list.outlookEnabled, true);
  assert.deepEqual(a, { id: 2, provider: 'outlook_graph', email: 'me@example.com', aliases: [], connected: false, lastSyncedMs: Date.parse('2026-11-19T01:00:00Z') });
  assert.throws(() => toMailAccounts({ outlook_enabled: true, items: [{ id: 2, provider: 'x', email: 'e', connected: 'yes', last_synced_at: null }] }), ContractError);
  assert.throws(() => toMailAccounts([]), ContractError); // 예전 모양(배열)은 받지 않는다
  assert.equal(toConnectUrl({ url: 'https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?x=1' }).startsWith('https://login'), true);
  assert.throws(() => toConnectUrl({ url: 'https://evil.example.com/login' }), ContractError); // 서버 응답이 엉뚱한 곳으로 보내지 못하게
});

test('메일 찾기 · 요약(T19 · T20, 11-18): mails · lines를 옮기고, 없으면(null) 빈 목록, 모르는 direction은 계약 오류', async () => {
  const { toAgentResult } = await import('./adapter.ts');
  const base = { kind: 'query', action: 'T19', action_name: '메일_찾기', source: 'agent_model', title: '받은 메일 1통입니다', targets: [], notes: [], action_id: null, preview_id: null, expires_at: null };
  const mail = { mail_id: 7, subject: '[누리물류] 킥오프 장소 변경', who: '백승현 과장', direction: 'received', at: '2026-11-16T09:00:00+09:00' };
  const r = toAgentResult({ ...base, mails: [mail], lines: ['요청: 참석자 회신'] });
  assert.deepEqual(r.mails!.map((m) => [m.mailId, m.who, m.direction]), [[7, '백승현 과장', 'received']]);
  assert.deepEqual(r.lines, ['요청: 참석자 회신']);
  assert.deepEqual(toAgentResult({ ...base, mails: null }).mails, []);
  assert.throws(() => toAgentResult({ ...base, mails: [{ ...mail, direction: 'draft' }] }), ContractError);
});
