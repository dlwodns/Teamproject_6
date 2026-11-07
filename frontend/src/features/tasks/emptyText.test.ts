import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NATURE_COLUMNS, PRIORITY_COLUMNS } from './aggregate.ts';
import { emptyNatureText, emptyPriorityText, withRo } from './emptyText.ts';

test('모든 칸의 빈 칸 문구 (왼쪽은 포함 조건, 오른쪽은 분류 이름 + 조사)', () => {
  assert.deepEqual([...PRIORITY_COLUMNS.map(emptyPriorityText), ...NATURE_COLUMNS.map(emptyNatureText)], [
    '기한이 지났거나 오늘·내일 마감인 미처리 업무가 없습니다.',
    '상급자가 보낸 메일에서 나온 미처리 업무가 없습니다.',
    '즐겨찾기한 발신자의 메일에서 나온 미처리 업무가 없습니다.',
    '회신으로 분류된 미처리 업무가 없습니다.',
    '요청으로 분류된 미처리 업무가 없습니다.',
    '검토로 분류된 미처리 업무가 없습니다.',
    '기타로 분류된 미처리 업무가 없습니다.',
  ]);
});

test('ㄹ 받침은 로, 한글이 아니면 (으)로', () => {
  assert.equal(withRo('메일'), '메일로');
  assert.equal(withRo('ABC'), 'ABC(으)로');
});
