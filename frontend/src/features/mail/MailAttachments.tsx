// 받은 메일의 첨부(BE-7 단계 2): 이름 · 크기, 누르면 내려받는다. Outlook 메일이 아니면(서버 501) · 첨부가 없으면 그리지 않는다.
// 파일은 서버도 저장하지 않고 누를 때 Outlook에서 가져온다(구조도 10절).
import { api } from '../../api/client.ts';
import type { MailId } from '../../api/types.ts';
import { useAttachmentsQuery } from '../../api/queries.ts';
import { Button, useToast } from '../../ui/index.ts';
import styles from './ScheduledList.module.css';

/** 그림 첨부는 아웃룩처럼 작은 미리보기를 보인다(AI-42). 서버가 그림 형식만 내준다 */
const IMAGE = /^image\/(png|jpeg|gif|webp|bmp)$/i;
const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`);

export function MailAttachments({ mailId }: { mailId: MailId }) {
  const q = useAttachmentsQuery(mailId);
  const toast = useToast();
  const files = q.isNotAvailable ? [] : (q.data ?? []);
  if (files.length === 0) return null;
  const download = async (attId: string, name: string) => {
    try {
      const url = URL.createObjectURL(await api.downloadAttachment(mailId, attId));
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      toast.show({ kind: 'error', title: '첨부를 내려받지 못했습니다' });
    }
  };
  return (
    <section className={styles.list} aria-label={`첨부 ${files.length}개`}>
      <h2 className={styles.title}>첨부 {files.length}</h2>
      <ul>
        {files.map((f) => (
          <li key={f.id} className={styles.row}>
            {f.contentType && IMAGE.test(f.contentType) && (
              <img
                className={styles.thumb}
                src={`/api/mails/${mailId}/attachments/${encodeURIComponent(f.id)}?view=1`}
                alt={f.name}
                loading="lazy"
                onError={(e) => e.currentTarget.remove()}
              />
            )}
            <span className={styles.main}>
              <b>{f.name}</b>
              <span className={styles.meta}>{kb(f.size)}</span>
            </span>
            <Button size="sm" variant="ghost" aria-label={`${f.name} 내려받기`} onClick={() => void download(f.id, f.name)}>
              내려받기
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
