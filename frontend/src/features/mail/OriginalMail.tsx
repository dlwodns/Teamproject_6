// 회신 · 전달 쓰기 화면 아래의 원본 메일(AI-42, 아웃룩 회신 화면과 같게). 내가 쓰는 칸과 선으로 확실히 나누고,
// 아웃룩이 붙이는 머리(보낸 사람 · 보낸 날짜 · 받는 사람 · 참조 · 제목)를 그대로 보인다. 보낼 때는 Outlook(Graph createReply ·
// createForward)이 이 원본을 붙이므로 화면은 보여 주기만 한다.
import type { Mail } from '../../api/types.ts';
import { useMailQuery } from '../../api/queries.ts';
import { HtmlBody } from './HtmlBody.tsx';
import styles from './Compose.module.css';

const WHEN = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'full', timeStyle: 'short' });

export function OriginalMail({ mail, senderLabel, forward }: { mail: Mail; senderLabel: string; forward: boolean }) {
  const detail = useMailQuery(mail.id);
  const d = detail.data;
  const rows: [string, string][] = [
    ['보낸 사람', senderLabel === mail.sender ? mail.sender : `${senderLabel} <${mail.sender}>`],
    ['보낸 날짜', WHEN.format(mail.receivedAtMs)],
    ['받는 사람', (d?.to ?? mail.to ?? []).join('; ')],
    ['참조', (d?.cc ?? []).join('; ')],
    ['제목', mail.subject],
  ];
  return (
    <section className={styles.original} aria-label="원본 메일">
      <h3 className={styles.sectionTitle}>원본 메일</h3>
      <p className={styles.originalNote}>{forward ? '이 원본이 내 글 아래에 붙어 전달됩니다' : '이 원본이 내 회신 아래에 붙어 나갑니다'}</p>
      <dl className={styles.originalHead}>
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}:</dt> <dd lang={k === '제목' ? (mail.lang ?? undefined) : undefined}>{v}</dd>
            </div>
          ))}
      </dl>
      <div className={styles.originalBody} lang={mail.lang ?? undefined}>
        {d?.bodyHtml ? <HtmlBody html={d.bodyHtml} marks={[]} active={null} /> : d?.body.map((p, i) => <p key={i}>{p}</p>)}
      </div>
    </section>
  );
}
