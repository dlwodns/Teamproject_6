// 초안 메뉴 (FE-16 · 명세 5절): 에이전트가 쓴 회신 · 재촉 초안을 대화 결과에서 모아 보인다.
// 가운데 목록, 오른쪽은 대화 메뉴 결과물 칸과 같은 초안 화면(고쳐 쓰기 · [복사] · [답장 화면에서 열기]). 보내기는 없다(D48).
// 고른 초안은 결과물 칸 상태(agentViewer)와 같이 쓴다 — 토스트 [열기]로 들어와도 그 초안이 열린다.
import { useId } from 'react';
import { agentViewer, useAgentViewer } from '../../features/agent/agentViewer.ts';
import type { Run } from '../../features/agent/agentSession.ts';
import type { SenderOf } from '../../features/agent/AgentCards.tsx';
import { ResultViewer } from '../../features/agent/ResultViewer.tsx';
import { ChevronLeft, cx } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

interface Props {
  drafts: readonly Run[];
  senderOf: SenderOf;
  asOfMs: number;
}

export function DraftsView({ drafts, senderOf, asOfMs }: Props) {
  const { openRunId } = useAgentViewer();
  const headingId = useId();
  const viewerHeadingId = useId();
  const selected = drafts.find((r) => r.id === openRunId) ?? null;

  return (
    <div className={styles.split} data-view={selected ? 'detail' : 'list'}>
      <section className={styles.listCol} aria-labelledby={headingId}>
        <div className={styles.colHead}>
          <h2 id={headingId} className={styles.colTitle} tabIndex={-1} data-agent-heading="">
            초안
          </h2>
          {drafts.length > 0 && <span className={styles.colCount}>{drafts.length}건</span>}
        </div>
        <div className={styles.scroll}>
          {drafts.length === 0 ? (
            <div className={styles.empty}>
              <p className={styles.emptyTitle}>아직 쓴 초안이 없어요</p>
              <p className={styles.emptyText}>
                리마인더에서 [초안 보기] · [재촉 초안]을 누르거나 아래 입력에 "이 메일 회신 초안 써 줘"라고 말하면 여기에 모여요. 보내기는 답장 화면에서 직접 눌러요.
              </p>
            </div>
          ) : (
            <ul className={styles.plainList} aria-label="초안 목록">
              {drafts.map((r) => {
                const d = r.outcome?.type === 'draft' ? r.outcome.draft : null;
                if (!d) return null;
                return (
                  <li key={r.id}>
                    <button
                      type="button"
                      className={cx(styles.pick, r.id === selected?.id && styles.picked)}
                      aria-current={r.id === selected?.id ? 'true' : undefined}
                      onClick={() => agentViewer.open(r.id)}
                    >
                      <span className={styles.pickTitle}>{d.subject}</span>
                      <span className={styles.pickSub}>{`${d.to} · '${r.text}'`}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
      <div className={styles.detailCol}>
        {selected && (
          <button type="button" className={styles.backLink} onClick={() => agentViewer.close()}>
            <ChevronLeft size={16} aria-hidden="true" />
            뒤로
          </button>
        )}
        <ResultViewer
          run={selected}
          senderOf={senderOf}
          asOfMs={asOfMs}
          headingId={viewerHeadingId}
          heading="초안"
          emptyTitle="고른 초안이 없어요"
          emptyText="왼쪽 목록에서 초안을 고르면 여기서 고쳐 쓰고 복사할 수 있어요."
        />
      </div>
    </div>
  );
}
