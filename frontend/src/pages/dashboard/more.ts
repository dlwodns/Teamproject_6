// 더보기 사이드바(LP)에 무엇을 여는지와 그 제목. 제목은 건수를 담아 완료 뒤에도 다시 계산한다(V-9 '요청 · 6').
import { moreTitle, TYPE_COLUMNS, type DashboardModel, type TypeColumnKey } from '../../features/tasks/aggregate.ts';

export type MoreKey = 'urgent' | 'favorites' | TypeColumnKey | 'checks' | 'awaiting';

export const MORE_NAMES: Record<MoreKey, string> = {
  urgent: '긴급',
  favorites: '즐겨찾기',
  회신: '회신',
  요청: '요청',
  검토: '검토',
  기타: '기타',
  checks: '확인사항',
  awaiting: '응답 대기',
};

export function isTypeKey(key: MoreKey): key is TypeColumnKey {
  return (TYPE_COLUMNS as readonly string[]).includes(key);
}

/** 그 칸 전체 건수. 카드가 숨겨진 칸(데이터 없음)이면 null */
export function moreCount(key: MoreKey, model: DashboardModel): number | null {
  if (key === 'urgent') return model.urgent.length;
  if (key === 'favorites') return model.favorites.length;
  if (key === 'checks') return model.checks ? model.checks.확인.length + model.checks.참고.length : null;
  if (key === 'awaiting') return model.awaiting ? model.awaiting.length : null;
  return model.typeCounts[key].own; // 긴급과 겹치는 업무는 세지 않는다(카드 머리와 같은 숫자)
}

export function moreTitleOf(key: MoreKey, model: DashboardModel | null): string {
  const count = model ? moreCount(key, model) : null;
  return count === null ? MORE_NAMES[key] : moreTitle(MORE_NAMES[key], count);
}
