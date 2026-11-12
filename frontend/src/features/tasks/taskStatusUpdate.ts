// 업무 상태가 바뀐 결과를 화면 데이터에 반영한다(FE-4). 집계는 바뀐 원본으로 buildDashboard를 다시 돌려 얻는다.
import type { TaskStatusChange } from '../../api/actions.ts';
import { ConfigError, ContractError, HttpError, NetworkError } from '../../api/errors.ts';
import type { DashboardSource } from '../../api/types.ts';

/** 바뀐 업무만 새 상태로 바꾼 새 원본. 목록에 없는 id는 무시한다(다른 화면에서 사라진 업무). 바뀐 게 없으면 같은 객체. */
export function applyTaskStatuses(src: DashboardSource, changes: readonly TaskStatusChange[]): DashboardSource {
  const next = new Map(changes.map((c) => [c.id, c.status]));
  let changed = false;
  const tasks = src.tasks.map((t) => {
    const s = next.get(t.id);
    if (s === undefined || s === t.status) return t;
    changed = true;
    return { ...t, status: s };
  });
  return changed ? { ...src, tasks } : src;
}

/** 완료 · 되돌리기 실패 안내. 서버 오류 원문 · 주소는 보이지 않는다. */
export function actionErrorText(verb: '완료로 바꾸지' | '되돌리지', error: unknown): string {
  const head = `${verb} 못했습니다.`;
  if (error instanceof NetworkError) return `${head} 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.`;
  if (error instanceof HttpError) {
    if (error.status === 409) return `${head} 이미 다른 곳에서 바뀌었습니다. 화면을 새로 불러와 주세요.`;
    if (error.status === 404) return `${head} 업무나 기록을 찾지 못했습니다(오류 코드 404). 화면을 새로 불러와 주세요.`;
    return `${head} (오류 코드 ${error.status}) 잠시 후 다시 시도해 주세요.`;
  }
  if (error instanceof ContractError) return `${head} 받은 응답을 읽을 수 없습니다. 문제가 계속되면 담당자에게 알려 주세요.`;
  if (error instanceof ConfigError) return `${head} 화면 설정에 문제가 있습니다. 담당자에게 알려 주세요.`;
  return `${head} 다시 시도해 주세요.`;
}
