// 업무 완료 움직임 순서(UX-D9): 체크 → 빠짐 → 접힘 → 서버 요청, 실패하면 줄이 돌아온다.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { TaskId } from '../../api/types.ts';
import { createCompletionStore, parseCssTimeMs, runCompletion, type CompletionDeps } from './completion.ts';

const ID = 5 as TaskId;
const TIMINGS = { checkMs: 150, slideMs: 250, collapseMs: 200 };

function harness(complete: CompletionDeps['complete'], reduceMotion = false) {
  const store = createCompletionStore();
  const log: string[] = [];
  store.subscribe(() => log.push(`phase:${store.get(ID) ?? '-'}`));
  const deps: CompletionDeps = {
    store,
    timings: TIMINGS,
    reduceMotion,
    wait: async (ms) => {
      log.push(`wait:${ms}`);
    },
    complete: async (ids) => {
      log.push(`complete:${ids.join(',')}:${store.get(ID)}`);
      return complete(ids);
    },
  };
  return { store, log, deps };
}

test('체크(--d-short) → data-leaving(--d-move + --d-exit) → 완료 요청 → 단계 지움', async () => {
  const h = harness(async () => undefined);
  assert.equal(await runCompletion(ID, h.deps), true);
  assert.deepEqual(h.log, ['phase:checked', 'wait:150', 'phase:leaving', 'wait:450', `complete:${ID}:leaving`, 'phase:-']);
  assert.equal(h.store.get(ID), undefined);
});

test('동작 줄이기: 기다리지 않고 바로 완료 요청', async () => {
  const h = harness(async () => undefined, true);
  assert.equal(await runCompletion(ID, h.deps), true);
  assert.ok(!h.log.some((l) => l.startsWith('wait:')));
});

test('서버 실패: false를 돌려주고 단계를 지워 줄이 돌아온다(던지지 않음)', async () => {
  const h = harness(async () => {
    throw new Error('실패');
  });
  assert.equal(await runCompletion(ID, h.deps), false);
  assert.equal(h.store.get(ID), undefined);
});

test('이미 빠지는 중인 업무를 다시 누르면 무시', async () => {
  let calls = 0;
  const h = harness(async () => {
    calls += 1;
  });
  const first = runCompletion(ID, h.deps);
  assert.equal(await runCompletion(ID, h.deps), false);
  await first;
  assert.equal(calls, 1);
});

test('CSS 시간 값 읽기', () => {
  assert.equal(parseCssTimeMs('150ms'), 150);
  assert.equal(parseCssTimeMs(' 0.25s'), 250);
  assert.equal(parseCssTimeMs(''), 0);
  assert.equal(parseCssTimeMs('var(--x)'), 0);
  assert.equal(parseCssTimeMs('0.01ms'), 0);
});
