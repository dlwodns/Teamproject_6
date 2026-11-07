// 화면이 오류 종류에 따라 안내를 다르게 할 수 있게 나눈다.

/** 응답이 FE가 기대한 형식이 아니다(필드 누락 · 시간대 없는 시각 등). */
export class ContractError extends Error {
  override name = 'ContractError';
}

/** 서버가 오류 상태 코드를 돌려줬다. */
export class HttpError extends Error {
  override name = 'HttpError';
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** 요청이 서버에 닿지 못했다(연결 거부 · 주소 찾기 실패 · 오프라인 등). fetch 호출 경계(httpClient.ts)에서만 만든다. */
export class NetworkError extends Error {
  override name = 'NetworkError';
}

/** 환경 변수 설정이 잘못됐다. */
export class ConfigError extends Error {
  override name = 'ConfigError';
}
