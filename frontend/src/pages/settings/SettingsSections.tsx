// 설정 화면 칸 (11-18): 내 정보(읽기만) · 근무 · 메일 본문 읽기 · 답장 템플릿 · 테마.
// - 칸은 바꾸면 바로 저장한다(SavedField: 칸을 벗어날 때). 답장 템플릿만 [템플릿 저장] 버튼으로 통째로 저장한다
// - 서버가 그 칸을 보내지 않으면(undefined · 없는 요청) 그 칸을 숨긴다
// - 11-18 사용자 피드백: 사람(상급자 · 즐겨찾기) 칸은 뺐다(캐치봇에 물어보면 된다). 템플릿은 이름 + 자유 글 한 칸
import { useEffect, useId, useState, type InputHTMLAttributes } from 'react';
import type { ReplyTemplate, Settings, SettingsPatch } from '../../api/contract.ts';
import { useAgentMemoryQuery, usePatchSettings, useSettingsQuery } from '../../api/queries.ts';
import { readTheme, saveTheme, THEMES, type Theme } from '../../lib/theme.ts';
import { Button, Checkbox, SegmentedControl, StateRow, useToast } from '../../ui/index.ts';
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

/** 로그인한 계정의 정보를 그대로 보인다(고치지 않는다). 부서 · 직급은 메일에서 나를 가리키는지 판단하는 데 쓴다 */
export function MyInfo() {
  const memory = useAgentMemoryQuery();
  if (memory.isNotAvailable) return null;
  if (!memory.data) return <StateRow state={memory.isError ? 'error' : 'loading'} onRetry={() => void memory.refetch()} />;
  const me = memory.data.me;
  const rows: Array<[string, string]> = [
    ['이름', me.name],
    ['부서', me.department ?? '—'],
    ['직급', me.position ?? '—'],
  ];
  return (
    <div className={styles.form}>
      <dl className={styles.info}>
        {rows.map(([k, v]) => (
          <div key={k} className={styles.infoRow}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <p className={styles.hint}>로그인한 계정 정보에서 자동으로 가져옵니다.</p>
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

// ── 답장 템플릿 ──

const MAX_TEMPLATES = 20; // 서버와 같다(api/settings.py)
const MAX_PATTERN = 4000;
const NEW_PATTERN = '{수신자명}님, 안녕하세요.\n\n{내용}\n\n감사합니다.\n{발신자명} 드림';
const newKey = () => `t${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

/** 답장 쓰기 칸의 [템플릿] 고르기에 나오는 글. 이름과 글 한 칸만 두고 자유롭게 쓴다 */
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
  const invalid = list.some((t) => !t.name.trim());
  const edit = (i: number, field: 'name' | 'pattern', v: string) => setList((l) => l.map((t, j) => (j === i ? { ...t, [field]: v } : t)));
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
      <p className={styles.hint}>
        {'답장 쓰기에서 고르는 틀입니다. 자유롭게 쓰면 되고, {수신자명} · {발신자명}은 보낼 때 이름으로 바뀝니다. {내용}을 넣으면 쓴 글이 그 자리에, 없으면 틀 아래에 들어갑니다.'}
      </p>
      {list.map((t, i) => (
        <details key={t.key} className={styles.template} open={!server.some((x) => x.key === t.key)} role="group" aria-label={`템플릿 ${t.name.trim() || '이름 없음'}`}>
          <summary className={styles.label}>{t.name.trim() || '이름 없는 템플릿'}</summary>
          <TemplateInput label="이름" value={t.name} onChange={(v) => edit(i, 'name', v)} maxLength={100} />
          <TemplateInput label="내용" multiline value={t.pattern} onChange={(v) => edit(i, 'pattern', v)} maxLength={MAX_PATTERN} />
          <Button size="sm" variant="ghost" disabled={list.length <= 1} onClick={() => setList((l) => l.filter((_, j) => j !== i))}>
            이 템플릿 삭제
          </Button>
        </details>
      ))}
      <span className={styles.inline}>
        <Button size="sm" disabled={list.length >= MAX_TEMPLATES} onClick={() => setList((l) => [...l, { key: newKey(), name: '새 템플릿', pattern: NEW_PATTERN }])}>
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
          이름이 빈 템플릿이 있어 저장할 수 없습니다.
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
        <textarea id={id} className={styles.textarea} rows={7} value={value} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input id={id} className={styles.wide} value={value} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} />
      )}
    </div>
  );
}

// ── 화면 테마 ──

const THEME_LABEL: Record<Theme, string> = { light: '라이트', dark: '다크', system: '시스템' };

/** 라이트 · 다크 · 시스템(기기 설정을 따름). 이 브라우저에만 저장한다(lib/theme.ts) */
export function ThemePicker() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  return (
    <div className={styles.field}>
      <span className={styles.label} aria-hidden="true">
        테마
      </span>
      <SegmentedControl
        label="테마"
        value={theme}
        options={THEMES.map((t) => ({ value: t, label: THEME_LABEL[t] }))}
        onValueChange={(v) => {
          setTheme(v);
          saveTheme(v);
        }}
      />
      <p className={styles.hint}>시스템을 고르면 기기의 라이트 · 다크 설정을 따릅니다.</p>
    </div>
  );
}
