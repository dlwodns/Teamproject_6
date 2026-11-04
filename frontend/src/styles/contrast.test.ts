// 실제 토큰 값(tokens.css)으로 화면에 쓰는 색 조합의 대비를 검사한다(WCAG 2.x 상대 휘도 공식).
// 글씨 4.5:1(큰 글씨 3:1), 상태를 알리는 비텍스트 표시 · 포커스 링 3:1. 장식용 경계는 검사 대상이 아니다.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/--(color-[a-z-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
const c = (name: string): string => {
  const v = tokens[`color-${name}`];
  assert.ok(v, `토큰 없음: --color-${name}`);
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

test('가이드 5색이 그대로다', () => {
  assert.deepEqual(
    ['primary', 'surface', 'text', 'background', 'accent'].map((n) => c(n).toUpperCase()),
    ['#FF6000', '#F9F9F9', '#1C1C1C', '#F2EDE6', '#FFE066'],
  );
});

// [설명, 앞, 뒤, 최소 대비]
const PAIRS: Array<[string, string, string, number]> = [
  // 글씨
  ['본문 · 제목 / 페이지 배경', 'text', 'background', 4.5],
  ['본문 · 제목 / 카드', 'text', 'surface', 4.5],
  ['선택 메뉴 · 열린 버튼 글씨 / 오렌지', 'text', 'primary', 4.5],
  ['기한 지남 칩 · 경고 띠 글씨 / 노랑', 'text', 'accent', 4.5],
  ['보조 글씨 / 페이지 배경', 'text-sub', 'background', 4.5],
  ['보조 글씨 / 카드', 'text-sub', 'surface', 4.5],
  ['보조 글씨 / 노랑', 'text-sub', 'accent', 4.5],
  ['건수 배지 글씨 / 검정 배지', 'on-dark', 'text', 4.5],
  ['태그 · 오늘 칩 글씨 / 페이지 배경색 칩', 'text', 'background', 4.5],
  // 상태 표시 · 포커스(비텍스트)
  ['선택 메뉴 검정 밑줄 / 오렌지 채움', 'text', 'primary', 3],
  ['선택 메뉴 검정 밑줄 / 카드(상단 바)', 'text', 'surface', 3],
  ['포커스 링 / 페이지 배경', 'focus', 'background', 3],
  ['포커스 링 / 카드', 'focus', 'surface', 3],
  ['포커스 링 / 오렌지', 'focus', 'primary', 3],
  ['포커스 링 / 노랑', 'focus', 'accent', 3],
  ['화면 제목 키보드 포커스 밑줄 / 페이지 배경', 'focus', 'background', 3],
  ['화면 제목 키보드 포커스 밑줄 / 카드(준비 중 화면)', 'focus', 'surface', 3],
  ['입력창 · 칩 테두리 / 카드', 'border-strong', 'surface', 3],
  ['입력창 · 칩 테두리 / 페이지 배경', 'border-strong', 'background', 3],
  ['기한 지남 칩 검정 테두리 / 카드', 'text', 'surface', 3],
  ['완료율 원 호(검정) / 원 바탕(장식 선 색)', 'text', 'border', 3],
];

for (const [label, fg, bg, min] of PAIRS) {
  const ratio = contrast(c(fg), c(bg));
  test(`대비 ${label}: ${ratio.toFixed(2)}:1 (기준 ${min}:1)`, () => {
    assert.ok(ratio >= min, `${label}: ${ratio.toFixed(2)}:1`);
  });
}

test('금지 조합: 오렌지 위 흰 글씨 · 밝은 배경 위 오렌지 글씨는 4.5:1이 안 된다(쓰지 않는다)', () => {
  assert.ok(contrast(c('on-dark'), c('primary')) < 4.5);
  assert.ok(contrast(c('primary'), c('surface')) < 4.5);
  // 오렌지 채움만으로는 카드와 3:1이 안 된다 → 선택 메뉴에 검정 밑줄 · 체크를 함께 쓴다
  assert.ok(contrast(c('primary'), c('surface')) < 3);
});
