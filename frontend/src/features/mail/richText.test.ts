import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cleanStyle, hasFormatting, safeHref, textToHtml } from './richText.ts';

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
