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

test('Ctrl+J · ⌘J는 에이전트 패널을 여닫는다. 한글 조합 중 · 입력 중에는 무시하고, Ctrl+B와 섞이지 않는다', async () => {
  const { agentShortcutAction, isToggleAgentShortcut } = await import('./shortcuts.ts');
  const j = (over: Record<string, unknown> = {}) => ({ ...key({ key: 'j', code: 'KeyJ', ctrlKey: true }), target: null, ...over });
  assert.equal(isToggleAgentShortcut(j()), true);
  assert.equal(isToggleAgentShortcut(j({ ctrlKey: false, metaKey: true })), true); // ⌘J
  assert.equal(isToggleAgentShortcut(j({ key: 'ㅓ' })), true); // 한글 자판: 물리 키로 본다
  assert.equal(isToggleAgentShortcut(j({ shiftKey: true })), false);
  assert.equal(isToggleAgentShortcut(j({ ctrlKey: false })), false);
  assert.equal(isToggleAgentShortcut(j({ ctrlKey: true, metaKey: true })), false);

  assert.equal(agentShortcutAction(j(), 'other'), 'open-agent');
  assert.equal(agentShortcutAction(j(), 'agent-page'), 'focus-input');
  assert.equal(agentShortcutAction(j({ isComposing: true }), 'other'), null);
  assert.equal(agentShortcutAction(j({ keyCode: 229 }), 'other'), null);
  assert.equal(agentShortcutAction(j({ target: { tagName: 'TEXTAREA' } }), 'other'), null);

  // Ctrl+B는 그대로 메일함, Ctrl+J는 메일함이 아니다
  assert.equal(isToggleMailboxShortcut(key({ ctrlKey: true })), true);
  assert.equal(isToggleAgentShortcut(key({ ctrlKey: true })), false);
  assert.equal(isToggleMailboxShortcut(j()), false);
});
