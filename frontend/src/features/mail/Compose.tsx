// 답장 쓰기 (components.md 4.3 · wireframe 13-5 · UX-D5 · UX-D14). 읽기 자리를 대신한다.
// 11-15 왼쪽 위 → 오른쪽 아래 한 흐름: 보낸 사람 ▾ / 받는 사람 / 제목 RE: … / 템플릿 ▾ / 내용(오른쪽 아래 ✎ · 🎙) / 미리보기 / [삭제] [보내기].
// 참조 · 숨은 참조 · 예약 보내기는 아직 없는 기능이라 그리지 않는다(D50 결정 7 — 가짜 버튼 금지).
// 11-15: 내용 칸 오른쪽 아래 아이콘 — 격식체로 다시 쓰기(보내지 않음) · 음성 입력(브라우저 받아쓰기, 지원할 때만).
// 쓰던 답장이 있으면 [삭제] · 다른 화면으로 가기 · 창 닫기 전에 '버릴까요?'를 묻는다(React Router useBlocker).
import { useEffect, useId, useRef, useState } from 'react';
import { useBeforeUnload, useBlocker } from 'react-router';
import type { ReplyTemplate } from '../../api/contract.ts';
import { HttpError, NotAvailableError } from '../../api/errors.ts';
import { usePolishReply, useSendReply } from '../../api/queries.ts';
import type { Mail } from '../../api/types.ts';
import { Button, IconButton, Mic, PenLine, Select, Sheet, Spinner, useToast } from '../../ui/index.ts';
import { useVoiceInput } from '../voice/useVoiceInput.ts';
import { voiceErrorText } from '../voice/voiceText.ts';
import { canApplyPolish, hasDraft, recipientName, renderReply, replySubject, replyText, sendFailure } from './compose.ts';
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
  const polish = usePolishReply();
  const [content, setContent] = useState(initialContent);
  // 음성 입력(FE-8 · 캐치봇 입력과 같은 부품): 들은 말을 쓰던 글 뒤에 붙인다. 직접 고치거나 다듬기 · 보내기를 누르면 듣기를 끊는다
  const contentNow = useRef(content);
  contentNow.current = content;
  const voice = useVoiceInput({ getText: () => contentNow.current, setText: setContent });
  useEffect(() => {
    if (!voice.error) return;
    toast.show({ kind: 'error', title: voiceErrorText(voice.error) });
    voice.clearError();
  }, [voice, toast]);
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
    voice.abort();
    setPhase('sending');
    try {
      await send.mutateAsync({ id: mail.id, draft: { account, subject, content: replyText(parts), templateKey: template?.key ?? null } });
    } catch (e) {
      setPhase('idle');
      if (e instanceof NotAvailableError) {
        setUnavailable(true);
        toast.show({ kind: 'error', title: '보내지 못했습니다', description: '서버에 답장 보내기 기능이 아직 없습니다' });
      } else {
        const f = sendFailure(e instanceof HttpError ? e.status : 'network');
        toast.show({ kind: 'error', title: f.title, description: f.description, ...(f.retry ? { actionLabel: '다시 시도', onAction: () => void submit() } : {}) });
      }
      return;
    }
    setPhase('done');
    window.setTimeout(() => {
      leaveOk.current = true;
      onSent();
    }, DONE_MS);
  };

  const runPolish = () => {
    if (!hasDraft(content) || polish.isPending) {
      if (!hasDraft(content)) {
        setEmpty(true);
        contentRef.current?.focus();
      }
      return;
    }
    voice.abort();
    const before = content;
    polish.mutate(
      { id: mail.id, text: content },
      {
        onSuccess: (r) => {
          if (r.source === 'none') {
            toast.show({ kind: 'info', title: '격식체 변환을 사용할 수 없어 작성 내용을 유지했습니다' });
            return;
          }
          if (!r.changed) {
            toast.show({ kind: 'info', title: '수정할 부분이 없습니다' });
            return;
          }
          // 기다리는 동안 쓴 글은 지키고 결과는 버린다. textarea 값이 지금 화면의 글이다.
          if (!canApplyPolish(before, contentRef.current?.value ?? before)) {
            toast.show({ kind: 'info', title: '작성 내용이 바뀌어 격식체 변환 결과를 적용하지 않았습니다' });
            return;
          }
          setContent(r.text);
          toast.show({ kind: 'info', title: '격식체로 다시 썼습니다', actionLabel: '되돌리기', onAction: () => setContent(before) });
        },
        onError: () => toast.show({ kind: 'error', title: '격식체로 바꾸지 못했습니다', description: '작성 내용은 그대로 유지됩니다' }),
      },
    );
  };

  const accountOptions = accounts.map((a) => ({ value: a, label: me ? `${me} · ${accountLabel(a)}` : accountLabel(a) }));
  const templateOptions = (templates ?? []).map((t) => ({ value: t.key, label: t.name }));

  return (
    <section className={styles.compose} aria-labelledby={`${ids}-title`}>
      <h2 id={`${ids}-title`} className={styles.title}>
        답장 · <span lang={mail.lang ?? undefined}>{mail.subject}</span>
      </h2>

      {accountOptions.length > 0 && (
        <div className={styles.from}>
          <Select label="보낸 사람" options={accountOptions} value={account} onValueChange={setAccount} />
        </div>
      )}
      <div className={styles.row}>
        <span className={styles.key}>받는 사람</span>
        <span className={styles.rcpt}>
          {toLine} &lt;{mail.sender}&gt;
        </span>
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
        {/* 입력칸 오른쪽 아래: 격식체로 다시 쓰기 · 음성 입력(아이콘만, 이름은 말풍선 · 화면 읽기) */}
        <div className={styles.contentBox}>
          <textarea
            ref={contentRef}
            id={`${ids}-content`}
            className={styles.textarea}
            value={content}
            rows={5}
            placeholder="전할 내용을 자유롭게 쓰거나 말씀하십시오. 예: 금요일까지 수정본 보낼게요"
            aria-invalid={empty || undefined}
            aria-describedby={empty ? `${ids}-empty` : undefined}
            onChange={(e) => {
              voice.abort();
              setContent(e.target.value);
              if (empty) setEmpty(false);
            }}
          />
          <div className={styles.tools}>
            <IconButton
              label="격식체로 다시 쓰기"
              icon={polish.isPending ? <Spinner size={16} /> : <PenLine size={20} aria-hidden="true" />}
              aria-busy={polish.isPending || undefined}
              aria-disabled={polish.isPending || undefined}
              onClick={runPolish}
            />
            {voice.supported && (
              <IconButton
                label={voice.listening ? '음성 입력 중지' : '음성 입력'}
                icon={<Mic size={20} aria-hidden="true" />}
                aria-pressed={voice.listening}
                data-on={voice.listening ? '' : undefined}
                className={styles.mic}
                onClick={voice.toggle}
              />
            )}
          </div>
        </div>
        {empty && (
          <p id={`${ids}-empty`} className={styles.error}>
            작성된 내용이 없습니다
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

      {/* 다 쓰고 확인한 자리(맨 아래 오른쪽)에서 보낸다 */}
      <div className={styles.foot}>
        {(demo || unavailable) && <span className={styles.demo}>시연 모드 · 실제로 보내지 않음</span>}
        <Button variant="ghost" onClick={discard}>
          삭제
        </Button>
        <Button
          variant="primary"
          loading={phase === 'sending'}
          done={phase === 'done'}
          loadingText="보내는 중"
          doneText="보냈습니다"
          onClick={() => void submit()}
        >
          보내기
        </Button>
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
