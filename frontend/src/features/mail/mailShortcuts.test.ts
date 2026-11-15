import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isInsideDialog, isReloadKey, mailShortcutOf } from './mailShortcuts.ts';

const key = (over: Partial<Parameters<typeof mailShortcutOf>[0]> = {}) => ({
  key: 'r',
  code: 'KeyR',
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  altKey: false,
  target: { tagName: 'BODY' },
  ...over,
});

test('Ctrl+R은 입력칸 안에서도 새로고침 키로 본다(메일 화면이 늘 막는다)', () => {
  assert.equal(isReloadKey(key({ ctrlKey: true })), true);
  assert.equal(isReloadKey(key({ ctrlKey: true, target: { tagName: 'TEXTAREA' } })), true);
  assert.equal(isReloadKey(key({ ctrlKey: true, key: 'ㄱ' })), true); // 한글 자판
  assert.equal(isReloadKey(key()), false); // R 하나는 답장 단축키일 뿐
  assert.equal(isReloadKey(key({ ctrlKey: true, altKey: true })), false);
  // 입력칸 안에서는 답장 단축키로 쓰지 않는다(막기만 한다)
  assert.equal(mailShortcutOf(key({ ctrlKey: true, target: { tagName: 'TEXTAREA' } })), null);
  assert.equal(mailShortcutOf(key({ ctrlKey: true })), 'reply');
});

test('확인 시트 · 도움말 같은 대화상자 안의 키는 대화상자 안으로 본다', () => {
  const inDialog = { tagName: 'BUTTON', closest: (sel: string) => (sel.includes('[role="dialog"]') ? {} : null) };
  const outside = { tagName: 'BUTTON', closest: () => null };
  assert.equal(isInsideDialog(inDialog), true);
  assert.equal(isInsideDialog(outside), false);
  assert.equal(isInsideDialog({ tagName: 'BODY' }), false); // closest가 없는 대상
  assert.equal(isInsideDialog(null), false);
});
