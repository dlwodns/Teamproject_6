// "에이전트가 아는 것" (agent_pickle_plan.md 5.2 · 계약 3.3 · 3.4). 에이전트 패널 ⋯ 메뉴에서 여는 패널 안 화면이고,
// 설정 화면 담당이 그대로 붙일 수 있게 따로 내보낸다: <AgentMemoryView /> (onBack을 주면 맨 위에 ‹ 뒤로가 생긴다).
// - 읽는 곳이 정해진 값만 보인다(나 · 중요한 사람). 항목마다 쓰는 곳(used_by) · 쓰는 방식(uses) · 출처 한 줄(origin)
// - 고치기 · 지우기는 바로 서버에 보내고, 맨 위 한 줄에 결과 + [실행 취소](같은 되돌리기 API)
// - 메일 기억하기 켬 · 끔(PATCH /api/agent/settings)
// 초안 습관 · 예약 명령은 P2라 그리지 않는다(없는 기능을 보이지 않는다).
import { Switch } from '@base-ui/react/switch';
import { useId, useState, type FormEvent } from 'react';
import { MAILING_LIST_KINDS, type MailingList, type MailingListKind, type MemoryPerson } from '../../api/contract.ts';
import { useAgentMemoryQuery, useMemoryMutations } from '../../api/queries.ts';
import { Button, Checkbox, ChevronLeft, IconButton, LiveRegion, Select, StateRow } from '../../ui/index.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import styles from './AgentMemoryView.module.css';

const KIND_LABEL: Record<MailingListKind, string> = { role: '직책 목록', team: '팀 목록', all: '전사 목록' };
const ADDRESS = /^[^@\s,;<>"']+@[^@\s,;<>"']+$/;

interface Change {
  text: string;
  actionId: number | null;
  undo: 'idle' | 'pending' | 'done' | 'error';
}

const personName = (p: Pick<MemoryPerson, 'name' | 'position' | 'email'>) =>
  p.name ? (p.position ? `${p.name} ${p.position}` : p.name) : p.email;

export function AgentMemoryView({ onBack, hideTitle = false }: { onBack?: () => void; /** 화면이 같은 제목을 이미 둔 곳(에이전트 화면 메뉴, FE-16) */ hideTitle?: boolean }) {
  const query = useAgentMemoryQuery();
  const { me, person, settings } = useMemoryMutations();
  const actions = useTaskActions();
  const [change, setChange] = useState<Change | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const titleId = useId();

  const done = (text: string, actionId: number | null) => {
    setFailed(null);
    setChange(actionId === null ? null : { text, actionId, undo: 'idle' });
  };
  const fail = () => setFailed('바꾸지 못했어요. 다시 해 주세요.');

  async function undoChange() {
    if (!change || change.actionId === null || change.undo === 'pending' || change.undo === 'done') return;
    setChange({ ...change, undo: 'pending' });
    try {
      await actions.undo(change.actionId, { source: 'button', toast: false });
      setChange({ ...change, undo: 'done' });
    } catch {
      setChange({ ...change, undo: 'error' });
    }
  }

  const header = onBack ? (
    <div className={styles.top}>
      <IconButton label="뒤로" icon={<ChevronLeft size={20} aria-hidden="true" />} onClick={onBack} className={styles.back} />
      <h3 id={titleId} className={styles.viewTitle} tabIndex={-1}>
        에이전트가 아는 것
      </h3>
    </div>
  ) : hideTitle ? null : (
    <h3 id={titleId} className={styles.viewTitle}>
      에이전트가 아는 것
    </h3>
  );

  if (query.isPending)
    return (
      <div className={styles.root}>
        {header}
        <StateRow state="loading" />
      </div>
    );
  if (query.isError && !query.data)
    return (
      <div className={styles.root}>
        {header}
        <StateRow state="error" text="불러오지 못함" onRetry={() => void query.refetch()} />
      </div>
    );

  const m = query.data;
  const learnPending = settings.isPending ? settings.variables?.learnFromMail : undefined;

  const patchPerson = (p: MemoryPerson, patch: Parameters<typeof person.mutate>[0]['patch'], text: string) =>
    person.mutate({ contactId: p.contactId, patch }, { onSuccess: (r) => done(text, r.actionId), onError: fail });

  const removeList = (address: string) =>
    me.mutate(
      { mailingLists: m.me.mailingLists.filter((l) => l.address !== address) },
      { onSuccess: (r) => done(`배포 목록에서 ${address}를 지웠어요`, r.actionId), onError: fail },
    );

  return (
    <section className={styles.root} aria-labelledby={hideTitle ? undefined : titleId}>
      {header}
      <p className={styles.intro}>에이전트는 아래 값으로 메일을 분류하고 제안 카드를 띄워요. 고치거나 지우면 바로 다음 판단부터 반영돼요.</p>

      <LiveRegion>{change ? (change.undo === 'done' ? '되돌렸어요' : change.text) : (failed ?? '')}</LiveRegion>
      {(change || failed) && (
        <div className={styles.banner}>
          <span className={styles.bannerText}>{failed ?? (change!.undo === 'done' ? '되돌렸어요' : change!.text)}</span>
          {change && !failed && change.undo !== 'done' && (
            <Button size="sm" variant="ghost" className={styles.trailing} aria-disabled={change.undo === 'pending' || undefined} onClick={() => void undoChange()}>
              {change.undo === 'pending' ? '되돌리는 중' : change.undo === 'error' ? '다시 되돌리기' : '실행 취소'}
            </Button>
          )}
        </div>
      )}

      {/* 메일 기억하기 */}
      <div className={styles.card}>
        <div className={styles.switchRow}>
          <div className={styles.switchText}>
            <p className={styles.itemTitle} id={`${titleId}-learn`}>
              메일 기억하기
            </p>
            <p className={styles.help}>
              사내 메일 서명과 받는 사람에서 보낸 사람 직급 · 상급자 · 내 배포 목록을 알아서 넣어요. 넣은 것은 기록 탭에 &lsquo;자동&rsquo;으로 남고 되돌릴 수 있어요.
            </p>
          </div>
          <Switch.Root
            className={styles.switch}
            checked={learnPending ?? m.learnFromMail}
            aria-labelledby={`${titleId}-learn`}
            onCheckedChange={(on) => settings.mutate({ learnFromMail: on }, { onSuccess: () => setFailed(null), onError: fail })}
          >
            <Switch.Thumb className={styles.thumb} />
          </Switch.Root>
        </div>
      </div>

      {/* 나 */}
      <div className={styles.section}>
        <div className={styles.sectionHead}>
          <h4 className={styles.heading}>나</h4>
          {!editing && (
            <Button size="sm" variant="ghost" className={styles.trailing} onClick={() => setEditing(true)}>
              고치기
            </Button>
          )}
        </div>
        <div className={styles.card}>
          {editing ? (
            <MeForm
              department={m.me.department}
              position={m.me.position}
              lists={m.me.mailingLists}
              saving={me.isPending}
              onCancel={() => setEditing(false)}
              onSave={(patch) =>
                me.mutate(patch, {
                  onSuccess: (r) => {
                    setEditing(false);
                    done('내 정보를 바꿨어요', r.actionId);
                  },
                  onError: fail,
                })
              }
            />
          ) : (
            <>
              <dl className={styles.fields}>
                <div className={styles.field}>
                  <dt>이름</dt>
                  <dd>{m.me.name}</dd>
                </div>
                <div className={styles.field}>
                  <dt>팀</dt>
                  <dd>{m.me.department ?? <span className={styles.none}>없음</span>}</dd>
                </div>
                <div className={styles.field}>
                  <dt>직책</dt>
                  <dd>{m.me.position ?? <span className={styles.none}>없음</span>}</dd>
                </div>
                <div className={styles.field}>
                  <dt>배포 목록</dt>
                  <dd>
                    {m.me.mailingLists.length === 0 ? (
                      <span className={styles.none}>아직 없어요</span>
                    ) : (
                      <ul className={styles.lists}>
                        {m.me.mailingLists.map((l) => (
                          <li key={l.address} className={styles.listItem}>
                            <span className={styles.address} title={l.address}>
                              {l.address}
                            </span>
                            <span className={styles.kind}>{KIND_LABEL[l.kind]}</span>
                            <Button size="sm" variant="ghost" className={styles.trailing} onClick={() => removeList(l.address)}>
                              지우기
                            </Button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </dd>
                </div>
              </dl>
              <Uses uses={m.me.uses} usedBy={m.me.usedBy} origin={m.me.origin.text} />
            </>
          )}
        </div>
      </div>

      {/* 중요한 사람 */}
      <div className={styles.section}>
        <div className={styles.sectionHead}>
          <h4 className={styles.heading}>중요한 사람</h4>
        </div>
        {m.people.length === 0 ? (
          <p className={styles.help}>상급자나 즐겨찾기로 표시한 사람이 없어요.</p>
        ) : (
          <ul className={styles.people}>
            {m.people.map((p) => (
              <li key={p.contactId} className={styles.person}>
                <div className={styles.personHead}>
                  <p className={styles.personName}>
                    <span className={styles.itemTitle}>{personName(p)}</span>
                    <span className={styles.email} title={p.email}>
                      {p.email}
                    </span>
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    className={styles.trailing}
                    onClick={() =>
                      patchPerson(
                        p,
                        { isSuperior: false, isFavorite: false, ...(p.facts.length ? { facts: Object.fromEntries(p.facts.map((f) => [f.kind, null])) } : {}) },
                        `${personName(p)}님을 중요한 사람에서 지웠어요`,
                      )
                    }
                  >
                    지우기
                  </Button>
                </div>
                <div className={styles.flags}>
                  <Checkbox
                    checked={p.isSuperior}
                    label="상급자"
                    onCheckedChange={(on) => patchPerson(p, { isSuperior: on }, `${personName(p)}님을 상급자${on ? '로 정했어요' : '에서 뺐어요'}`)}
                  />
                  <Checkbox
                    checked={p.isFavorite}
                    label="즐겨찾기"
                    onCheckedChange={(on) => patchPerson(p, { isFavorite: on }, `${personName(p)}님을 즐겨찾기${on ? '에 넣었어요' : '에서 뺐어요'}`)}
                  />
                </div>
                {p.facts.length > 0 && (
                  <ul className={styles.lists}>
                    {p.facts.map((f) => (
                      <li key={f.kind} className={styles.listItem}>
                        <span className={styles.kind}>{f.label}</span>
                        <span className={styles.address}>{f.value}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          className={styles.trailing}
                          onClick={() => patchPerson(p, { facts: { [f.kind]: null } }, `${personName(p)}님의 ${f.label}을 지웠어요`)}
                        >
                          지우기
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
                <Uses uses={p.uses} usedBy={p.usedBy} origin={p.origin.text} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function Uses({ uses, usedBy, origin }: { uses: string; usedBy: string[]; origin: string }) {
  return (
    <div className={styles.uses}>
      {uses && <p className={styles.help}>{uses}</p>}
      <p className={styles.meta}>
        {usedBy.length > 0 && <span>쓰는 곳 {usedBy.join(' · ')}</span>}
        <span>{origin}</span>
      </p>
    </div>
  );
}

interface MeFormProps {
  department: string | null;
  position: string | null;
  lists: MailingList[];
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: { department: string | null; position: string | null; mailingLists?: MailingList[] }) => void;
}

function MeForm({ department, position, lists, saving, onCancel, onSave }: MeFormProps) {
  const [dept, setDept] = useState(department ?? '');
  const [pos, setPos] = useState(position ?? '');
  const [address, setAddress] = useState('');
  const [kind, setKind] = useState<MailingListKind>('team');
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    const a = address.trim().toLowerCase();
    if (a && !ADDRESS.test(a)) {
      setError('배포 목록 주소는 이름@도메인 하나만 적어 주세요.');
      return;
    }
    if (a && lists.length >= 20) {
      setError('배포 목록은 20개까지 넣을 수 있어요.');
      return;
    }
    setError(null);
    onSave({
      department: dept.trim() || null,
      position: pos.trim() || null,
      ...(a ? { mailingLists: [...lists.filter((l) => l.address !== a), { address: a, kind }] } : {}),
    });
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <label className={styles.formField} htmlFor={`${id}-dept`}>
        <span className={styles.formLabel}>팀</span>
        <input id={`${id}-dept`} className={styles.input} value={dept} maxLength={100} onChange={(e) => setDept(e.target.value)} />
      </label>
      <label className={styles.formField} htmlFor={`${id}-pos`}>
        <span className={styles.formLabel}>직책</span>
        <input id={`${id}-pos`} className={styles.input} value={pos} maxLength={50} onChange={(e) => setPos(e.target.value)} />
      </label>
      <label className={styles.formField} htmlFor={`${id}-list`}>
        <span className={styles.formLabel}>배포 목록 넣기</span>
        <input
          id={`${id}-list`}
          className={styles.input}
          value={address}
          inputMode="email"
          autoComplete="off"
          placeholder="예: team1@cne.example"
          onChange={(e) => setAddress(e.target.value)}
        />
      </label>
      {address.trim() && (
        <Select<MailingListKind>
          label="종류"
          options={MAILING_LIST_KINDS.map((k) => ({ value: k, label: KIND_LABEL[k] }))}
          value={kind}
          onValueChange={setKind}
        />
      )}
      {error && (
        <p className={styles.formError} role="alert">
          {error}
        </p>
      )}
      <div className={styles.formActions}>
        <Button size="sm" onClick={onCancel}>
          취소
        </Button>
        <Button size="sm" type="submit" variant="primary" loading={saving} loadingText="저장하는 중" doneText="저장했어요">
          저장
        </Button>
      </div>
    </form>
  );
}
