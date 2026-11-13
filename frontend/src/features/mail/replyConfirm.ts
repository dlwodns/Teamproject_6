// 답장을 보낸 뒤 할 일(wireframe 13-5 완료 확인 시트 · UX-D6 · D48).
// - 그 메일에 끝나지 않은 업무가 없으면: 토스트 '답장을 보냈어요'만
// - '오늘 다시 보지 않음'을 고른 시각(reply_confirm_skip_until)이 아직 지나지 않았으면: 시트 없이 바로 완료(reply_auto)
// - 그 밖에는 시트 "완료로 처리할까요?"
import type { TaskId } from '../../api/types.ts';

const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;
const KST = 9 * 60 * MINUTE;
const HH_MM = /^([01]\d|2[0-3]):([0-5]\d)$/;

/**
 * 다음 아침 알림 시각(KST remindTime): 지금보다 뒤에 오는 가장 가까운 그 시각.
 * 오늘 그 시각 전이면 오늘, 지났으면(같은 시각 포함) 내일. 형식이 틀리면 08:30으로 본다(설정 기본값).
 */
export function nextRemindAtMs(nowMs: number, remindTime: string): number {
  const m = HH_MM.exec(remindTime);
  const minutes = m ? Number(m[1]) * 60 + Number(m[2]) : 8 * 60 + 30;
  const day = Math.floor((nowMs + KST) / DAY);
  const today = day * DAY - KST + minutes * MINUTE;
  return today > nowMs ? today : today + DAY;
}

export type AfterSend =
  | { kind: 'sent-only' }
  | { kind: 'auto-complete'; taskIds: TaskId[]; untilMs: number }
  | { kind: 'sheet'; taskIds: TaskId[] };

/**
 * @param openTaskIds 그 메일의 끝나지 않은 업무
 * @param skipUntilMs 설정 reply_confirm_skip_until(null = 꺼짐, undefined = 서버가 안 보냄)
 */
export function decideAfterSend(openTaskIds: readonly TaskId[], skipUntilMs: number | null | undefined, nowMs: number): AfterSend {
  if (openTaskIds.length === 0) return { kind: 'sent-only' };
  if (typeof skipUntilMs === 'number' && skipUntilMs > nowMs) return { kind: 'auto-complete', taskIds: [...openTaskIds], untilMs: skipUntilMs };
  return { kind: 'sheet', taskIds: [...openTaskIds] };
}

/**
 * 데이터 기준 지금 시각: 받은 자료의 기준 시각(as_of)에 받은 뒤 흐른 시간을 더한다.
 * 모의 모드는 시연 날짜(11/6) 시계로 돌기 때문에 브라우저 시각(Date.now())을 그대로 쓰면 '오늘'이 어긋난다.
 */
export function dataNowMs(asOfMs: number, fetchedAtMs: number, realNowMs: number): number {
  return asOfMs + Math.max(0, realNowMs - fetchedAtMs);
}
