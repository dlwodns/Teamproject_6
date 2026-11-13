// 답장 쓰기 (components.md 4.3 · wireframe 13-5 · UX-D5 · UX-D14). 읽기 자리를 대신한다.
// 위에서 아래: [보내기] · 보낸 사람 ▾ … [삭제] / 받는 사람(고정) / 제목 RE: … / 템플릿 ▾ / 내용 / 미리보기.
// 참조 · 숨은 참조 · 예약 보내기 · 엑사원으로 다듬기는 아직 없는 기능이라 그리지 않는다(D50 결정 7 — 가짜 버튼 금지).
// 쓰던 답장이 있으면 [삭제] · 다른 화면으로 가기 · 창 닫기 전에 '버릴까요?'를 묻는다(React Router useBlocker).
import { useEffect, useId, useRef, useState } from 'react';
import { useBeforeUnload, useBlocker } from 'react-router';
import type { ReplyTemplate } from '../../api/contract.ts';
import { NotAvailableError } from '../../api/errors.ts';
import { useSendReply } from '../../api/queries.ts';
import type { Mail } from '../../api/types.ts';
import { Button, Select, Sheet, useToast } from '../../ui/index.ts';
import { hasDraft, recipientName, renderReply, replySubject, replyText } from './compose.ts';
import styles from './Compose.module.css';
import { accountLabel, type MailContext } from './mailboxes.ts';

interface Props {
  mail: Mail;
  ctx: MailContext;
  /** 메일에 나온 계정(보낸 사람 고르기). 비면 보낸 사람 칸을 숨긴다 */
  accounts: string[];
  /** 설정의 템플릿. undefined = 서버가 안 보냄(템플릿 칸을 숨기고 쓴 말만 보낸다) */
  templates: ReplyTemplate[] | undefined;
  /** 내 이름({발신자명}). 모르면 null */
  me: string | null;
  /** 내용 칸에 미리 넣을 글(주소 ?draft=) */
  initialContent: string;
  /** 모의 데이터면 '시연 모드 · 실제로 보내지 않음'을 보인다 */
  demo: boolean;
  /** 쓰기를 닫는다(메일 보기로). 버릴지 묻기는 이 부품이 먼저 한다 */
  onClose: () => void;
  /** 보내기가 끝났다(보냄 ✓ 뒤). 완료 확인은 부른 쪽이 한다 */
  onSent: () => void;
}

const DONE_MS = 700; // 보냄 ✓을 보이는 시간(components.md 3절 Button)

export function Compose({ mail, ctx, accounts, templates, me, initialContent, demo, onClose, onSent }: Props) {
  const ids = useId();
  const toast = useToast();
  const send = useSendReply();
  const [content, setContent] = useState(initialContent);
  const [account, setAccount] = useState<string | null>(mail.account && accounts.includes(mail.account) ? mail.account : (accounts[0] ?? null));
  const [templateKey, setTemplateKey] = useState<string | null>(templates?.[0]?.key ?? null);
  const [phase, setPhase] = useState<'idle' | 'sending' | 'done'>('idle');
  const [unavailable, setUnavailable] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const contentRef = useRef<HTMLTextAreaElement>(null);
  /** 보냈거나 버리기로 한 뒤에는 떠나도 묻지 않는다(이동 막기 함수가 이동하는 순간에 읽는다) */
  const leaveOk = useRef(false);
  const dirty = hasDraft(content) && phase !== 'done';

  // 템플릿이 늦게 도착하면 첫 템플릿을 고른다
  useEffect(() => {
    if (templateKey === null && templates?.[0]) setTemplateKey(templates[0].key);
  }, [templates, templateKey]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (leaveOk.current || !dirty) return false;
    return currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search;
  });
  useBeforeUnload((e) => {
    if (dirty && !leaveOk.current) e.preventDefault();
  });

  const template = templates?.find((t) => t.key === templateKey) ?? null;
  const toLine = recipientName(ctx.contactsByEmail.get(mail.sender), mail.sender);
  const subject = replySubject(mail.subject);
  const parts = renderReply(template, { recipient: toLine, sender: me, subject: mail.subject }, content);

  const discard = () => {
    if (hasDraft(content)) setConfirmDiscard(true);
    else {
      leaveOk.current = true;
      onClose();
    }
  };

  const submit = async () => {
    if (phase !== 'idle') return;
    if (!hasDraft(content)) {
      setEmpty(true);
      contentRef.current?.focus();
      return;
    }
    setPhase('sending');
    try {
      await send.mutateAsync({ id: mail.id, draft: { account, subject, content: replyText(parts), templateKey: template?.key ?? null } });
    } catch (e) {
      setPhase('idle');
      if (e instanceof NotAvailableError) {
        setUnavailable(true);
        toast.show({ kind: 'error', title: '보내지 못함', description: '서버에 답장 보내기가 아직 없어요' });
      } else {
        toast.show({ kind: 'error', title: '보내지 못함', actionLabel: '다시 시도', onAction: () => void submit() });
      }
      return;
    }
    setPhase('done');
    window.setTimeout(() => {
      leaveOk.current = true;
      onSent();
    }, DONE_MS);
  };

  const accountOptions = accounts.map((a) => ({ value: a, label: me ? `${me} · ${accountLabel(a)}` : accountLabel(a) }));
  const templateOptions = (templates ?? []).map((t) => ({ value: t.key, label: t.name }));

  return (
    <section className={styles.compose} aria-labelledby={`${ids}-title`}>
      <h2 id={`${ids}-title`} className={styles.title}>
        답장 · <span lang={mail.lang ?? undefined}>{mail.subject}</span>
      </h2>

      <div className={styles.bar}>
        <Button
          variant="primary"
          loading={phase === 'sending'}
          done={phase === 'done'}
          loadingText="보내는 중"
          doneText="보냈어요"
          onClick={() => void submit()}
        >
          보내기
        </Button>
        {(demo || unavailable) && <span className={styles.demo}>시연 모드 · 실제로 보내지 않음</span>}
        {accountOptions.length > 0 && (
          <div className={styles.from}>
            <Select label="보낸 사람" options={accountOptions} value={account} onValueChange={setAccount} />
          </div>
        )}
        <Button variant="ghost" size="sm" className={styles.discard} onClick={discard}>
          삭제
        </Button>
      </div>

      <div className={styles.row}>
        <span className={styles.key}>받는 사람</span>
        <span className={styles.rcpt}>
          {toLine} &lt;{mail.sender}&gt;
        </span>
        <span className={styles.hint}>고정</span>
      </div>
      <div className={styles.row}>
        <span className={styles.key}>제목</span>
        <span className={styles.subject} lang={mail.lang ?? undefined}>
          {subject}
        </span>
      </div>

      {templateOptions.length > 0 && (
        <div className={styles.field}>
          <Select label="템플릿" options={templateOptions} value={templateKey} onValueChange={setTemplateKey} />
        </div>
      )}

      <div className={styles.field}>
        <label className={styles.label} htmlFor={`${ids}-content`}>
          내용
        </label>
        <textarea
          ref={contentRef}
          id={`${ids}-content`}
          className={styles.textarea}
          value={content}
          rows={4}
          placeholder="하고 싶은 말만 쓰기"
          aria-invalid={empty || undefined}
          aria-describedby={empty ? `${ids}-empty` : undefined}
          onChange={(e) => {
            setContent(e.target.value);
            if (empty) setEmpty(false);
          }}
        />
        {empty && (
          <p id={`${ids}-empty`} className={styles.error}>
            보낼 내용 없음
          </p>
        )}
      </div>

      <div className={styles.field}>
        <span className={styles.label} id={`${ids}-preview`}>
          미리보기
        </span>
        <div className={styles.preview} aria-labelledby={`${ids}-preview`} role="group">
          <span className={styles.previewSubject}>{subject}</span>
          {parts.before}
          <span className={styles.user}>{parts.content || '(내용)'}</span>
          {parts.after}
        </div>
      </div>

      <Sheet
        open={confirmDiscard || blocker.state === 'blocked'}
        title="버릴까요?"
        onYes={() => {
          leaveOk.current = true;
          setConfirmDiscard(false);
          if (blocker.state === 'blocked') blocker.proceed();
          else onClose();
        }}
        onNo={() => {
          setConfirmDiscard(false);
          if (blocker.state === 'blocked') blocker.reset();
        }}
      />
    </section>
  );
}
