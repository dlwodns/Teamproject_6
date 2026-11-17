// 설정 화면 칸 (11-18): 내 정보 · 근무 · 메일 본문 읽기 · 사람 · 답장 템플릿.
// - 칸은 바꾸면 바로 저장한다(SavedField: 칸을 벗어날 때). 답장 템플릿만 여러 칸을 함께 고치므로 [템플릿 저장] 버튼으로 통째로 저장한다
// - 서버가 그 칸을 보내지 않으면(undefined · 없는 요청) 그 칸을 숨긴다
import { useEffect, useId, useState, type InputHTMLAttributes } from 'react';
import type { ReplyTemplate, Settings, SettingsPatch } from '../../api/contract.ts';
import { useAgentMemoryQuery, useContactsQuery, usePatchMemoryMe, usePatchPerson, usePatchSettings, useSettingsQuery } from '../../api/queries.ts';
import { Button, Checkbox, StateRow, useToast } from '../../ui/index.ts';
import styles from './SettingsPage.module.css';
import { formatDays, fromKstLocal, parseDays, toKstLocal } from './settingsModel.ts';

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
export const validTime = (v: string) => HHMM.test(v);

type FieldProps = { label: string; hint?: string; value: string; valid: (v: string) => boolean; onSave: (v: string) => Promise<unknown>; unit?: string } & Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'onBlur' | 'id'
>;

/** 칸을 벗어날 때(blur) 값이 바뀌었고 맞는 값이면 저장한다. 실패하거나 틀린 값이면 원래 값으로 돌린다 */
export function SavedField({ label, hint, value, valid, onSave, unit, ...input }: FieldProps) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const [saved, setSaved] = useState(false);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    if (draft === value) return;
    if (draft.trim() === value && input.type === 'text') return setDraft(value); // 공백만 바뀌면 저장하지 않는다
    if (!valid(draft)) return setDraft(value);
    setSaved(false);
    void onSave(draft).then(() => setSaved(true), () => setDraft(value));
  };
  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      <span className={styles.inline}>
        <input id={id} {...input} value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit} />
        {unit}
        <span role="status" className={styles.saved}>
          {saved ? '저장되었습니다' : ''}
        </span>
      </span>
      {hint && <p className={styles.hint}>{hint}</p>}
    </div>
  );
}

/** 설정 저장(실패하면 알림을 띄우고 다시 던진다 — SavedField가 원래 값으로 돌린다) */
function useSaveSettings(toastId: string) {
  const patch = usePatchSettings();
  const toast = useToast();
  return (p: SettingsPatch) =>
    patch.mutateAsync(p).catch((e: unknown) => {
      toast.show({ id: toastId, kind: 'error', title: '설정을 변경하지 못했습니다' });
      throw e;
    });
}

// ── 내 정보 ──

const shortText = (max: number) => (v: string) => v.trim().length <= max;

/** 이름은 계정 이름이라 바꾸지 않는다. 부서 · 직급은 메일 분류(나를 가리키는지)와 캐치봇 답에 쓴다 */
export function MyInfo() {
  const memory = useAgentMemoryQuery();
  const patch = usePatchMemoryMe();
  const toast = useToast();
  if (memory.isNotAvailable) return null;
  if (!memory.data) return <StateRow state={memory.isError ? 'error' : 'loading'} onRetry={() => void memory.refetch()} />;
  const me = memory.data.me;
  const save = (p: { department?: string | null; position?: string | null }) =>
    patch.mutateAsync(p).catch((e: unknown) => {
      toast.show({ id: 'settings-me', kind: 'error', title: '내 정보를 변경하지 못했습니다' });
      throw e;
    });
  return (
    <div className={styles.form}>
      <div className={styles.field}>
        <span className={styles.label}>이름</span>
        <span>{me.name}</span>
      </div>
      <SavedField type="text" className={styles.wide} label="부서" valid={shortText(100)} value={me.department ?? ''} onSave={(v) => save({ department: v.trim() || null })} />
      <SavedField
        type="text"
        label="직급"
        hint="메일에서 나를 부르는 말('김 팀장님')을 알아보는 데 씁니다."
        valid={shortText(50)}
        value={me.position ?? ''}
        onSave={(v) => save({ position: v.trim() || null })}
      />
    </div>
  );
}

// ── 근무 · 방해 금지 · 부재 ──

const DAY_LABELS = ['월', '화', '수', '목', '금', '토', '일'] as const;

export function WorkPolicy() {
  const settings = useSettingsQuery();
  const save = useSaveSettings('settings-work');
  const s = settings.data;
  if (!s || s.workStart === undefined || s.workEnd === undefined) return null; // 불러오는 중 · 오류는 위 칸이 보인다
  return <WorkPolicyForm s={s} save={save} />;
}

function WorkPolicyForm({ s, save }: { s: Settings; save: (p: SettingsPatch) => Promise<Settings> }) {
  const patch = usePatchSettings();
  // 저장 중이면 보낸 값을 기준으로(연달아 누를 때 앞의 변경을 덮지 않게)
  const pendingDays = patch.isPending ? patch.variables?.workDays : undefined;
  const days = parseDays(pendingDays ?? s.workDays ?? '1-5');
  const daysId = useId();
  const quietOn = s.quietStart !== null && s.quietEnd !== null;
  const toggleDay = (d: number, on: boolean) => {
    const next = new Set(days);
    if (on) next.add(d);
    else next.delete(d);
    if (next.size > 0) void save({ workDays: formatDays(next) }).catch(() => undefined);
  };
  return (
    <div className={styles.form}>
      <div className={styles.inline}>
        <SavedField type="time" required label="근무 시작" valid={(v) => validTime(v) && v < s.workEnd!} value={s.workStart!} onSave={(v) => save({ workStart: v })} />
        <SavedField type="time" required label="근무 끝" valid={(v) => validTime(v) && v > s.workStart!} value={s.workEnd!} onSave={(v) => save({ workEnd: v })} />
      </div>
      <div className={styles.field} role="group" aria-labelledby={daysId}>
        <span id={daysId} className={styles.label}>
          근무 요일
        </span>
        <span className={styles.inline}>
          {DAY_LABELS.map((label, i) => (
            <Checkbox key={label} label={label} checked={days.has(i + 1)} disabled={patch.isPending || (days.size === 1 && days.has(i + 1))} onCheckedChange={(v) => toggleDay(i + 1, v)} />
          ))}
        </span>
        <p className={styles.hint}>근무 시간 밖에 생긴 알림은 다음 근무 시작에 모아 드립니다. 요약 · 회고도 근무일에만 만듭니다.</p>
      </div>
      <div className={styles.field}>
        <Checkbox
          label="방해 금지 시간 사용"
          checked={quietOn}
          onCheckedChange={(v) => void save(v ? { quietStart: '22:00', quietEnd: '07:00' } : { quietStart: null, quietEnd: null }).catch(() => undefined)}
        />
        {quietOn && (
          <span className={styles.inline}>
            <SavedField type="time" required label="방해 금지 시작" valid={validTime} value={s.quietStart!} onSave={(v) => save({ quietStart: v })} />
            <SavedField type="time" required label="방해 금지 끝" valid={validTime} value={s.quietEnd!} onSave={(v) => save({ quietEnd: v })} />
          </span>
        )}
        <p className={styles.hint}>이 시간에는 알림을 보내지 않고 끝나는 시각에 모아 드립니다.</p>
      </div>
      {s.awayUntilMs !== undefined && <Away awayUntilMs={s.awayUntilMs} save={save} />}
    </div>
  );
}

function Away({ awayUntilMs, save }: { awayUntilMs: number | null; save: (p: SettingsPatch) => Promise<Settings> }) {
  return (
    <div className={styles.field}>
      <SavedField
        type="datetime-local"
        className={styles.wide}
        label="부재 중(~까지)"
        hint="이 시각까지 알림을 보내지 않고, 돌아오면 그동안 쌓인 것을 한 번에 알려 드립니다."
        valid={(v) => v === '' || !Number.isNaN(fromKstLocal(v))}
        value={awayUntilMs === null ? '' : toKstLocal(awayUntilMs)}
        onSave={(v) => save({ awayUntilMs: v === '' ? null : fromKstLocal(v) })}
      />
      {awayUntilMs !== null && (
        <Button size="sm" variant="ghost" onClick={() => void save({ awayUntilMs: null }).catch(() => undefined)}>
          부재 중 해제
        </Button>
      )}
    </div>
  );
}

// ── 메일 본문 읽기 ──

export function ReadBody() {
  const settings = useSettingsQuery();
  const patch = usePatchSettings();
  const toast = useToast();
  if (!settings.data || settings.data.readBody === undefined) return null;
  const on = patch.isPending && patch.variables?.readBody !== undefined ? patch.variables.readBody : settings.data.readBody;
  return (
    <div className={styles.field}>
      <Checkbox
        label="메일 본문 읽기"
        checked={on}
        disabled={patch.isPending}
        onCheckedChange={(v) => patch.mutate({ readBody: v }, { onError: () => toast.show({ id: 'settings-body', kind: 'error', title: '설정을 변경하지 못했습니다' }) })}
      />
      <p className={styles.hint}>끄면 새로 받는 메일은 제목과 보낸 사람으로만 업무를 판단합니다. 본문 속 기한 · 요청을 놓칠 수 있습니다.</p>
    </div>
  );
}

// ── 사람(상급자 · 즐겨찾기) ──

export function People() {
  const contacts = useContactsQuery();
  const patch = usePatchPerson();
  const toast = useToast();
  const [q, setQ] = useState('');
  const searchId = useId();
  if (contacts.isNotAvailable) return null;
  if (!contacts.data) return <StateRow state={contacts.isError ? 'error' : 'loading'} onRetry={() => void contacts.refetch()} />;
  const term = q.trim().toLowerCase();
  const rows = contacts.data.filter((c) => !term || `${c.name ?? ''} ${c.position ?? ''} ${c.email}`.toLowerCase().includes(term));
  const set = (contactId: number, p: { isSuperior?: boolean; isFavorite?: boolean }) =>
    patch.mutate({ contactId, patch: p }, { onError: () => toast.show({ id: 'settings-person', kind: 'error', title: '표시를 변경하지 못했습니다' }) });
  return (
    <div className={styles.form}>
      <p className={styles.hint}>상급자가 보낸 메일은 우선순위를 높이고, 오래 미처리면 따로 알려 드립니다. 즐겨찾기는 목록에서 먼저 보입니다.</p>
      <div className={styles.field}>
        <label htmlFor={searchId}>사람 찾기</label>
        <input id={searchId} type="search" className={styles.wide} value={q} onChange={(e) => setQ(e.target.value)} placeholder="이름 · 직급 · 메일 주소" />
      </div>
      {rows.length === 0 ? (
        <p className={styles.hint}>{contacts.data.length === 0 ? '아직 연락처가 없습니다. 메일을 받으면 보낸 사람이 여기에 생깁니다.' : '찾는 사람이 없습니다.'}</p>
      ) : (
        <ul className={styles.people}>
          {rows.map((c) => {
            const who = [c.name ?? c.email, c.position].filter(Boolean).join(' ');
            return (
              <li key={c.contactId} className={styles.person}>
                <span className={styles.personName}>
                  {who}
                  {c.name && <span className={styles.hint}>{c.email}</span>}
                </span>
                <Checkbox label="상급자" aria-label={`${who} 상급자`} checked={c.isSuperior} onCheckedChange={(v) => set(c.contactId, { isSuperior: v })} />
                <Checkbox label="즐겨찾기" aria-label={`${who} 즐겨찾기`} checked={c.isFavorite} onCheckedChange={(v) => set(c.contactId, { isFavorite: v })} />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── 답장 템플릿 ──

const MAX_TEMPLATES = 20; // 서버와 같다(api/settings.py)
const newKey = () => `t${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

/** 답장 쓰기 칸의 [템플릿] 고르기에 나오는 글. 자리표시자 {수신자명} · {발신자명}은 보낼 때 채운다 */
export function Templates() {
  const settings = useSettingsQuery();
  const save = useSaveSettings('settings-templates');
  const server = settings.data?.templates;
  if (server === undefined) return null;
  return <TemplateEditor key={JSON.stringify(server)} server={server} save={save} />;
}

function TemplateEditor({ server, save }: { server: ReplyTemplate[]; save: (p: SettingsPatch) => Promise<Settings> }) {
  const [list, setList] = useState(server);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const dirty = JSON.stringify(list) !== JSON.stringify(server);
  const bodySlot = list.some((t) => [t.greeting, t.closing, t.signature].some((x) => x.includes('{내용}')));
  const invalid = bodySlot || list.some((t) => !t.name.trim());
  const edit = (i: number, field: 'name' | 'greeting' | 'closing' | 'signature', v: string) => setList((l) => l.map((t, j) => (j === i ? { ...t, [field]: v } : t)));
  const submit = async () => {
    setBusy(true);
    try {
      await save({ templates: list });
      toast.show({ id: 'settings-templates', kind: 'info', title: '템플릿을 저장했습니다' });
    } catch {
      /* useSaveSettings가 알렸다 */
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={styles.form}>
      <p className={styles.hint}>{'답장 쓰기에서 고르는 틀입니다. {수신자명} · {발신자명}은 보낼 때 이름으로 바뀌고, 쓴 내용은 인사와 맺음말 사이에 들어갑니다.'}</p>
      {list.map((t, i) => (
        <details key={t.key} className={styles.template} open={!server.some((x) => x.key === t.key)} role="group" aria-label={`템플릿 ${t.name.trim() || '이름 없음'}`}>
          <summary className={styles.label}>{t.name.trim() || '이름 없는 템플릿'}</summary>
          <TemplateInput label="이름" value={t.name} onChange={(v) => edit(i, 'name', v)} maxLength={100} />
          <TemplateInput label="인사" multiline value={t.greeting} onChange={(v) => edit(i, 'greeting', v)} maxLength={2000} />
          <TemplateInput label="맺음말" multiline value={t.closing} onChange={(v) => edit(i, 'closing', v)} maxLength={2000} />
          <TemplateInput label="서명" value={t.signature} onChange={(v) => edit(i, 'signature', v)} maxLength={500} />
          <Button size="sm" variant="ghost" disabled={list.length <= 1} onClick={() => setList((l) => l.filter((_, j) => j !== i))}>
            이 템플릿 삭제
          </Button>
        </details>
      ))}
      <span className={styles.inline}>
        <Button
          size="sm"
          disabled={list.length >= MAX_TEMPLATES}
          onClick={() => setList((l) => [...l, { key: newKey(), name: '새 템플릿', greeting: '{수신자명}님, 안녕하세요. {발신자명}입니다.', closing: '감사합니다.', signature: '{발신자명} 드림', pattern: '' }])}
        >
          템플릿 추가
        </Button>
        <Button size="sm" variant="primary" disabled={!dirty || invalid || busy} onClick={() => void submit()}>
          템플릿 저장
        </Button>
        {dirty && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setList(server)}>
            되돌리기
          </Button>
        )}
      </span>
      {invalid && (
        <p className={styles.hint} role="status">
          {bodySlot ? '{내용}은 쓴 글이 들어갈 자리라 인사 · 맺음말 · 서명에 넣을 수 없습니다.' : '이름이 빈 템플릿이 있어 저장할 수 없습니다.'}
        </p>
      )}
    </div>
  );
}

function TemplateInput({ label, value, onChange, multiline, maxLength }: { label: string; value: string; onChange: (v: string) => void; multiline?: boolean; maxLength: number }) {
  const id = useId();
  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea id={id} className={styles.textarea} rows={2} value={value} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input id={id} className={styles.wide} value={value} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} />
      )}
    </div>
  );
}
