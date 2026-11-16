// 결과물 칸 (FE-15 · FE-D20). 에이전트 화면 오른쪽 절반. 대화의 짧은 카드 [열기]로 고른 결과 하나를 크게 보인다.
// - 회신 초안: 그 자리에서 고쳐 쓰는 입력칸 + [복사] + [답장 화면에서 열기]. 보내기는 여기 두지 않는다(보내기는 답장 화면에서만)
// - 오늘 요약: 건수 줄 · 그 밖에 줄 → 브리핑 문장(있을 때) → '새로 정리 중'(서버가 다시 정리할 때) → 업무 목록
// - 업무 목록 · 답장 없는 메일: 줄을 누르면 그 메일로 간다(메일 화면 맨 위 [← 에이전트])
// - 아무것도 열지 않았으면 빈 상태
import { useId, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import type { AgentDraft, AgentSummary, AgentTarget } from '../../api/contract.ts';
import type { Awaiting, MailId } from '../../api/types.ts';
import { Button, ChevronRight, Copy, DueLabel, IconButton, LiveRegion, Spinner, X } from '../../ui/index.ts';
import { useOpenMail } from '../tasks/useOpenMail.ts';
import type { SenderOf } from './AgentCards.tsx';
import type { Run } from './agentSession.ts';
import { dueOf, replyDraftPath, targetStatusText } from './agentText.ts';
import { agentViewer, useAgentViewer } from './agentViewer.ts';
import styles from './ResultViewer.module.css';

interface Props {
  /** 연 결과. null = 빈 상태 */
  run: Run | null;
  senderOf: SenderOf;
  asOfMs: number;
  /** 결과물 칸 제목 id(화면이 aria-labelledby로 쓴다) */
  headingId: string;
  /** 제목 줄 오른쪽(브라우저 알림 켜기) */
  headExtra?: ReactNode;
  id?: string;
  /** 칸 제목(기본 '결과물'). 초안 메뉴는 '초안'(FE-16) */
  heading?: string;
  /**
   * 초안의 [답장 화면에서 열기] 모양. 대화 메뉴 결과물 칸은 채움(FE-D20 그대로), 초안 메뉴는 테두리 버튼이다 —
   * 초안 메뉴에서는 여러 초안을 오가며 고쳐 쓰는 것이 주된 일이고, 빨강 채움은 확정 동작에만 쓴다(UX-D18)
   */
  replyVariant?: 'primary' | 'secondary';
  /** 빈 상태 문구(기본은 대화 결과물 안내) */
  emptyTitle?: string;
  emptyText?: string;
  /** 있으면 제목 줄 오른쪽에 ✕(결과 칸을 접는다, 11-15) */
  onClose?: () => void;
}

export function ResultViewer({
  run,
  senderOf,
  asOfMs,
  headingId,
  headExtra,
  id,
  heading = '결과물',
  replyVariant = 'primary',
  emptyTitle = '열린 결과물이 없습니다',
  emptyText = '초안 · 요약 · 업무 목록은 대화에서 [열기]를 누르면 이곳에 표시됩니다.',
  onClose,
}: Props) {
  const o = run?.outcome ?? null;
  return (
    <section id={id} className={styles.viewer} aria-labelledby={headingId}>
      <div className={styles.head}>
        <h2 id={headingId} className={styles.heading}>
          {heading}
        </h2>
        {run && o && <p className={styles.said}>'{run.text}'</p>}
        {headExtra && <div className={styles.headExtra}>{headExtra}</div>}
        {onClose && <IconButton label="결과 닫기" icon={<X size={18} aria-hidden="true" />} className={styles.close} onClick={onClose} />}
      </div>
      <div className={styles.body}>
        {!run || !o ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>{emptyTitle}</p>
            <p className={styles.emptyText}>{emptyText}</p>
          </div>
        ) : o.type === 'draft' ? (
          <DraftView key={run.id} runId={run.id} title={o.title} draft={o.draft} replyVariant={replyVariant} />
        ) : o.type === 'summary' ? (
          <SummaryView title={o.title} summary={o.summary} asOfMs={asOfMs} senderOf={senderOf} />
        ) : o.type === 'query' ? (
          <TargetsView title={o.title} targets={o.targets} senderOf={senderOf} />
        ) : o.type === 'awaiting' ? (
          <AwaitingView title={o.title} items={o.items} />
        ) : null}
      </div>
    </section>
  );
}

// ── 회신 초안 ──

function DraftView({ runId, title, draft, replyVariant }: { runId: number; title: string; draft: AgentDraft; replyVariant: 'primary' | 'secondary' }) {
  const navigate = useNavigate();
  const { drafts } = useAgentViewer();
  const text = drafts.get(runId) ?? draft.text;
  const [copied, setCopied] = useState('');
  const inputId = useId();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied('복사했습니다');
    } catch {
      setCopied('복사하지 못했습니다. 글자를 직접 선택하여 복사해 주십시오');
    }
  };

  return (
    <div className={styles.section}>
      <h3 className={styles.title}>{title}</h3>
      <dl className={styles.meta}>
        <div>
          <dt>받는 사람</dt>
          <dd>{draft.to}</dd>
        </div>
        <div>
          <dt>제목</dt>
          <dd>{draft.subject}</dd>
        </div>
      </dl>
      <label htmlFor={inputId} className={styles.label}>
        초안
      </label>
      <textarea
        id={inputId}
        className={styles.draft}
        value={text}
        onChange={(e) => {
          setCopied('');
          agentViewer.setDraft(runId, e.target.value);
        }}
      />
      <p className={styles.hint}>초안은 발송되지 않습니다. 수정한 내용은 화면을 옮겨도 유지되며, 발송은 답장 화면에서 진행합니다.</p>
      <div className={styles.actions}>
        <span className={styles.copied} aria-hidden="true">
          {copied}
        </span>
        <Button size="sm" onClick={() => void copy()}>
          <Copy size={16} aria-hidden="true" />
          복사
        </Button>
        <Button size="sm" variant={replyVariant} onClick={() => void navigate(replyDraftPath(draft.mailId, text))}>
          답장 화면에서 열기
        </Button>
      </div>
      <LiveRegion>{copied}</LiveRegion>
    </div>
  );
}

// ── 오늘 요약 ──

function SummaryView({ title, summary, asOfMs, senderOf }: { title: string; summary: AgentSummary; asOfMs: number; senderOf: SenderOf }) {
  const openMail = useOpenMail('agent');
  return (
    <div className={styles.section}>
      <h3 className={styles.title}>{title}</h3>
      {summary.hint && <p className={styles.hint}>{summary.hint}</p>}
      {summary.text && <p className={styles.briefing}>{summary.text}</p>}
      {summary.refreshing && (
        <p className={styles.refreshing}>
          <Spinner size={16} />
          새로 정리 중
        </p>
      )}
      {summary.items.length > 0 && (
        <ul className={styles.rows} aria-label="업무">
          {summary.items.map((i) => {
            const due = dueOf(i, asOfMs);
            const sender = senderOf(i.mailId);
            return (
              <li key={i.taskId}>
                <RowButton mailId={i.mailId} onOpen={openMail}>
                  <DueLabel kind={due.kind} text={due.text} srText={due.full ?? undefined} />
                  <span className={styles.rowText}>
                    {i.text}
                    {sender && <span className={styles.sub}> · {sender}</span>}
                  </span>
                </RowButton>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── 업무 목록(T02) · 답장 없는 메일(T06) ──

function TargetsView({ title, targets, senderOf }: { title: string; targets: AgentTarget[]; senderOf: SenderOf }) {
  const openMail = useOpenMail('agent');
  return (
    <div className={styles.section}>
      <h3 className={styles.title}>{title}</h3>
      <ul className={styles.rows} aria-label="업무">
        {targets.map((t) => {
          const sender = senderOf(t.mailId);
          const status = targetStatusText(t);
          return (
            <li key={t.id}>
              <RowButton mailId={t.mailId} onOpen={openMail}>
                <span className={styles.rowText}>
                  {t.text}
                  {sender && <span className={styles.sub}> · {sender}</span>}
                  {status && <span className={styles.sub}> · {status}</span>}
                </span>
              </RowButton>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AwaitingView({ title, items }: { title: string; items: Awaiting[] }) {
  const openMail = useOpenMail('agent');
  return (
    <div className={styles.section}>
      <h3 className={styles.title}>{title}</h3>
      <ul className={styles.rows} aria-label="메일">
        {items.map((a) => (
          <li key={a.mailId}>
            <RowButton mailId={a.mailId} onOpen={openMail}>
              <span className={styles.days}>{a.days}일째</span>
              <span className={styles.rowText}>
                {a.subject}
                <span className={styles.sub}> · {a.to}</span>
              </span>
            </RowButton>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RowButton({ mailId, onOpen, children }: { mailId: MailId; onOpen: (id: MailId) => void; children: ReactNode }) {
  return (
    <button type="button" className={styles.row} onClick={() => onOpen(mailId)}>
      {children}
      <ChevronRight size={16} aria-hidden="true" className={styles.chevron} />
    </button>
  );
}
