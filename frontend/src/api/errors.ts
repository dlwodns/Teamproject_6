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

/**
 * 서버에 그 요청이 아직 없다(HTTP 404 · 405 · 501, FE 제안 요청에서만).
 * 화면은 이 오류면 그 부분을 숨긴다. 0건 · 빈 화면으로 보이거나 모의 데이터로 바꾸지 않는다(components.md 1절 6번).
 * HttpError와 따로 둔다: '고장'(다시 시도 안내)과 '아직 없음'(숨김)을 화면이 다르게 다뤄야 해서다.
 */
export class NotAvailableError extends Error {
  override name = 'NotAvailableError';
  readonly status: number;
  readonly endpoint: string;
  constructor(endpoint: string, status: number) {
    super(`${endpoint}: 서버에 아직 없는 요청 (${status})`);
    this.endpoint = endpoint;
    this.status = status;
  }
}
