import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { osReducedMotion, reducedMotion } from './motion.ts';

const g = globalThis as Record<string, unknown>;
const stub = (os: boolean, attr: boolean) => {
  g.matchMedia = () => ({ matches: os });
  g.document = { documentElement: { hasAttribute: () => attr } };
};
afterEach(() => {
  delete g.matchMedia;
  delete g.document;
});

test('둘 다 꺼져 있으면 움직인다', () => {
  stub(false, false);
  assert.equal(reducedMotion(), false);
});

test('CNE 설정만 켜도 줄인다(기기 설정과 상관없이)', () => {
  stub(false, true);
  assert.equal(reducedMotion(), true);
  assert.equal(osReducedMotion(), false);
});

test('기기 설정만 켜져 있어도 줄인다', () => {
  stub(true, false);
  assert.equal(reducedMotion(), true);
});

test('브라우저 밖(document · matchMedia 없음)에서는 움직임을 줄이지 않고 터지지 않는다', () => {
  assert.equal(reducedMotion(), false);
});
