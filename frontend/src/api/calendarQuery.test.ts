// 캘린더 쿼리 주기 재조회(BE-D24 보완): 화면을 열어 둔 동안 1분마다 다시 묻는다. 같은 키라 보던 기간이 바뀌지 않는다.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { environmentManager, QueryClient, QueryObserver } from '@tanstack/react-query';
import type { CalendarRange } from './contract.ts';
import { CALENDAR_REFRESH_MS, calendarKey, calendarQueryOptions } from './queries.ts';

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve();
};

test('캘린더는 지켜보는 동안 60초마다 다시 묻고, 멈추면 더 묻지 않는다', async (t) => {
  // Node에는 window가 없어 React Query가 서버로 보고 주기 재조회를 끈다. 브라우저 화면처럼 보게 한다(끝나면 되돌림)
  const wasServer = environmentManager.isServer();
  environmentManager.setIsServer(() => false);
  t.after(() => environmentManager.setIsServer(() => wasServer));
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] });
  const calls: string[] = [];
  const range = (start: string, end: string): CalendarRange => ({ start, end, asOfMs: 0, items: [] }) as unknown as CalendarRange;
  const client = new QueryClient();
  const observer = new QueryObserver(
    client,
    calendarQueryOptions('2026-10-26', '2026-12-06', async (s, e) => {
      calls.push(`${s}~${e}`);
      return range(s, e);
    }),
  );
  const stop = observer.subscribe(() => {});
  await flush();
  assert.equal(calls.length, 1, '처음 한 번');
  t.mock.timers.tick(CALENDAR_REFRESH_MS - 1);
  await flush();
  assert.equal(calls.length, 1, '60초 전에는 다시 묻지 않는다');
  t.mock.timers.tick(1);
  await flush();
  assert.equal(calls.length, 2, '60초에 다시 묻는다');
  t.mock.timers.tick(CALENDAR_REFRESH_MS);
  await flush();
  assert.deepEqual(calls, Array(3).fill('2026-10-26~2026-12-06'), '같은 기간(보던 달)을 다시 묻는다');
  assert.deepEqual(observer.getCurrentQuery().queryKey, calendarKey('2026-10-26', '2026-12-06'));
  stop();
  t.mock.timers.tick(CALENDAR_REFRESH_MS * 3);
  await flush();
  assert.equal(calls.length, 3, '화면을 떠나면(지켜보는 쪽 없음) 멈춘다');
  client.clear();
});
