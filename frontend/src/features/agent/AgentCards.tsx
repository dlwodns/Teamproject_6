// 에이전트 대화 안 카드 (components.md 4.4 · wireframe 13-4). 모두 대화 흐름 안에 둔다(모달 아님).
// 제목 · 대상은 서버 결과(AgentResult) 그대로 보인다. 보낸 사람은 원자료(대시보드 캐시)에서 메일 id로 찾아 붙인다(senderOf).
// - ConfirmCard: 동사 질문 제목 + 체크 목록(풀어서 뺄 수 있음) + [취소] [N건 완료 처리]. 미리 고른 버튼 없음, 뜨면 카드로 포커스
// - ResultCard: 과거형 제목 + 대상 + [실행 취소](계속 남고, 누르면 '취소했습니다') + '어떻게 해석했나요'(접힘, 서버 notes)
// - QueryCard(T02) · NoticeCard · UnsupportedCard
// - FE 제안(모의만): SummaryCard(T01) · AwaitingCard(T06) · DraftCard(T07)
// - ResultLinkCard(FE-15): 에이전트 화면에서 위 결과를 대신하는 짧은 카드('초안 1건 · 열기')
// 포커스를 받는 카드는 tabIndex=-1 + 제목 id로 이름을 붙인다(agentSession의 focus 요청이 id로 찾는다).
import { useId, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import type { AgentDraft, AgentMail, AgentPerson, AgentSummary, AgentTarget } from '../../api/contract.ts';
import type { Awaiting, MailId, TaskId } from '../../api/types.ts';
import { Button, Check, Checkbox, Collapsible, DueLabel, VisuallyHidden } from '../../ui/index.ts';
import { confirmLabel, dueOf, formatMdhm, replyDraftPath, targetStatusText, UNDO_BLOCKED_TEXT } from './agentText.ts';
import styles from './AgentCards.module.css';
import type { UndoState } from './agentSession.ts';
import { ExampleList } from './ExampleList.tsx';

interface CardProps {
  id?: string;
  title: ReactNode;
  variant?: 'confirm' | 'muted' | 'current';
  children?: ReactNode;
}

function AgentCard({ id, title, variant, children }: CardProps) {
  const titleId = useId();
  return (
    <section id={id} className={styles.card} data-variant={variant} tabIndex={id ? -1 : undefined} aria-labelledby={titleId}>
      <h3 id={titleId} className={styles.title}>
        {title}
      </h3>
      {children}
    </section>
  );
}

// ── 확인 카드 ──

export type SenderOf = (mailId: MailId) => string | null;

interface ConfirmProps {
  id: string;
  title: string;
  action: string | null;
  targets: AgentTarget[];
  senderOf: SenderOf;
  onConfirm: (ids: TaskId[]) => void;
  onCancel: () => void;
}

export function ConfirmCard({ id, title, action, targets, senderOf, onConfirm, onCancel }: ConfirmProps) {
  const [checked, setChecked] = useState<ReadonlySet<TaskId>>(() => new Set(targets.map((t) => t.id)));
  const n = checked.size;
  const toggle = (taskId: TaskId, on: boolean) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (on) next.add(taskId);
      else next.delete(taskId);
      return next;
    });
  const senders = targets.map((t) => senderOf(t.mailId));
  const showSender = new Set(senders).size > 1;
  return (
    <AgentCard id={id} title={title} variant="confirm">
      <ul className={styles.list}>
        {targets.map((t, i) => (
          <li key={t.id}>
            <Checkbox
              checked={checked.has(t.id)}
              onCheckedChange={(on) => toggle(t.id, on)}
              label={
                <span className={styles.itemText}>
                  {t.text}
                  {showSender && senders[i] && <span className={styles.sub}> · {senders[i]}</span>}
                </span>
              }
            />
          </li>
        ))}
      </ul>
      <p className={styles.hint}>제외할 업무는 체크를 해제해 주십시오. 변경 후에도 되돌릴 수 있습니다.</p>
      <div className={styles.actions}>
        <Button size="sm" onClick={onCancel}>
          취소
        </Button>
        <Button
          size="sm"
          variant="primary"
          disabled={n === 0}
          onClick={() => onConfirm(targets.filter((t) => checked.has(t.id)).map((t) => t.id))}
        >
          {confirmLabel(action, n)}
        </Button>
      </div>
    </AgentCard>
  );
}

// ── 결과 카드 ──

interface ResultProps {
  id: string;
  title: string;
  targets: AgentTarget[];
  canUndo: boolean;
  undo: UndoState;
  notes: string[];
  onUndo: () => void;
}

export function ResultCard({ id, title, targets, canUndo, undo, notes, onUndo }: ResultProps) {
  const undone = undo === 'done';
  return (
    <AgentCard id={id} title={title} variant={undone ? 'muted' : undefined}>
      {targets.length > 0 && (
        <ul className={styles.list}>
          {targets.map((t) => (
            <li key={t.id} className={styles.done}>
              <Check size={16} aria-hidden="true" className={styles.check} />
              <span className={styles.itemText}>{t.text}</span>
            </li>
          ))}
        </ul>
      )}
      {notes.length > 0 && (
        <Collapsible label="요청 해석 내용">
          {notes.map((line) => (
            <p key={line} className={styles.why}>
              {line}
            </p>
          ))}
        </Collapsible>
      )}
      {undo === 'error' && <p className={styles.hint}>취소하지 못했습니다. 다시 시도해 주십시오.</p>}
      {undo === 'blocked' && <p className={styles.hint}>{UNDO_BLOCKED_TEXT}</p>}
      {canUndo && undo !== 'blocked' && (
        <div className={styles.actions}>
          <Button size="sm" aria-disabled={undone || undo === 'pending' || undefined} onClick={() => !undone && undo !== 'pending' && onUndo()}>
            {undone ? '취소했습니다' : undo === 'pending' ? '되돌리는 중' : '실행 취소'}
          </Button>
        </div>
      )}
    </AgentCard>
  );
}

// ── 미처리 조회(T02) ──

interface QueryProps {
  id: string;
  title: string;
  targets: AgentTarget[];
  notes: string[];
  senderOf: SenderOf;
  /** 11-18 메일 찾기 · 요약 · 내용 질문이 실은 메일. 누르면 메일을 연다 */
  mails?: AgentMail[];
  /** 11-18 근거 문장 · 일정 · 요청한 것. 접지 않고 보인다 */
  lines?: string[];
  onOpenMail?: (mailId: MailId) => void;
}

export function QueryCard({ id, title, targets, notes, senderOf, mails = [], lines = [], onOpenMail }: QueryProps) {
  return (
    <AgentCard id={id} title={title}>
      {lines.map((line, i) => (
        <p key={`${i}-${line}`} className={styles.itemText}>
          {line}
        </p>
      ))}
      {mails.length > 0 && (
        <ul className={styles.list} aria-label={`메일 ${mails.length}통`}>
          {mails.map((m) => (
            <li key={m.mailId} className={styles.row}>
              {onOpenMail ? (
                <Button variant="ghost" size="sm" onClick={() => onOpenMail(m.mailId)}>
                  {m.subject}
                </Button>
              ) : (
                <span className={styles.itemText}>{m.subject}</span>
              )}
              <span className={styles.sub}>
                {' '}· {m.direction === 'sent' ? `받는 사람 ${m.who}` : m.who}
                {m.atMs !== null && ` · ${formatMdhm(m.atMs)}`}
              </span>
            </li>
          ))}
        </ul>
      )}
      {targets.length > 0 && (
        <ul className={styles.list}>
          {targets.map((t) => {
            const sender = senderOf(t.mailId);
            const status = targetStatusText(t);
            return (
              <li key={t.id} className={styles.row}>
                <span className={styles.itemText}>
                  {t.text}
                  {sender && <span className={styles.sub}> · {sender}</span>}
                  {status && <span className={styles.sub}> · {status}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {notes.length > 0 && (
        <Collapsible label="요청 해석 내용">
          {notes.map((line) => (
            <p key={line} className={styles.why}>
              {line}
            </p>
          ))}
        </Collapsible>
      )}
    </AgentCard>
  );
}

// ── 사람 조회(T17, 11-17) ──
// 누구인지(직급 · 상급자 · 맡은 일 · 소속) → 보낸 메일 → 그 메일의 업무(끝난 것 포함). 맡은 일 · 소속은 메일 내용 분석을 켰을 때만 온다.

export function PersonCard({ id, title, person, targets, notes, onOpenMail }: { id: string; title: string; person: AgentPerson; targets: AgentTarget[]; notes: string[]; onOpenMail: (mailId: MailId) => void }) {
  const who = [person.name ?? person.email, person.position].filter(Boolean).join(' ');
  const marks = [person.isSuperior && '상급자', person.isFavorite && '즐겨찾기'].filter(Boolean).join(' · ');
  return (
    <AgentCard id={id} title={title}>
      <p className={styles.itemText}>
        {who}
        <span className={styles.sub}> · {person.email}{marks && ` · ${marks}`}</span>
      </p>
      {person.facts.length > 0 && (
        <ul className={styles.list} aria-label="메일에서 확인한 정보">
          {person.facts.map((f) => (
            <li key={f.label} className={styles.row}>
              <span className={styles.itemText}>
                {f.label}: {f.value}
                {f.evidence && <span className={styles.sub}> · “{f.evidence}”</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {person.mails.length > 0 && (
        <ul className={styles.list} aria-label={`보낸 메일 ${person.mailTotal}건`}>
          {person.mails.map((m) => (
            <li key={m.mailId} className={styles.row}>
              <Button variant="ghost" size="sm" onClick={() => onOpenMail(m.mailId)}>
                {m.subject}
              </Button>
              {m.receivedAtMs !== null && <span className={styles.sub}> · {formatMdhm(m.receivedAtMs)}</span>}
            </li>
          ))}
        </ul>
      )}
      {targets.length > 0 && (
        <ul className={styles.list} aria-label={`업무 ${targets.length}건`}>
          {targets.map((t) => {
            const status = targetStatusText(t);
            return (
              <li key={t.id} className={styles.row}>
                <span className={styles.itemText}>
                  {t.text}
                  {status && <span className={styles.sub}> · {status}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {notes.length > 0 && notes.map((line) => (
        <p key={line} className={styles.why}>
          {line}
        </p>
      ))}
    </AgentCard>
  );
}

// ── 오늘 요약(T01, FE 제안) ──

interface SummaryProps {
  id: string;
  title: string;
  summary: AgentSummary;
  asOfMs: number;
  senderOf: SenderOf;
}

export function SummaryCard({ id, title, summary, asOfMs, senderOf }: SummaryProps) {
  return (
    <AgentCard id={id} title={title}>
      {summary.items.length > 0 && (
        <ul className={styles.list}>
          {summary.items.map((i) => {
            const due = dueOf(i, asOfMs);
            const sender = senderOf(i.mailId);
            return (
              <li key={i.taskId} className={styles.row}>
                <DueLabel kind={due.kind} text={due.text} srText={due.full ?? undefined} />
                <span className={styles.itemText}>
                  {i.text}
                  {sender && <span className={styles.sub}> · {sender}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {summary.hint && <p className={styles.hint}>{summary.hint}</p>}
    </AgentCard>
  );
}

// ── 답장 없는 메일(T06, FE 제안) ──

export function AwaitingCard({ id, title, items }: { id: string; title: string; items: Awaiting[] }) {
  return (
    <AgentCard id={id} title={title}>
      {items.length > 0 && (
        <ul className={styles.list}>
          {items.map((a) => (
            <li key={a.mailId} className={styles.row}>
              <span className={styles.days}>{a.days}일째</span>
              <span className={styles.itemText}>
                {a.subject}
                <span className={styles.sub}> · {a.to}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </AgentCard>
  );
}

// ── 회신 초안(T07, FE 제안) ──

export function DraftCard({ id, title, draft }: { id: string; title: string; draft: AgentDraft }) {
  const navigate = useNavigate();
  const { mailId, subject, to, text } = draft;
  return (
    <AgentCard id={id} title={title}>
      <p className={styles.sub}>
        받는 사람 {to} · {subject}
      </p>
      <blockquote className={styles.preview}>
        <VisuallyHidden>초안: </VisuallyHidden>
        {text}
      </blockquote>
      <p className={styles.hint}>초안은 발송되지 않습니다. 답장 화면에서 검토 후 직접 발송해 주십시오.</p>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" onClick={() => navigate(replyDraftPath(mailId, text))}>
          답장 화면에서 열기
        </Button>
      </div>
    </AgentCard>
  );
}

// ── 결과물 짧은 카드(FE-15, 에이전트 화면) ──
// 에이전트 화면 대화에서는 길거나 다시 볼 결과를 이 카드로만 보이고, [열기]로 오른쪽 결과물 칸에 연다. 지금 열린 결과는 진한 테두리.

interface ResultLinkProps {
  id: string;
  title: string;
  /** '초안 1건' · '요약' · '업무 3건' */
  label: string;
  open: boolean;
  onOpen: () => void;
}

export function ResultLinkCard({ id, title, label, open, onOpen }: ResultLinkProps) {
  return (
    <AgentCard id={id} title={title} variant={open ? 'current' : undefined}>
      <div className={styles.linkRow}>
        <span className={styles.sub}>{label}</span>
        <Button size="sm" aria-pressed={open} onClick={onOpen}>
          {open ? '보는 중' : '열기'}
        </Button>
      </div>
    </AgentCard>
  );
}

// ── 알림 · 실패 · 지원 외 ──

export function NoticeCard({ id, title, hint }: { id?: string; title: string; hint: string | null }) {
  return (
    <AgentCard id={id} title={title}>
      {hint && <p className={styles.hint}>{hint}</p>}
    </AgentCard>
  );
}

interface UnsupportedProps {
  title: string;
  hint: string;
  examples: readonly string[];
  busy: boolean;
  onRun: (text: string) => void;
  /** 11-19 되묻기의 후보 업무(T16 여러 건). 고르면 그 업무로 같은 말을 다시 보낸다 */
  choices?: AgentTarget[];
  senderOf?: SenderOf;
  onPick?: (taskId: TaskId) => void;
}

export function UnsupportedCard({ title, hint, examples, busy, onRun, choices = [], senderOf, onPick }: UnsupportedProps) {
  if (choices.length > 0 && onPick) {
    return (
      <AgentCard title={title}>
        <ul className={styles.list} aria-label={`고를 업무 ${choices.length}건`}>
          {choices.map((t) => {
            const sender = senderOf?.(t.mailId);
            const status = targetStatusText(t);
            return (
              <li key={t.id} className={styles.row}>
                <Button variant="ghost" size="sm" disabled={busy} onClick={() => onPick(t.id)}>
                  {t.text}
                </Button>
                <span className={styles.sub}>
                  {sender && ` · ${sender}`}
                  {status && ` · ${status}`}
                </span>
              </li>
            );
          })}
        </ul>
      </AgentCard>
    );
  }
  return (
    <AgentCard title={title}>
      <p className={styles.hint}>{hint}</p>
      <ExampleList examples={examples} busy={busy} onRun={onRun} label="요청 예시" />
    </AgentCard>
  );
}
