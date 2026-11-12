// 실제 토큰 값(tokens.css)으로 화면에 쓰는 색 조합의 대비를 검사한다(WCAG 2.x 상대 휘도 공식).
// 글자 4.5:1, 상태를 알리는 비텍스트 표시 · 포커스 링 · 입력칸 테두리 3:1. 장식용 구분선(--c-line)은 검사 대상이 아니다.
// 기준 수치는 docs/20_frontend/design_system.md 1절 표(UX-D4 · UX-D10).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/--c-([a-z-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
const c = (name: string): string => {
  const v = tokens[name];
  assert.ok(v, `토큰 없음: --c-${name}`);
  return v;
};

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

test('포인트 색은 LG Heritage Red(#A50034, 로고 SVG 값)다', () => {
  assert.equal(c('point').toUpperCase(), '#A50034');
});

test('UX-D4 60 · 35 · 5 값이 design_system.md 1절과 같다', () => {
  const expected: Record<string, string> = {
    surface: '#FFFFFF', canvas: '#F7F8F9', ink: '#121212', gray: '#6B6B6B', line: '#E5E5E5', fill: '#F0F1F3',
    point: '#A50034', 'point-press': '#610024', sub: '#565656', input: '#8E8E8E',
  };
  for (const [k, v] of Object.entries(expected)) assert.equal(c(k).toUpperCase(), v, `--c-${k}`);
});

// [설명, 앞, 뒤, 최소 대비, design_system에 적힌 값(있으면 소수 둘째 자리까지 같아야 한다)]
const PAIRS: Array<[string, string, string, number, number?]> = [
  // 글자
  ['본문 / 카드', 'ink', 'surface', 4.5, 18.73],
  ['본문 / 페이지 바탕', 'ink', 'canvas', 4.5],
  ['본문 / 채움(hover · 선택 행 · 긴급 띠)', 'ink', 'fill', 4.5],
  ['LG GRAY 보조 글자 / 카드', 'gray', 'surface', 4.5, 5.33],
  ['작은 보조 글자 / 카드', 'sub', 'surface', 4.5, 7.34],
  ['작은 보조 글자 / 페이지 바탕', 'sub', 'canvas', 4.5],
  ['주 버튼 글자 / 포인트', 'on-strong', 'point', 4.5, 7.93],
  ['주 버튼 글자 / 포인트 누름', 'on-strong', 'point-press', 4.5],
  ['건수 배지 · 긴급 라벨 글자 / 검정', 'on-strong', 'due-urgent-bg', 4.5, 18.73],
  ['오늘 라벨 글자 / 파랑 바탕', 'due-today-text', 'due-today-bg', 4.5],
  ['남음 라벨 글자 / 초록 바탕', 'due-later-text', 'due-later-bg', 4.5],
  ['기한 없음 라벨 글자 / 회색 바탕', 'due-none-text', 'due-none-bg', 4.5],
  ['정보 글자 / 정보 바탕(모의 데이터 배지 · 메일 정보 확인 필요)', 'info', 'info-bg', 4.5],
  ['완료 글자 / 완료 바탕', 'done', 'done-bg', 4.5],
  ['위험 글자 / 위험 바탕(음성 듣는 중)', 'danger', 'danger-bg', 4.5],
  // 상태 표시 · 포커스 · 필수 경계(비텍스트)
  ['선택 메뉴 포인트 선 / 채움', 'point', 'fill', 3],
  ['에이전트 원형 버튼 / 페이지 바탕', 'point', 'canvas', 3],
  ['포커스 링 / 페이지 바탕', 'ink', 'canvas', 3],
  ['포커스 링 / 포인트 버튼 둘레(카드)', 'ink', 'surface', 3],
  ['입력칸 · 칩 · 버튼 테두리 / 카드', 'input', 'surface', 3, 3.28],
  ['입력칸 · 칩 · 버튼 테두리 / 페이지 바탕', 'input', 'canvas', 3],
  ['긴급 라벨 바탕 / 카드', 'due-urgent-bg', 'surface', 3],
  ['완료율 호 / 원 바탕(구분선 색)', 'done-bar', 'line', 3],
  ['메일 정보 확인 필요 카드 테두리 / 페이지 바탕', 'info', 'canvas', 3],
];

for (const [label, fg, bg, min, documented] of PAIRS) {
  const ratio = contrast(c(fg), c(bg));
  test(`대비 ${label}: ${ratio.toFixed(2)}:1 (기준 ${min}:1)`, () => {
    assert.ok(ratio >= min, `${label}: ${ratio.toFixed(2)}:1`);
    if (documented !== undefined) assert.equal(ratio.toFixed(2), documented.toFixed(2), `${label}: 문서 값 ${documented}:1과 다름`);
  });
}

test('입력칸 테두리 색(--c-input)은 글자 4.5:1에 못 미쳐 글자에 쓰지 않는다', () => {
  assert.ok(contrast(c('input'), c('surface')) < 4.5);
});
