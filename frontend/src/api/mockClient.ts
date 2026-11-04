// 모의 모드: src/api/mock/dashboard.v1.json(scripts/extract-mock.mjs로 만든 파일)을 실제 응답처럼 읽는다.
// 실제 모드와 같은 adapter를 거친다.
import { toDashboardSource } from './adapter.ts';
import type { DashboardApi } from './client.ts';
import { HttpError } from './errors.ts';
import type { DashboardSource } from './types.ts';

/** 화면 상태 확인용: 주소에 ?mock=loading | empty | error 를 붙이면 그 상태를 흉내 낸다(모의 모드에서만). */
export type MockPreview = 'loading' | 'empty' | 'error' | null;

export function readMockPreview(search: string): MockPreview {
  const v = new URLSearchParams(search).get('mock');
  return v === 'loading' || v === 'empty' || v === 'error' ? v : null;
}

export function createMockApi(preview: MockPreview): DashboardApi {
  return {
    async getDashboardSource(signal) {
      if (preview === 'loading') {
        return new Promise<DashboardSource>((_, reject) => {
          signal?.addEventListener('abort', () => reject(signal.reason));
        });
      }
      if (preview === 'error') throw new HttpError(503, '모의 오류 상태(?mock=error)');
      const file = (await import('./mock/dashboard.v1.json')).default;
      const origin = { kind: 'mock', dataset: file.meta.dataset, version: file.meta.version } as const;
      const source = toDashboardSource(file.response, origin);
      return preview === 'empty' ? { ...source, mails: [], tasks: [], contacts: [] } : source;
    },
  };
}
