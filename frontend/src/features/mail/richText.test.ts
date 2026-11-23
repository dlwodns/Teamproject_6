import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cleanStyle, hasFormatting, imageProblem, safeHref, tableHtml, textToHtml } from './richText.ts';

test('AI-32 붙여넣기 style: 서식 속성만, url() · expression은 버린다', () => {
  assert.equal(cleanStyle('color: red; position: fixed; background-color: yellow'), 'color: red; background-color: yellow');
  assert.equal(cleanStyle('background-color: url(http://t/x); line-height: 1.5'), 'line-height: 1.5');
  assert.equal(cleanStyle('font-family: expression(alert(1))'), '');
});

test('AI-32 링크는 http · https · mailto만', () => {
  assert.equal(safeHref('https://example.com'), true);
  assert.equal(safeHref(' mailto:a@b.c'), true);
  assert.equal(safeHref('javascript:alert(1)'), false);
  assert.equal(safeHref('data:text/html,x'), false);
});

test('AI-32 서식이 없으면 글 그대로 보낸다, 템플릿 글은 이스케이프', () => {
  assert.equal(hasFormatting('안녕하세요<div>둘째 줄<br></div>'), false);
  assert.equal(hasFormatting('<b>굵게</b>'), true);
  assert.equal(hasFormatting('<div style="text-align: center">가운데</div>'), true);
  assert.equal(textToHtml('<김> & "팀"\n감사합니다'), '&lt;김&gt; &amp; &quot;팀&quot;<br>감사합니다');
});

test('AI-39 표 넣기: 행 × 열 칸, 서식 있는 메일로 보낸다', () => {
  const t = tableHtml(2, 3);
  assert.equal(t.match(/<tr>/g)?.length, 2);
  assert.equal(t.match(/<td /g)?.length, 6);
  assert.equal(hasFormatting(t), true);
  assert.equal(cleanStyle('border-collapse: collapse; width: 100%; position: fixed'), 'border-collapse: collapse; width: 100%');
});

test('AI-39 그림 넣기: png · jpeg · gif · webp, 3MB 미만만', () => {
  assert.equal(imageProblem({ type: 'image/png', size: 1000 }), null);
  assert.match(imageProblem({ type: 'image/svg+xml', size: 10 }) ?? '', /PNG/);
  assert.match(imageProblem({ type: 'image/jpeg', size: 3 * 1024 * 1024 }) ?? '', /3MB/);
});
