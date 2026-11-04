// VITE_ 환경 변수는 빌드 결과에 그대로 들어가 누구나 볼 수 있다. 비밀값을 넣지 않는다(infra/plan.md 3-4).
import { ConfigError } from './errors.ts';

export type ApiMode = 'mock' | 'http';

export interface ApiConfig {
  mode: ApiMode;
  baseUrl: string;
}

/** VITE_API_MODE: mock(기본) | http. 그 밖의 값은 설정 오류로 본다(모의 데이터로 몰래 바꾸지 않는다). */
export function readApiConfig(env: { VITE_API_MODE?: string; VITE_API_BASE?: string }): ApiConfig {
  const mode = env.VITE_API_MODE?.trim() || 'mock';
  if (mode !== 'mock' && mode !== 'http') {
    throw new ConfigError(`VITE_API_MODE는 mock 또는 http여야 한다 (지금: ${mode})`);
  }
  const baseUrl = (env.VITE_API_BASE?.trim() || '/api').replace(/\/+$/, '');
  return { mode, baseUrl };
}
