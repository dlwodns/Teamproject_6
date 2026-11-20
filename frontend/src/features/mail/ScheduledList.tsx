// 예약 보내기 목록(BE-7 단계 2): 메일을 고르지 않았을 때 읽기 자리 아래에 보인다. 없으면 아무것도 그리지 않는다.
// 아직 안 나간 것은 [취소], 실패 · 보냈는지 모름은 이유와 [치우기]. 서버가 예약을 모르면(옛 서버) 숨긴다.
import { useCancelScheduled, useScheduledSendsQuery } from '../../api/queries.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { Button, useToast } from '../../ui/index.ts';
import styles from './ScheduledList.module.css';

const STATUS: Record<string, string> = { pending: '예약됨', sending: '보내는 중', failed: '보내지 못함', unknown: '보냈는지 모름 · 보낸 편지함 확인' };

export function ScheduledList() {
  const q = useScheduledSendsQuery();
  const cancel = useCancelScheduled();
  const toast = useToast();
  const rows = q.isNotAvailable ? [] : (q.data ?? []);
  if (rows.length === 0) return null;
  return (
    <section className={styles.list} aria-labelledby="scheduled-title">
      <h2 id="scheduled-title" className={styles.title}>
        예약 보내기 {rows.length}
      </h2>
      <ul>
        {rows.map((r) => (
          <li key={r.scheduledId} className={styles.row}>
            <span className={styles.main}>
              <b>{r.subject}</b>
              <span className={styles.meta}>
                {formatKstShort(r.sendAtMs)} · {r.to || '받는 사람'} · {STATUS[r.status] ?? r.status}
                {r.error && r.status === 'failed' ? ` (${r.error})` : ''}
              </span>
            </span>
            {r.status !== 'sending' && (
              <Button
                size="sm"
                variant="ghost"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate(r.scheduledId, { onError: () => toast.show({ kind: 'error', title: '바꾸지 못했습니다' }) })}
              >
                {r.status === 'pending' ? '취소' : '치우기'}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
