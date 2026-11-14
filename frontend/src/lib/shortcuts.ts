// 단축키 가드 (components.md 6절). 모든 전역 단축키는 이 함수들을 거친다.
// 입력칸 · 여러 줄 입력 · 편집 가능한 영역에 포커스가 있거나 한글을 조합하는 중이면 단축키가 동작하지 않는다.
// DOM 타입에 기대지 않고 필요한 속성만 읽어 node --test에서 평범한 객체로 시험할 수 있다.

/** 글자를 치지 않는 input 종류. 여기에 포커스가 있을 때는 단축키를 막지 않는다(체크 상자에서 Ctrl+B 등). */
const NON_TEXT_INPUT_TYPES = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image']);

interface TargetLike {
  tagName?: unknown;
  type?: unknown;
  isContentEditable?: unknown;
}

/** 글자를 입력하는 요소인가: input(글자 종류) · textarea · select · contenteditable */
export function isTypingTarget(el: unknown): boolean {
  if (typeof el !== 'object' || el === null) return false;
  const t = el as TargetLike;
  if (t.isContentEditable === true) return true;
  const tag = typeof t.tagName === 'string' ? t.tagName.toUpperCase() : '';
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') {
    const type = typeof t.type === 'string' ? t.type.toLowerCase() : 'text';
    return !NON_TEXT_INPUT_TYPES.has(type);
  }
  return false;
}

export interface ShortcutEventLike {
  target: unknown;
  isComposing?: boolean;
  keyCode?: number;
}

/** 단축키를 무시해야 하는가: 입력 중이거나 한글 조합 중(isComposing 또는 keyCode 229) */
export function shouldIgnoreShortcut(e: ShortcutEventLike): boolean {
  return e.isComposing === true || e.keyCode === 229 || isTypingTarget(e.target);
}

export interface KeyEventLike {
  key: string;
  code?: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

/**
 * 메일함 열고 닫기: Ctrl+B 또는 ⌘B(Shift · Alt 없이).
 * 한글 자판에서는 key가 'ㅠ'로 올 수 있어 물리 키(code === 'KeyB')도 본다.
 */
export function isToggleMailboxShortcut(e: KeyEventLike): boolean {
  if (e.shiftKey || e.altKey) return false;
  if (e.ctrlKey === e.metaKey) return false; // 둘 다 없거나 둘 다 누름
  return e.key.toLowerCase() === 'b' || e.code === 'KeyB';
}

/** 화면에 보이는 단축키 표시(aria-keyshortcuts 값과 함께 쓴다) */
export const TOGGLE_MAILBOX_KEYSHORTCUTS = 'Control+B Meta+B';
