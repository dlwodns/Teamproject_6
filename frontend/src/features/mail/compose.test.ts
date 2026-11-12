// 답장 쓰기 판단 시험(wireframe 13-5 · V-13 · V-26).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toSettings } from '../../api/adapter.ts';
import { hasDraft, recipientName, renderReply, replySubject, replyText } from './compose.ts';

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
