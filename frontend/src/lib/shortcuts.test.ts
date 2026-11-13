import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isToggleMailboxShortcut, isTypingTarget, shouldIgnoreShortcut } from './shortcuts.ts';

const key = (over: Partial<Parameters<typeof isToggleMailboxShortcut>[0]> = {}) => ({
  key: 'b',
  code: 'KeyB',
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  altKey: false,
  ...over,
});

test('입력칸 · 여러 줄 입력 · 선택 상자 · 편집 영역은 입력 대상이다', () => {
  assert.equal(isTypingTarget({ tagName: 'INPUT', type: 'text' }), true);
  assert.equal(isTypingTarget({ tagName: 'input', type: 'search' }), true);
  assert.equal(isTypingTarget({ tagName: 'INPUT' }), true); // type 없음 = text
  assert.equal(isTypingTarget({ tagName: 'TEXTAREA' }), true);
  assert.equal(isTypingTarget({ tagName: 'SELECT' }), true);
  assert.equal(isTypingTarget({ tagName: 'DIV', isContentEditable: true }), true);
});

test('버튼 · 체크 상자 · 일반 요소 · 없음은 입력 대상이 아니다', () => {
  assert.equal(isTypingTarget({ tagName: 'BUTTON' }), false);
  assert.equal(isTypingTarget({ tagName: 'INPUT', type: 'checkbox' }), false);
  assert.equal(isTypingTarget({ tagName: 'INPUT', type: 'radio' }), false);
  assert.equal(isTypingTarget({ tagName: 'DIV', isContentEditable: false }), false);
  assert.equal(isTypingTarget(null), false);
  assert.equal(isTypingTarget(undefined), false);
});

test('한글 조합 중(isComposing · keyCode 229)이거나 입력 중이면 단축키를 무시한다', () => {
  const body = { tagName: 'BODY' };
  assert.equal(shouldIgnoreShortcut({ target: body }), false);
  assert.equal(shouldIgnoreShortcut({ target: body, isComposing: true }), true);
  assert.equal(shouldIgnoreShortcut({ target: body, keyCode: 229 }), true);
  assert.equal(shouldIgnoreShortcut({ target: { tagName: 'TEXTAREA' } }), true);
  assert.equal(shouldIgnoreShortcut({ target: { tagName: 'BUTTON' }, keyCode: 66 }), false);
});

test('Ctrl+B · ⌘B만 메일함 열고 닫기다', () => {
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true })), true);
  assert.equal(isToggleMailboxShortcut(key({ metaKey: true })), true);
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true, key: 'B' })), true);
  // 한글 자판: key는 'ㅠ'지만 물리 키는 B
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true, key: 'ㅠ' })), true);
});

test('B만 · Shift · Alt가 붙거나 다른 키면 아니다', () => {
  assert.equal(isToggleMailboxShortcut(key()), false);
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true, shiftKey: true })), false);
  assert.equal(isToggleMailboxShortcut(key({ metaKey: true, altKey: true })), false);
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true, metaKey: true })), false);
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true, key: 'k', code: 'KeyK' })), false);
});
