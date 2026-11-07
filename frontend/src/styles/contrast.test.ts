// 실제 토큰 값(tokens.css)으로 화면에 쓰는 색 조합의 대비를 검사한다(WCAG 2.x 상대 휘도 공식).
// 글씨 4.5:1(큰 글씨 3:1), 상태를 알리는 비텍스트 표시 · 포커스 링 · 필수 경계 3:1. 장식용 경계는 검사 대상이 아니다.
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

test('브랜드 색은 LG CI 공개 값(Heritage Red · LG RED, RGB 165/0/52)이다', () => {
  assert.equal(c('brand').toUpperCase(), '#A50034');
});

// [설명, 앞, 뒤, 최소 대비]
const PAIRS: Array<[string, string, string, number]> = [
  // 글씨
  ['본문 · 제목 / 페이지 바탕', 'text', 'background', 4.5],
  ['본문 · 제목 / 카드', 'text', 'surface', 4.5],
  ['본문 / 마우스 올림 바탕', 'text', 'hover', 4.5],
  ['선택 메뉴 글씨 / 옅은 브랜드 바탕', 'text', 'brand-soft', 4.5],
  ['보조 글씨 / 페이지 바탕', 'text-sub', 'background', 4.5],
  ['보조 글씨 / 카드', 'text-sub', 'surface', 4.5],
  ['주 버튼 글씨 / 브랜드 레드', 'on-brand', 'brand', 4.5],
  ['주 버튼 글씨 / 브랜드 마우스 올림', 'on-brand', 'brand-hover', 4.5],
  ['주 버튼 글씨 / 브랜드 누름', 'on-brand', 'brand-pressed', 4.5],
  ['기한 지남 칩 · 경고 띠 글씨 / 위험 바탕', 'danger', 'danger-bg', 4.5],
  ['오늘 마감 칩 글씨 / 주의 바탕', 'warning-text', 'warning-bg', 4.5],
  ['모의 데이터 배지 글씨 / 주의 바탕', 'text', 'warning-bg', 4.5],
  ['건수 배지 글씨 / 검정 배지', 'on-dark', 'text', 4.5],
  // 상태 표시 · 포커스 · 필수 경계(비텍스트)
  ['선택 메뉴 브랜드 막대 / 옅은 브랜드 바탕', 'brand', 'brand-soft', 3],
  ['선택 메뉴 브랜드 막대 / 카드', 'brand', 'surface', 3],
  ['에이전트 원형 버튼 / 페이지 바탕', 'brand', 'background', 3],
  ['에이전트 원형 버튼 아이콘 / 브랜드 레드', 'on-brand', 'brand', 3],
  ['포커스 링 / 페이지 바탕', 'focus', 'background', 3],
  ['포커스 링 / 카드', 'focus', 'surface', 3],
  ['포커스 링 / 옅은 브랜드 바탕', 'focus', 'brand-soft', 3],
  ['화면 제목 키보드 포커스 밑줄 / 페이지 바탕', 'focus', 'background', 3],
  ['입력창 · 칩 테두리 / 카드', 'border-strong', 'surface', 3],
  ['입력창 · 칩 테두리 / 페이지 바탕', 'border-strong', 'background', 3],
  ['기한 지남 칩 테두리 / 카드', 'danger', 'surface', 3],
  ['완료율 원 호 / 원 바탕(장식 선 색)', 'success', 'border', 3],
];

for (const [label, fg, bg, min] of PAIRS) {
  const ratio = contrast(c(fg), c(bg));
  test(`대비 ${label}: ${ratio.toFixed(2)}:1 (기준 ${min}:1)`, () => {
    assert.ok(ratio >= min, `${label}: ${ratio.toFixed(2)}:1`);
  });
}
