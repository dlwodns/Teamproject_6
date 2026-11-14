// 메일 화면 단축키(FE-5d, Outlook 호환 · components.md 6절). 입력 중 · 한글 조합 중 가드는 lib/shortcuts.ts를 거친다.
// 한글 자판에서는 key가 'ㄱ'처럼 오므로 물리 키(code)도 본다. 맥에서도 Outlook처럼 Ctrl을 쓴다(⌘Q · ⌘R은 브라우저가 먼저 가져간다).
import { shouldIgnoreShortcut, type KeyEventLike, type ShortcutEventLike } from '../../lib/shortcuts.ts';

export type MailShortcut = 'reply' | 'read' | 'unread' | 'pin' | 'exclude' | 'next' | 'prev' | 'help' | 'clear';

const letter = (e: KeyEventLike, ch: string) => e.key.toLowerCase() === ch || e.code === `Key${ch.toUpperCase()}`;

/**
 * 새로고침 키(Ctrl+R)인가. 메일 화면에서는 입력칸 안이든 밖이든 항상 막는다(#59 리뷰).
 * 답장을 쓰는 중에 눌러도 쓰던 답장이 사라지지 않게 — 단축키로는 '답장'이지만, 입력 중이면 아무 일도 하지 않고 막기만 한다.
 */
export function isReloadKey(e: KeyEventLike): boolean {
  return e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey && letter(e, 'r');
}

interface ClosestLike {
  closest?: (selector: string) => unknown;
}

/** 대화상자(확인 시트 · 도움말 등) 안에서 누른 키인가. 그 안의 키는 뒤 메일 화면에 보내지 않는다(#59 리뷰) */
export function isInsideDialog(target: unknown): boolean {
  if (typeof target !== 'object' || target === null) return false;
  const closest = (target as ClosestLike).closest;
  if (typeof closest !== 'function') return false;
  return closest.call(target, '[role="dialog"], [role="alertdialog"]') != null;
}

/** 키 하나 → 메일 동작. 입력 중이면 null */
export function mailShortcutOf(e: KeyEventLike & ShortcutEventLike): MailShortcut | null {
  if (shouldIgnoreShortcut(e) || e.altKey || e.metaKey) return null;
  if (e.ctrlKey) {
    if (e.shiftKey) return null; // Ctrl+Shift+R(전체 답장) 등은 아직 없다
    if (letter(e, 'r')) return 'reply';
    if (letter(e, 'q')) return 'read';
    if (letter(e, 'u')) return 'unread';
    if (e.key === '.' || e.code === 'Period') return 'next';
    if (e.key === ',' || e.code === 'Comma') return 'prev';
    return null;
  }
  if (e.key === '?') return 'help';
  if (e.shiftKey) return null;
  if (letter(e, 'r')) return 'reply';
  if (e.key === 'Insert') return 'pin';
  if (e.key === 'Delete') return 'exclude';
  if (e.key === 'Escape') return 'clear';
  return null;
}

export interface ShortcutHelpRow {
  keys: string[];
  label: string;
}

/** 단축키 도움말(?)에 보이는 줄. 화면 동작과 같은 차례 */
export const MAIL_SHORTCUT_HELP: ShortcutHelpRow[] = [
  { keys: ['↑', '↓'], label: '메일 줄 옮기기' },
  { keys: ['Enter'], label: '메일 열기' },
  { keys: ['Ctrl .', 'Ctrl ,'], label: '다음 · 이전 메일' },
  { keys: ['R', 'Ctrl R'], label: '답장' },
  { keys: ['Ctrl Q'], label: '읽음으로 표시' },
  { keys: ['Ctrl U'], label: '안 읽음으로 표시' },
  { keys: ['Insert'], label: '고정 · 고정 해제 (Outlook의 플래그 키)' },
  { keys: ['Delete'], label: '업무 제외 (여러 통은 확인 뒤 · 되돌리기 가능)' },
  { keys: ['Shift 클릭', 'Ctrl 클릭'], label: '여러 통 고르기' },
  { keys: ['Esc'], label: '고른 것 해제' },
  { keys: ['Ctrl B'], label: '메일함 열고 닫기' },
  { keys: ['?'], label: '이 도움말' },
];
