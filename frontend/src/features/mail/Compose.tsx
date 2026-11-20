// 메일 쓰기 (components.md 4.3 · wireframe 13-5 · UX-D5 · UX-D14 · FE-18). 읽기 자리를 대신한다.
// 11-15 왼쪽 위 → 오른쪽 아래 한 흐름: 보낸 사람 ▾ / 받는 사람 / 참조 · 숨은 참조 / 제목 / 템플릿 ▾ / 내용(오른쪽 아래 ✎ · 🎙) / 미리보기 / [삭제] [보내기].
// FE-18 종류: 답장 · 전체 답장(받는 사람은 서버가 원 메일에서 정한다) · 전달(받는 사람을 쓴다) · 새 메일(받는 사람 · 제목을 쓴다).
// 템플릿은 답장 · 전체 답장에만({수신자명}이 원 메일 발신자). 격식체 다시 쓰기는 원 메일이 있을 때만(POST /mails/{id}/polish).
// BE-7 단계 2: [파일 첨부](합쳐 3MB 미만) · [예약 보내기](그 시각에 서버가 보냄, 토스트에서 취소) · 설정의 메일 서명을 글 끝에 붙인다.
// 쓰던 메일이 있으면 [삭제] · 다른 화면으로 가기 · 창 닫기 전에 '버릴까요?'를 묻는다(React Router useBlocker).
import { type Ref, useEffect, useId, useRef, useState } from 'react';
import { useBeforeUnload, useBlocker } from 'react-router';
import { isScheduled, type ComposeMode, type DraftAttachment, type MailAccount, type ReplyTemplate } from '../../api/contract.ts';
import { HttpError, NetworkError, NotAvailableError } from '../../api/errors.ts';
import { useCancelScheduled, usePolishReply, useSendReply } from '../../api/queries.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { fromKstLocal, toKstLocal } from '../../pages/settings/settingsModel.ts';
import type { Mail } from '../../api/types.ts';
import { Button, IconButton, Mic, PenLine, Select, Sheet, Spinner, useToast } from '../../ui/index.ts';
import { useVoiceInput } from '../voice/useVoiceInput.ts';
import { voiceErrorText } from '../voice/voiceText.ts';
import {
  attachTotal,
  canApplyPolish,
  forwardSubject,
  hasDraft,
  MAX_ATTACH_BYTES,
  parseAddresses,
  recipientName,
  renderReply,
  replySubject,
  replyText,
  sendFailure,
  validSendAt,
  withSignature,
} from './compose.ts';
import styles from './Compose.module.css';
import { accountLabel, type MailContext } from './mailboxes.ts';

interface Props {
  mode: ComposeMode;
  /** 원 메일. 새 메일이면 undefined */
  mail: Mail | undefined;
  ctx: MailContext;
  /** 답장 · 전달: 메일에 나온 계정(보낸 사람 고르기). 비면 보낸 사람 칸을 숨긴다 */
  accounts: string[];
  /** 새 메일: 보낼 수 있는 계정(GET /api/accounts). 비면 서버가 보낼 수 있는 첫 계정으로 */
  sendAccounts: MailAccount[];
  /** 설정의 템플릿. undefined = 서버가 안 보냄(템플릿 칸을 숨기고 쓴 말만 보낸다) */
  templates: ReplyTemplate[] | undefined;
  /** 내 이름({발신자명}). 모르면 null */
  me: string | null;
  /** 내용 칸에 미리 넣을 글(주소 ?draft=) */
  initialContent: string;
  /** 설정의 메일 서명(BE-7). 보낼 글 끝에 붙인다. 없으면 null */
  signature: string | null;
  /** 모의 데이터면 '시연 모드 · 실제로 보내지 않음'을 보인다 */
  demo: boolean;
  /** 쓰기를 닫는다(메일 보기로). 버릴지 묻기는 이 부품이 먼저 한다 */
  onClose: () => void;
  /** 보내기가 끝났다(보냄 ✓ 뒤). scheduled = 예약만 했다(아직 안 나감 — 완료 확인을 묻지 않는다) */
  onSent: (scheduled: boolean) => void;
}

const DONE_MS = 700; // 보냄 ✓을 보이는 시간(components.md 3절 Button)
const TITLES: Record<ComposeMode, string> = { reply: '답장', replyAll: '전체 답장', forward: '전달', new: '새 메일' };

type PickedFile = DraftAttachment & { size: number };

/** 파일 → base64(data: 주소의 쉼표 뒤) */
const readB64 = (f: File) =>
  new Promise<string>((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(',', 2)[1] ?? '');
    r.onerror = () => fail(r.error);
    r.readAsDataURL(f);
  });

export function Compose({ mode, mail, ctx, accounts, sendAccounts, templates, me, initialContent, signature, demo, onClose, onSent }: Props) {
  const ids = useId();
  const toast = useToast();
  const send = useSendReply();
  const cancelScheduled = useCancelScheduled();
  const polish = usePolishReply();
  const isReply = mode === 'reply' || mode === 'replyAll';
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
  const [account, setAccount] = useState<string | null>(mail?.account && accounts.includes(mail.account) ? mail.account : (accounts[0] ?? null));
  const [sendAccount, setSendAccount] = useState<string | null>(sendAccounts[0] ? String(sendAccounts[0].id) : null);
  const [templateKey, setTemplateKey] = useState<string | null>(isReply ? (templates?.[0]?.key ?? null) : null);
  const [to, setTo] = useState('');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [showCc, setShowCc] = useState(false);
  const [newSubject, setNewSubject] = useState('');
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [sendAt, setSendAt] = useState(''); // datetime-local 값(KST)
  const fileRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<'idle' | 'sending' | 'done'>('idle');
  const [unavailable, setUnavailable] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [badField, setBadField] = useState<'to' | 'cc' | 'bcc' | 'subject' | 'sendAt' | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const toRef = useRef<HTMLInputElement>(null);
  const ccRef = useRef<HTMLInputElement>(null);
  const bccRef = useRef<HTMLInputElement>(null);
  const subjectRef = useRef<HTMLInputElement>(null);
  /** 보냈거나 버리기로 한 뒤에는 떠나도 묻지 않는다(이동 막기 함수가 이동하는 순간에 읽는다) */
  const leaveOk = useRef(false);
  const written = [content, to, cc, bcc, newSubject].some(hasDraft) || files.length > 0;
  const scheduling = scheduleOpen && sendAt !== '';
  const dirty = written && phase !== 'done';

  // 템플릿이 늦게 도착하면 첫 템플릿을 고른다(답장만)
  useEffect(() => {
    if (isReply && templateKey === null && templates?.[0]) setTemplateKey(templates[0].key);
  }, [isReply, templates, templateKey]);
  // 계정 목록이 늦게 도착하면 첫 계정을 고른다(새 메일)
  useEffect(() => {
    if (sendAccount === null && sendAccounts[0]) setSendAccount(String(sendAccounts[0].id));
  }, [sendAccounts, sendAccount]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (leaveOk.current || !dirty) return false;
    return currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search;
  });
  useBeforeUnload((e) => {
    if (dirty && !leaveOk.current) e.preventDefault();
  });

  const template = isReply ? (templates?.find((t) => t.key === templateKey) ?? null) : null;
  const toLine = mail ? recipientName(ctx.contactsByEmail.get(mail.sender), mail.sender) : '';
  const subject = !mail ? newSubject.trim() : mode === 'forward' ? forwardSubject(mail.subject) : replySubject(mail.subject);
  const parts = renderReply(template, { recipient: toLine, sender: me, subject: mail?.subject ?? '' }, content);

  const discard = () => {
    if (written) setConfirmDiscard(true);
    else {
      leaveOk.current = true;
      onClose();
    }
  };

  const submit = async () => {
    if (phase !== 'idle') return;
    const toList = parseAddresses(to);
    const ccList = parseAddresses(cc);
    const bccList = parseAddresses(bcc);
    // 위에서 아래 순서로 첫 문제 칸에 포커스
    if (!isReply && (toList.ok.length === 0 || toList.bad.length > 0)) {
      setBadField('to');
      toRef.current?.focus();
      return;
    }
    if (ccList.bad.length > 0 || bccList.bad.length > 0) {
      const field = ccList.bad.length > 0 ? 'cc' : 'bcc';
      setBadField(field);
      setShowCc(true);
      window.setTimeout(() => (field === 'cc' ? ccRef : bccRef).current?.focus()); // 칸이 막 열렸을 수 있다
      return;
    }
    if (!mail && subject === '') {
      setBadField('subject');
      subjectRef.current?.focus();
      return;
    }
    const sendAtMs = scheduling ? fromKstLocal(sendAt) : null;
    if (sendAtMs !== null && !validSendAt(sendAtMs, Date.now())) {
      setBadField('sendAt');
      return;
    }
    setBadField(null);
    if (!hasDraft(content)) {
      setEmpty(true);
      contentRef.current?.focus();
      return;
    }
    voice.abort();
    setPhase('sending');
    let result;
    try {
      result = await send.mutateAsync({
        id: mail?.id ?? null,
        mode,
        accountId: sendAccount === null ? null : Number(sendAccount),
        draft: {
          account: mail ? account : null,
          subject,
          content: withSignature(replyText(parts), signature),
          templateKey: template?.key ?? null,
          ...(isReply ? {} : { to: toList.ok }),
          cc: ccList.ok,
          bcc: bccList.ok,
          attachments: files.map(({ name, contentType, contentB64 }) => ({ name, contentType, contentB64 })),
          sendAtMs,
        },
      });
    } catch (e) {
      setPhase('idle');
      if (e instanceof NotAvailableError && mode === 'new' && e.status === 404) {
        // 고른 계정으로 보낼 수 없음(서버 send_new 404) — 기능이 없는 것이 아니다
        toast.show({ kind: 'error', title: '보내지 못했습니다', description: '고른 계정으로 보낼 수 없습니다. 설정 > 메일 계정을 확인해 주세요' });
        return;
      }
      if (e instanceof NotAvailableError) {
        setUnavailable(true);
        toast.show({ kind: 'error', title: '보내지 못했습니다', description: `서버에 ${TITLES[mode]} 보내기 기능이 아직 없습니다` });
        return;
      }
      const f = sendFailure(e instanceof HttpError ? e.status : e instanceof NetworkError ? 'network' : 0);
      toast.show({ kind: 'error', title: f.title, description: f.description, ...(f.retry ? { actionLabel: '다시 시도', onAction: () => void submit() } : {}) });
      return;
    }
    setPhase('done');
    const scheduled = isScheduled(result);
    if (isScheduled(result)) {
      const id = result.scheduledId;
      toast.show({
        kind: 'undo',
        title: `${formatKstShort(result.sendAtMs)}에 보냅니다`,
        actionLabel: '예약 취소',
        onAction: () =>
          cancelScheduled.mutate(id, {
            onSuccess: () => toast.show({ kind: 'info', title: '예약을 취소했습니다' }),
            onError: () => toast.show({ kind: 'error', title: '예약을 취소하지 못했습니다' }),
          }),
      });
    }
    window.setTimeout(() => {
      leaveOk.current = true;
      onSent(scheduled);
    }, DONE_MS);
  };

  const pickFiles = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const picked = Array.from(list);
    if (attachTotal([...files, ...picked]) >= MAX_ATTACH_BYTES) {
      toast.show({ kind: 'error', title: '첨부는 합쳐 3MB 미만만 보낼 수 있습니다' });
      return;
    }
    try {
      const read = await Promise.all(
        picked.map(async (f) => ({ name: f.name, contentType: f.type || 'application/octet-stream', size: f.size, contentB64: await readB64(f) })),
      );
      setFiles((fs) => [...fs, ...read]);
    } catch {
      toast.show({ kind: 'error', title: '파일을 읽지 못했습니다' });
    }
  };

  const runPolish = () => {
    if (!mail) return;
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

  const accountOptions = mail
    ? accounts.map((a) => ({ value: a, label: me ? `${me} · ${accountLabel(a)}` : accountLabel(a) }))
    : sendAccounts.map((a) => ({ value: String(a.id), label: a.email }));
  const templateOptions = isReply ? (templates ?? []).map((t) => ({ value: t.key, label: t.name })) : [];

  /** 주소 입력 한 줄(받는 사람 · 참조 · 숨은 참조). 쉼표로 여러 명 */
  const addressRow = (key: string, label: string, value: string, set: (v: string) => void, ref?: Ref<HTMLInputElement>, invalid = false) => (
    <div className={styles.row}>
      <label className={styles.key} htmlFor={`${ids}-${key}`}>
        {label}
      </label>
      <input
        ref={ref}
        id={`${ids}-${key}`}
        className={styles.input}
        type="text"
        inputMode="email"
        autoComplete="email"
        spellCheck={false}
        value={value}
        placeholder="주소, 여러 명은 쉼표로"
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${ids}-addr-error` : undefined}
        onChange={(e) => {
          set(e.target.value);
          if (badField === 'to' || badField === 'cc' || badField === 'bcc') setBadField(null);
        }}
      />
    </div>
  );

  return (
    <section className={styles.compose} aria-labelledby={`${ids}-title`}>
      <h2 id={`${ids}-title`} className={styles.title}>
        {TITLES[mode]}
        {mail && (
          <>
            {' · '}
            <span lang={mail.lang ?? undefined}>{mail.subject}</span>
          </>
        )}
      </h2>

      {accountOptions.length > 0 && (
        <div className={styles.from}>
          <Select
            label="보낸 사람"
            options={accountOptions}
            value={mail ? account : sendAccount}
            onValueChange={mail ? setAccount : setSendAccount}
          />
        </div>
      )}
      {isReply && mail ? (
        <div className={styles.row}>
          <span className={styles.key}>받는 사람</span>
          <span className={styles.rcpt}>
            {toLine} &lt;{mail.sender}&gt;
            {mode === 'replyAll' && ' 외 원 메일을 받은 사람 모두'}
          </span>
        </div>
      ) : (
        addressRow('to', '받는 사람', to, setTo, toRef, badField === 'to')
      )}
      {showCc ? (
        <>
          {addressRow('cc', '참조', cc, setCc, ccRef, badField === 'cc')}
          {addressRow('bcc', '숨은 참조', bcc, setBcc, bccRef, badField === 'bcc')}
          {mode === 'replyAll' && <p className={styles.hint}>참조를 비우면 원 메일의 참조를 그대로 넣습니다</p>}
        </>
      ) : (
        <div className={styles.ccToggle}>
          <Button variant="ghost" size="sm" onClick={() => setShowCc(true)}>
            참조 · 숨은 참조
          </Button>
        </div>
      )}
      {(badField === 'to' || badField === 'cc' || badField === 'bcc') && (
        <p id={`${ids}-addr-error`} className={styles.error}>
          {badField === 'to' && parseAddresses(to).ok.length === 0 && parseAddresses(to).bad.length === 0
            ? '받는 사람을 적어 주세요'
            : '메일 주소 형식이 아닌 것이 있습니다'}
        </p>
      )}
      <div className={styles.row}>
        {mail ? (
          <>
            <span className={styles.key}>제목</span>
            <span className={styles.subject} lang={mail.lang ?? undefined}>
              {subject}
            </span>
          </>
        ) : (
          <>
            <label className={styles.key} htmlFor={`${ids}-subject`}>
              제목
            </label>
            <input
              ref={subjectRef}
              id={`${ids}-subject`}
              className={styles.input}
              value={newSubject}
              maxLength={255}
              aria-invalid={badField === 'subject' || undefined}
              aria-describedby={badField === 'subject' ? `${ids}-subject-error` : undefined}
              onChange={(e) => {
                setNewSubject(e.target.value);
                if (badField === 'subject') setBadField(null);
              }}
            />
          </>
        )}
      </div>
      {badField === 'subject' && (
        <p id={`${ids}-subject-error`} className={styles.error}>
          제목을 적어 주세요
        </p>
      )}

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
            {mail && (
              <IconButton
                label="격식체로 다시 쓰기"
                icon={polish.isPending ? <Spinner size={16} /> : <PenLine size={20} aria-hidden="true" />}
                aria-busy={polish.isPending || undefined}
                aria-disabled={polish.isPending || undefined}
                onClick={runPolish}
              />
            )}
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
          <span className={styles.previewSubject}>{subject || '(제목)'}</span>
          {parts.before}
          <span className={styles.user}>{parts.content || '(내용)'}</span>
          {parts.after}
          {signature?.trim() ? `\n\n${signature.trim()}` : ''}
        </div>
        {mode === 'forward' && <p className={styles.hint}>원 메일은 이 글 아래에 붙어 나갑니다</p>}
      </div>

      {/* 첨부 · 예약(BE-7 단계 2) */}
      <div className={styles.field}>
        <div className={styles.extras}>
          <input
            ref={fileRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              void pickFiles(e.target.files);
              e.target.value = ''; // 같은 파일을 다시 고를 수 있게
            }}
          />
          <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()}>
            파일 첨부
          </Button>
          <Button variant="ghost" size="sm" aria-pressed={scheduleOpen} onClick={() => setScheduleOpen((v) => !v)}>
            예약 보내기
          </Button>
          {scheduleOpen && (
            <label className={styles.when}>
              <span>보낼 시각</span>
              <input
                type="datetime-local"
                className={styles.input}
                value={sendAt}
                min={toKstLocal(Date.now() + 60_000)}
                aria-invalid={badField === 'sendAt' || undefined}
                onChange={(e) => {
                  setSendAt(e.target.value);
                  if (badField === 'sendAt') setBadField(null);
                }}
              />
            </label>
          )}
        </div>
        {badField === 'sendAt' && <p className={styles.error}>예약 시각은 지금부터 1분 뒤 이후여야 합니다</p>}
        {files.length > 0 && (
          <ul className={styles.files} aria-label="첨부 파일">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}>
                {f.name} <span className={styles.hint}>({Math.max(1, Math.round(f.size / 1024))}KB)</span>
                <Button variant="ghost" size="sm" aria-label={`${f.name} 빼기`} onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}>
                  빼기
                </Button>
              </li>
            ))}
          </ul>
        )}
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
          doneText={scheduling ? '예약했습니다' : '보냈습니다'}
          onClick={() => void submit()}
        >
          {scheduling ? '예약' : '보내기'}
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
