// 화면 테마(설정 > 화면): 라이트 · 다크 · 시스템. 이 기기(브라우저)에만 저장한다 — 서버에 둘 이유가 없고, 첫 화면부터 바로 칠해야 해서.
// 색은 styles/theme.css가 <html data-theme>에 맞춰 바꾼다.
export const THEMES = ['light', 'dark', 'system'] as const;
export type Theme = (typeof THEMES)[number];

const KEY = 'cne.theme';

export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system'; // 저장소를 막은 브라우저 · 테스트
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* 저장하지 못해도 이번 화면에는 적용한다 */
  }
  applyTheme(theme);
}
