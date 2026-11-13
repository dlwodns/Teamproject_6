// 디자인 토큰 고정 기록 만들기 (UX-D17)
// tokens.css의 :root 변수를 읽어 두 파일을 만든다. 의존성 없이 Node 내장 기능만 쓴다.
//   src/styles/cne.tokens.json        — 고정 기록 전체(DTCG 2025.10 형식). tokens.test.ts가 tokens.css와 같은지 본다
//   src/styles/cne.figma.tokens.json  — 피그마 변수 가져오기용(피그마가 받는 형식만: 색 · px · 초 · 숫자 · 글꼴 이름 하나)
// 쓰는 법
//   npm run tokens:export   두 파일을 다시 쓴다(토큰을 바꾸기로 결정한 뒤에만)
//   npm run tokens:check    다시 만든 결과가 커밋된 파일과 다르면 실패한다
import { readFileSync, writeFileSync } from 'node:fs';

const CSS = new URL('../src/styles/tokens.css', import.meta.url);
const FULL = new URL('../src/styles/cne.tokens.json', import.meta.url);
const FIGMA = new URL('../src/styles/cne.figma.tokens.json', import.meta.url);

/** 고정 대상에서 빼는 임시 변수(쓰는 곳을 지우면 함께 지운다) */
export const TEMPORARY = ['--sidebar-expanded', '--sidebar-collapsed'];

/** 변수 이름 앞부분 → 묶음 이름 · DTCG 형식. 위에서부터 먼저 맞는 것을 쓴다 */
const GROUPS = [
  ['--c-', 'color', 'color'],
  ['--font-', 'font-family', 'fontFamily'],
  ['--fs-', 'font-size', 'dimension'],
  ['--fw-', 'font-weight', 'fontWeight'],
  ['--lh-', 'line-height', 'number'],
  ['--sp-', 'space', 'dimension'],
  ['--space-', 'space', 'dimension'],
  ['--r-', 'radius', 'dimension'],
  ['--shadow-', 'shadow', 'shadow'],
  ['--d-', 'duration', 'duration'],
  ['--e-', 'easing', 'cubicBezier'],
  ['--z-', 'z-index', 'number'],
  ['--', 'layout', 'dimension'],
];

/** tokens.css의 :root 안 선언을 [이름, 값, 설명] 순서대로 읽는다 */
export function parseTokens(css) {
  const root = css.match(/:root\s*\{([\s\S]*?)\n\}/);
  if (!root) throw new Error('tokens.css에 :root 블록이 없다');
  const out = [];
  for (const line of root[1].split('\n')) {
    const m = line.match(/^\s*(--[a-z0-9-]+):\s*([^;]+);\s*(?:\/\*\s*(.*?)\s*\*\/)?\s*$/);
    if (m) out.push({ name: m[1], value: m[2].trim(), note: m[3] ?? '' });
  }
  return out;
}

const round = (x) => Math.round(x * 10000) / 10000;

function color(value) {
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16));
    return { colorSpace: 'srgb', components: [r, g, b].map((v) => round(v / 255)), alpha: 1, hex: `#${hex[1].toLowerCase()}` };
  }
  const rgba = value.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/);
  if (rgba) {
    const [r, g, b] = rgba.slice(1, 4).map(Number);
    const h = [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
    return { colorSpace: 'srgb', components: [r, g, b].map((v) => round(v / 255)), alpha: Number(rgba[4]), hex: `#${h}` };
  }
  throw new Error(`색 값을 읽지 못함: ${value}`);
}

function px(value) {
  const m = value.match(/^(\d+(?:\.\d+)?)px$/);
  if (!m) throw new Error(`px 값이 아님: ${value}`);
  return { value: Number(m[1]), unit: 'px' };
}

function fontFamily(value, all) {
  const expanded = value.replace(/var\((--[a-z-]+)\)/g, (_, n) => all.get(n) ?? '');
  return expanded.split(',').map((s) => s.trim().replace(/^'|'$/g, '')).filter(Boolean);
}

function shadow(value) {
  return value.split(/,(?![^(]*\))/).map((part) => {
    const m = part.trim().match(/^(-?\d+)(?:px)? (-?\d+)(?:px)? (\d+)(?:px)? (rgba\([^)]*\))$/);
    if (!m) throw new Error(`그림자 값을 읽지 못함: ${part}`);
    return { color: color(m[4]), offsetX: { value: Number(m[1]), unit: 'px' }, offsetY: { value: Number(m[2]), unit: 'px' }, blur: { value: Number(m[3]), unit: 'px' }, spread: { value: 0, unit: 'px' } };
  });
}

function toDtcg(type, value, all) {
  switch (type) {
    case 'color': return color(value);
    case 'fontFamily': return fontFamily(value, all);
    case 'dimension': return px(value);
    case 'fontWeight': return Number(value);
    case 'number': return Number(value);
    case 'shadow': return shadow(value);
    case 'duration': {
      const m = value.match(/^(\d+)ms$/);
      if (!m) throw new Error(`시간 값이 아님: ${value}`);
      return { value: Number(m[1]), unit: 'ms' };
    }
    case 'cubicBezier': {
      const m = value.match(/^cubic-bezier\(([^)]*)\)$/);
      if (!m) throw new Error(`easing 값이 아님: ${value}`);
      return m[1].split(',').map((s) => Number(s.trim()));
    }
    default: throw new Error(`모르는 형식: ${type}`);
  }
}

/** tokens.css 글자 → { full, figma } 두 객체 */
export function build(css) {
  const decls = parseTokens(css);
  const all = new Map(decls.map((d) => [d.name, d.value]));
  const full = { $description: 'CNE 디자인 토큰 v3.3 고정 기록(UX-D17). 원본은 frontend/src/styles/tokens.css, 이 파일은 scripts/tokens-export.mjs가 만든다. 손으로 고치지 않는다.' };
  const figma = {};
  for (const d of decls) {
    if (TEMPORARY.includes(d.name)) continue;
    const [prefix, group, type] = GROUPS.find(([p]) => d.name.startsWith(p));
    const key = d.name.slice(prefix.length);
    const $value = toDtcg(type, d.value, all);
    full[group] ??= { $type: type };
    full[group][key] = { $value, ...(d.note ? { $description: d.note } : {}), $extensions: { 'com.cne.css': d.name } };

    // 피그마는 cubicBezier · shadow를 받지 않고(손으로 효과 스타일을 만든다), 시간은 초 · 글꼴은 이름 하나만 받는다
    let fv;
    if (type === 'cubicBezier' || type === 'shadow' || d.name === '--font-fallback') continue;
    else if (type === 'duration') fv = { value: $value.value / 1000, unit: 's' };
    else if (type === 'fontFamily') fv = $value[0];
    else if (type === 'fontWeight') fv = $value;
    else if (type === 'color') fv = { colorSpace: 'srgb', components: $value.components, alpha: $value.alpha, hex: $value.hex };
    else fv = $value;
    const ftype = type === 'fontWeight' ? 'number' : type;
    figma[group] ??= { $type: ftype };
    figma[group][key] = { $value: fv, ...(d.note ? { $description: d.note } : {}) };
  }
  return { full, figma };
}

export const serialize = (obj) => `${JSON.stringify(obj, null, 2)}\n`;

const isMain = process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href;
if (isMain) {
  const { full, figma } = build(readFileSync(CSS, 'utf8'));
  const pairs = [[FULL, serialize(full)], [FIGMA, serialize(figma)]];
  if (process.argv.includes('--check')) {
    const stale = pairs.filter(([url, text]) => {
      try { return readFileSync(url, 'utf8') !== text; } catch { return true; }
    });
    if (stale.length) {
      console.error(`토큰 기록이 tokens.css와 다르다: ${stale.map(([u]) => u.pathname.split('/').pop()).join(', ')}`);
      console.error('토큰은 고정이다(UX-D17). 바꾸기로 결정했다면 npm run tokens:export 후 design_system.md 고정 해시도 고친다.');
      process.exit(1);
    }
    console.log('토큰 기록이 tokens.css와 같다.');
  } else {
    for (const [url, text] of pairs) writeFileSync(url, text);
    console.log('cne.tokens.json · cne.figma.tokens.json을 다시 썼다.');
  }
}
