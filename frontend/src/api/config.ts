// VITE_ 환경 변수는 빌드 결과에 그대로 들어가 누구나 볼 수 있다. 비밀값을 넣지 않는다(infra/plan.md 3-4).
import { ConfigError } from './errors.ts';

export type ApiMode = 'mock' | 'http';

export interface ApiConfig {
  mode: ApiMode;
  baseUrl: string;
  /** 실제 모드에서 X-User-Id 헤더로 보낼 사용자 번호(로그인이 생기기 전까지, backend core/user.py) */
  userId: string;
}

/** VITE_API_MODE: mock(기본) | http. 그 밖의 값은 설정 오류로 본다(모의 데이터로 몰래 바꾸지 않는다). */
export function readApiConfig(env: { VITE_API_MODE?: string; VITE_API_BASE?: string; VITE_USER_ID?: string }): ApiConfig {
  const mode = env.VITE_API_MODE?.trim() || 'mock';
  if (mode !== 'mock' && mode !== 'http') {
    throw new ConfigError(`VITE_API_MODE는 mock 또는 http여야 한다 (지금: ${mode})`);
  }
  const baseUrl = (env.VITE_API_BASE?.trim() || '/api').replace(/\/+$/, '');
  // 운영 모드(APP_MODE=prod) backend는 X-User-Id가 없으면 업무 변경 · 명령을 401로 막는다(#53 리뷰).
  // 비우면 시연 사용자 1번(backend 개발 모드 기본값과 같음). 숫자가 아니면 설정 오류로 알린다
  const userId = env.VITE_USER_ID?.trim() || '1';
  if (!/^[1-9][0-9]{0,17}$/.test(userId)) {
    throw new ConfigError(`VITE_USER_ID는 1 이상의 숫자여야 한다 (지금: ${userId})`);
  }
  return { mode, baseUrl, userId };
}
