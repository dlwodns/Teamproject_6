// 에이전트 입력칸 키 판단 (components.md 6절). Enter = 보내기, Shift+Enter = 줄바꿈,
// 한글 조합 중 Enter(isComposing 또는 keyCode 229)는 글자를 확정하는 Enter라 보내지 않는다.

export interface EnterKeyLike {
  key: string;
  shiftKey: boolean;
  altKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  isComposing?: boolean;
  keyCode?: number;
}

export function isSendKey(e: EnterKeyLike): boolean {
  if (e.key !== 'Enter') return false;
  if (e.isComposing || e.keyCode === 229) return false;
  return !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey;
}
