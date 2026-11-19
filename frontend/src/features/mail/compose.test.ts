// 답장 쓰기 판단 시험(wireframe 13-5 · V-13 · V-26).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toSettings } from '../../api/adapter.ts';
import { canApplyPolish, forwardSubject, hasDraft, parseAddresses, recipientName, renderReply, replySubject, replyText, sendFailure } from './compose.ts';

// 순수 판단만 본다. Compose.tsx가 응답 시점의 textarea 값을 넘기는 연결은 DOM 도구가 없어 검증하지 못한다.
test('다듬기 응답: 요청 뒤 글이 바뀌었으면 덮어쓰지 않는다', () => {
  assert.equal(canApplyPolish('금요일까지 보낼게요', '금요일까지 보낼게요'), true);
  assert.equal(canApplyPolish('금요일까지 보낼게요', '금요일까지 보낼게요. 표도 같이'), false);
});

const settings = toSettings(JSON.parse(readFileSync(new URL('../../api/mock/settings.v1.json', import.meta.url), 'utf8')));
const tpl = (key: string) => settings.templates!.find((t) => t.key === key)!;
const vars = { recipient: '김민준 팀장', sender: '이준호', subject: '계약서 수정본 검토 및 협력사 평가표 요청' };
const content = '수정본 검토했고 오늘 중으로 승인 올리겠습니다.';

test('제목: RE: 원메일제목, 이미 RE:면 그대로', () => {
  assert.equal(replySubject('계약서 수정본 검토'), 'RE: 계약서 수정본 검토');
  assert.equal(replySubject('RE: 서버 증설 견적 관련'), 'RE: 서버 증설 견적 관련');
  assert.equal(replySubject('re:견적'), 're:견적');
});

test('받는 사람 표시: 이름 + 직책, 이름이 없으면 주소', () => {
  const c = { email: 'a@x', name: '김민준', position: '팀장', isSuperior: false, isFavorite: true };
  assert.equal(recipientName(c, c.email), '김민준 팀장');
  assert.equal(recipientName({ ...c, position: '' }, c.email), '김민준');
  assert.equal(recipientName(undefined, 'a@x'), 'a@x');
});

test('V-13: 템플릿을 기본 회신 → 자료 송부로 바꾸면 쓴 내용은 그대로, 인사 · 맺음만 바뀐다', () => {
  const basic = renderReply(tpl('basic'), vars, content);
  const material = renderReply(tpl('material'), vars, content);
  assert.equal(basic.content, content);
  assert.equal(material.content, content);
  assert.equal(basic.before, '김민준 팀장님, 안녕하세요. 이준호입니다.\n\n');
  assert.equal(material.before, '김민준 팀장님, 안녕하세요. 이준호입니다.\n요청하신 자료를 첨부해 보내드립니다.\n\n');
  assert.equal(basic.after, '\n\n감사합니다.\n이준호 드림');
  assert.equal(material.after, '\n\n확인 부탁드립니다.\n이준호 드림');
  assert.equal(replyText(material), `${material.before}${content}${material.after}`);
});

test('자리표시: {원메일제목}도 채우고, 내 이름을 모르면 {발신자명}을 지어내지 않는다', () => {
  const t = { ...tpl('basic'), pattern: '{원메일제목} 건 회신드립니다.\n{내용}\n{발신자명}' };
  const parts = renderReply(t, { ...vars, sender: null }, '네');
  assert.equal(parts.before, '계약서 수정본 검토 및 협력사 평가표 요청 건 회신드립니다.\n');
  assert.equal(parts.after, '\n{발신자명}');
});

test('{내용}이 없는 템플릿 · 템플릿 없음', () => {
  const t = { ...tpl('basic'), pattern: '{수신자명}님,' };
  assert.deepEqual(renderReply(t, vars, '네'), { before: '김민준 팀장님,\n\n', content: '네', after: '' });
  assert.deepEqual(renderReply(null, vars, '네'), { before: '', content: '네', after: '' });
});

test('쓰던 답장 판단: 공백만이면 없음', () => {
  assert.equal(hasDraft('  \n'), false);
  assert.equal(hasDraft('네'), true);
});

test('자유 글 틀에 {내용}을 두 번 써도 쓴 글 자리는 첫 번째 하나다', () => {
  const t = { key: 'x', name: 'x', pattern: 'A {내용} B {내용} C' };
  const parts = renderReply(t, { recipient: '김', sender: '이', subject: '' }, '본문');
  assert.equal(replyText(parts), 'A 본문 B  C');
});

test('FE-18 주소 칸: 쉼표 · 세미콜론 · 공백으로 나누고, 형식이 아닌 것은 bad', () => {
  assert.deepEqual(parseAddresses(' a@x.com, b@y.kr;  A@x.com\nc@z.com '), { ok: ['a@x.com', 'b@y.kr', 'c@z.com'], bad: [] });
  assert.deepEqual(parseAddresses('kim, @x.com, a@@b, d@e.com'), { ok: ['d@e.com'], bad: ['kim', '@x.com', 'a@@b'] });
  assert.deepEqual(parseAddresses('   '), { ok: [], bad: [] });
});

test('FE-18 전달 제목: FW: 하나만', () => {
  assert.equal(forwardSubject('견적'), 'FW: 견적');
  assert.equal(forwardSubject('Fwd: 견적'), 'Fwd: 견적');
});

test('FE-18 보내기 실패: 504 · 응답 없음은 보냈는지 모름 → 다시 시도 버튼 없음(두 번 보내지 않게)', () => {
  assert.equal(sendFailure(504).retry, false);
  assert.match(sendFailure(504).description ?? '', /보낸 편지함/);
  assert.equal(sendFailure('network').retry, false);
  assert.match(sendFailure(409).description ?? '', /다시 연결/);
  assert.equal(sendFailure(500).retry, true);
});
