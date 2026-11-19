// 테마(theme.css): 라이트 값은 고정 토큰(tokens.css)과 같고, 다크 값도 같은 대비 기준(글자 4.5:1 · 표시 3:1)을 넘는다.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (f: string) => readFileSync(new URL(f, import.meta.url), 'utf8');
const base = Object.fromEntries([...read('./tokens.css').matchAll(/^\s*--c-([a-z-]+):\s*([^;]+);/gm)].map((m) => [m[1], m[2]!.trim()]));
const pairs = [...read('./theme.css').matchAll(/--c-([a-z-]+):\s*light-dark\((.+?),\s*(#[0-9a-f]{6}|rgba\([^)]*\))\);/g)];
const light = Object.fromEntries(pairs.map((m) => [m[1], m[2]!.trim()]));
const dark = Object.fromEntries(pairs.map((m) => [m[1], m[3]!.trim()]));

test('테마가 고정 토큰의 색을 빠짐없이 다시 정하고, 라이트 값은 tokens.css와 같다', () => {
  assert.deepEqual(Object.keys(light).sort(), Object.keys(base).sort());
  for (const [k, v] of Object.entries(base)) assert.equal(light[k], v, `--c-${k}`);
});

const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
};
const ratio = (a: string, b: string) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
};

// contrast.test.ts와 같은 조합(다크 값으로)
const PAIRS: Array<[string, string, number]> = [
  ['ink', 'surface', 4.5], ['ink', 'canvas', 4.5], ['ink', 'fill', 4.5], ['gray', 'surface', 4.5], ['sub', 'surface', 4.5], ['sub', 'canvas', 4.5],
  ['on-strong', 'point', 4.5], ['on-strong', 'point-press', 4.5], ['on-strong', 'ink', 4.5],
  ['due-urgent-text', 'due-urgent-bg', 4.5], ['due-today-text', 'due-today-bg', 4.5], ['due-later-text', 'due-later-bg', 4.5],
  ['due-none-text', 'due-none-bg', 4.5], ['info', 'info-bg', 4.5], ['done', 'done-bg', 4.5], ['danger', 'danger-bg', 4.5],
  ['remind', 'remind-bg', 4.5], ['ink', 'mark', 4.5], ['sub', 'mark', 4.5], ['ink', 'mark-strong', 4.5],
  ['point', 'fill', 3], ['point', 'canvas', 3], ['ink', 'canvas', 3], ['input', 'surface', 3], ['input', 'canvas', 3],
  ['done-bar', 'line', 3], ['info', 'canvas', 3], ['mark-line', 'surface', 3], ['mark-line', 'mark', 3], ['info-dot', 'surface', 3],
];

for (const [fg, bg, min] of PAIRS) {
  test(`다크 대비 ${fg} / ${bg} ≥ ${min}:1`, () => {
    const r = ratio(dark[fg]!, dark[bg]!);
    assert.ok(r >= min, `${fg}/${bg}: ${r.toFixed(2)}:1`);
  });
}

test('다크에서도 입력칸 테두리 색은 글자 4.5:1에 못 미쳐 글자에 쓰지 않는다', () => {
  assert.ok(ratio(dark.input!, dark.surface!) < 4.5);
});
