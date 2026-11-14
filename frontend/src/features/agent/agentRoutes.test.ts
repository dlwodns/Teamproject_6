// 에이전트 화면 주소(FE-16 · UX-D19): 메뉴 · 묶음 · 고른 항목 읽기와 만들기
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AGENT_MENUS, menuPath, parseAgentPath, reminderPath } from './agentRoutes.ts';

test('리마인더 주소: 묶음이 없으면 전체, 항목 키는 인코딩해 오간다', () => {
  assert.deepEqual(parseAgentPath('reminders'), { menu: 'reminders', group: 'all', key: null });
  assert.deepEqual(parseAgentPath('reminders/deadline'), { menu: 'reminders', group: 'deadline', key: null });
  const path = reminderPath('deadline', 'overdue:task:1');
  assert.equal(path, '/agent/reminders/deadline/overdue%3Atask%3A1');
  assert.deepEqual(parseAgentPath(path.replace('/agent/', '')), { menu: 'reminders', group: 'deadline', key: 'overdue:task:1' });
  assert.equal(reminderPath(), '/agent/reminders/all');
});

test('다른 메뉴는 한 마디만. 모르는 주소 · 묶음 · 깨진 인코딩은 null(리마인더 전체로 바꿔 쓴다)', () => {
  for (const m of AGENT_MENUS.filter((x) => x !== 'reminders')) {
    assert.deepEqual(parseAgentPath(m), { menu: m });
    assert.equal(menuPath(m), `/agent/${m}`);
  }
  assert.equal(menuPath('reminders'), '/agent/reminders/all');
  assert.equal(parseAgentPath(''), null);
  assert.equal(parseAgentPath('chat/1'), null);
  assert.equal(parseAgentPath('reminders/nope'), null);
  assert.equal(parseAgentPath('reminders/due'), null); // 이유 묶음은 더 이상 채널이 아니다
  assert.equal(parseAgentPath('reminders/deadline/%E0%A4%A'), null);
  assert.equal(parseAgentPath('reminders/deadline/a/b'), null);
});
