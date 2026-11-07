// 대시보드 오류를 사용자가 이해할 수 있는 안내로 바꾼다. 브라우저 오류 원문 · 내부 진단(필드 경로 · 주소)은 화면에 내지 않는다.
// 내부 분류(ContractError · ConfigError 등)는 그대로 두고 문구만 정한다.
import { ConfigError, ContractError, HttpError, NetworkError } from '../../api/errors.ts';

export function dashboardErrorText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.';
  if (error instanceof HttpError) {
    if (error.status === 404) return `대시보드 데이터를 아직 받을 수 없습니다(오류 코드 ${error.status}). 잠시 후 다시 시도해 주세요.`;
    if (error.status >= 500) return `서버에서 문제가 생겨 데이터를 받지 못했습니다(오류 코드 ${error.status}). 잠시 후 다시 시도해 주세요.`;
    return `요청이 처리되지 않았습니다(오류 코드 ${error.status}). 문제가 계속되면 담당자에게 알려 주세요.`;
  }
  if (error instanceof ContractError) return '받은 데이터를 화면에 표시할 수 없습니다. 문제가 계속되면 담당자에게 알려 주세요.';
  if (error instanceof ConfigError) return '화면 설정에 문제가 있어 데이터를 불러오지 못했습니다. 담당자에게 알려 주세요.';
  return '알 수 없는 문제로 데이터를 불러오지 못했습니다. 다시 시도해 주세요.';
}
