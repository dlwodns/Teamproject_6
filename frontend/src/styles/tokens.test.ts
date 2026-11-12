// 디자인 토큰 고정 검사 (UX-D17)
// 토큰을 바꾸려면 결정(decisions.md UX-D) → tokens.css → npm run tokens:export → design_system.md 고정 해시를 한 커밋에서 함께 고친다.
// 이 셋 중 하나만 바뀌면 여기서 실패한다.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));
const SCRIPT = here('../../scripts/tokens-export.mjs');
const RECORD = here('./cne.tokens.json');
const DESIGN_SYSTEM = here('../../../docs/20_frontend/design_system.md');

test('tokens.css와 고정 기록(cne.tokens.json · cne.figma.tokens.json)이 같다', () => {
  // 다르면 스크립트가 0이 아닌 값으로 끝나 execFileSync가 예외를 던진다
  execFileSync(process.execPath, [SCRIPT, '--check'], { stdio: 'pipe' });
});

test('고정 기록의 해시가 design_system.md에 적힌 고정 해시와 같다', () => {
  const sha = createHash('sha256').update(readFileSync(RECORD)).digest('hex').slice(0, 16);
  const doc = readFileSync(DESIGN_SYSTEM, 'utf8');
  const m = doc.match(/고정 해시[^`]*`([0-9a-f]{16})`/);
  assert.ok(m, 'design_system.md에 "고정 해시 `…`" 줄이 없다');
  assert.equal(sha, m[1], '토큰 기록이 바뀌었다. 결정 없이 토큰을 바꾸지 않는다(UX-D17)');
});

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return cssFiles(p);
    return p.endsWith('.css') && !p.endsWith('tokens.css') ? [p] : [];
  });
}

test('화면 CSS에는 색 HEX를 직접 쓰지 않는다(토큰 변수만)', () => {
  const offenders = cssFiles(here('..')).flatMap((file) =>
    readFileSync(file, 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .map((line, i) => [line, i + 1] as const)
      .filter(([line]) => /#[0-9a-fA-F]{3,8}\b/.test(line))
      .map(([line, n]) => `${file}:${n}: ${line.trim()}`),
  );
  assert.deepEqual(offenders, []);
});
