import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { MailId } from '../../api/types.ts';
import { mailPath, parseMailId, readComposeParams, readFrom } from './routes.ts';

test('메일 주소: 메일함 · 메일 · 답장 · 초안', () => {
  assert.equal(mailPath('inbox'), '/mail/inbox');
  assert.equal(mailPath('inbox', 3 as MailId), '/mail/inbox/3');
  assert.equal(mailPath('cat-회신', 3), `/mail/${encodeURIComponent('cat-회신')}/3`);
  assert.equal(mailPath('inbox', 3, { reply: true }), '/mail/inbox/3?reply=1');
  const withDraft = mailPath('inbox', 3, { reply: true, draft: '네, 확인했습니다 & 곧' });
  const q = new URLSearchParams(withDraft.split('?')[1]);
  assert.deepEqual(readComposeParams(q), { reply: true, draft: '네, 확인했습니다 & 곧' });
  assert.equal(mailPath('inbox', null, { reply: true }), '/mail/inbox');
});

test('주소 읽기: 메일 번호 · 답장 · 넘어온 화면', () => {
  assert.equal(parseMailId('12'), 12);
  assert.equal(parseMailId('x'), null);
  assert.equal(parseMailId(undefined), null);
  assert.deepEqual(readComposeParams(new URLSearchParams('')), { reply: false, draft: '' });
  assert.deepEqual(readFrom({ from: 'dashboard' }), { key: 'dashboard', label: '대시보드' });
  assert.equal(readFrom({ from: 'x' }), null);
  assert.equal(readFrom(null), null);
});
