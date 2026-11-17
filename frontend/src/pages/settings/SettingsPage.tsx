// 설정 화면 (11-14 · 11-15). 이 화면에서는 캐치봇 버튼 · 패널이 숨는다(앱 틀).
// - 모든 칸은 바꾸면 바로 저장한다(저장 버튼 없음). 시각은 칸을 벗어날 때(blur) 값이 바뀌었으면 저장하고 옆에 '저장되었습니다'
// - 시각은 <input type="time">(브라우저 기본 고르기). 서버가 다음 틱부터 그 시각에 업무 요약 · 회고를 만든다
// - 서버에 회고 시각 칸이 없으면(eveningTime undefined) 그 칸을 숨긴다
// - 11-17 FE-6(#126, #190 리뷰 합의): 답 없음 기준일(awaiting_reply_days 1–30) · 움직임 줄이기(reduce_motion, 앱 전체는 AppLayout이 건다)
// - 11-18: 내 정보 · 근무 · 방해 금지 · 부재 · 메일 본문 읽기 · 사람 · 답장 템플릿(SettingsSections.tsx)
import { useId } from 'react';
import type { SettingsPatch } from '../../api/contract.ts';
import { useAgentSettingsQuery, usePatchAgentSettings, usePatchSettings, useSettingsQuery } from '../../api/queries.ts';
import { AGENT_NAME } from '../../features/agent/agentBrand.tsx';
import { useBrowserNotify } from '../../features/agent/browserNotify.ts';
import { osReducedMotion } from '../../lib/motion.ts';
import { Checkbox, StateRow, useToast } from '../../ui/index.ts';
import styles from './SettingsPage.module.css';
import { MyInfo, People, ReadBody, SavedField, Templates, validTime, WorkPolicy } from './SettingsSections.tsx';

/** 답 없음 기준일: 서버와 같은 1–30일(backend settings.py) */
const validAwaitDays = (v: string) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 30;

function BriefingTimes() {
  const settings = useSettingsQuery();
  const patch = usePatchSettings();
  const toast = useToast();
  const data = settings.data;
  if (settings.isNotAvailable) return null;
  if (!data) return <StateRow state={settings.isError ? 'error' : 'loading'} text={settings.isError ? '설정을 불러오지 못했습니다' : undefined} onRetry={() => void settings.refetch()} />;
  const save = (p: SettingsPatch) =>
    patch.mutateAsync(p).catch((e: unknown) => {
      toast.show({ id: 'settings-briefing', kind: 'error', title: '설정을 변경하지 못했습니다' });
      throw e;
    });

  return (
    <div className={styles.form}>
      <SavedField
        type="time"
        required
        valid={validTime}
        label="일일 업무 요약"
        hint="근무일 지정 시각에 금일 마감 · 기한 경과 · 회신 대기 업무를 정리합니다."
        value={data.remindTime}
        onSave={(v) => save({ remindTime: v })}
      />
      {data.eveningTime !== undefined && (
        <SavedField
          type="time"
          required
          valid={validTime}
          label="일일 업무 회고"
          hint="금일 완료 · 미처리 · 익일 마감 업무를 정리합니다. 금요일에는 주간 회고도 함께 드립니다."
          value={data.eveningTime}
          onSave={(v) => save({ eveningTime: v })}
        />
      )}
      <SavedField
        type="number"
        inputMode="numeric"
        min={1}
        max={30}
        required
        valid={validAwaitDays}
        unit="일"
        label="답 없음 기준일"
        hint="보낸 요청 메일에 이 기간 동안 회신이 없으면 '답 기다림'으로 알려 드립니다(1–30일)."
        value={String(data.awaitingReplyDays)}
        onSave={(v) => save({ awaitingReplyDays: Number(v) })}
      />
      <p className={styles.hint}>{`${AGENT_NAME} 대화에서 "업무 요약" 또는 "오늘 회고 정리"를 요청하면 바로 확인할 수 있습니다.`}</p>
    </div>
  );
}

/** 움직임 줄이기(wireframe P5). 기기에서 '동작 줄이기'가 켜져 있으면 이미 줄이고 있으므로 켜진 채로 잠근다 */
function ReduceMotion() {
  const settings = useSettingsQuery();
  const patch = usePatchSettings();
  const toast = useToast();
  if (settings.isNotAvailable || !settings.data) return null; // 불러오는 중 · 오류 표시는 BriefingTimes가 한다
  const os = osReducedMotion();
  const on = os || (patch.isPending && patch.variables?.reduceMotion !== undefined ? patch.variables.reduceMotion : settings.data.reduceMotion);
  return (
    <div className={styles.field}>
      <Checkbox
        label="움직임 줄이기"
        checked={on}
        disabled={os || patch.isPending}
        onCheckedChange={(v) =>
          patch.mutate({ reduceMotion: v }, { onError: () => toast.show({ id: 'settings-motion', kind: 'error', title: '설정을 변경하지 못했습니다' }) })
        }
      />
      <p className={styles.hint}>
        {os ? '기기 설정에서 동작 줄이기가 켜져 있어 이미 적용 중입니다.' : '업무 완료 · 화면 전환 등의 애니메이션을 끄고 바로 바뀌게 합니다.'}
      </p>
    </div>
  );
}

/** 작업이 끝나면 브라우저 알림(11-15: 대화 결과 칸에서 옮김) */
function BrowserNotify() {
  const { on, permission, toggle } = useBrowserNotify();
  if (permission === 'unsupported') return null;
  return (
    <div className={styles.field}>
      <Checkbox checked={on} disabled={permission === 'denied'} onCheckedChange={(v) => void toggle(v)} label="작업 완료 시 브라우저 알림 받기" />
      {permission === 'denied' && <p className={styles.hint}>브라우저에서 알림이 차단되어 있습니다. 브라우저 설정에서 허용해 주십시오.</p>}
    </div>
  );
}

/** 메일 내용 분석(11-15). 켜면 받은 메일에서 보낸 사람의 소속 · 담당 업무를 뽑아 DB에 저장하고(mail extract), 끄면 뽑지 않는다.
 *  무엇을 뽑았는지는 보여 주지 않는다(DB가 관리, 캐치봇 판단에만 쓴다) */
function MailAnalysis() {
  const settings = useAgentSettingsQuery();
  const patch = usePatchAgentSettings();
  const toast = useToast();
  if (settings.isNotAvailable) return null;
  if (!settings.data) return <StateRow state={settings.isError ? 'error' : 'loading'} onRetry={() => void settings.refetch()} />;
  const on = patch.isPending && patch.variables ? patch.variables.learnFromMail : settings.data.learnFromMail;
  return (
    <div className={styles.field}>
      <Checkbox
        label="메일 내용 분석 허용"
        checked={on}
        disabled={patch.isPending}
        onCheckedChange={(v) =>
          patch.mutate({ learnFromMail: v }, { onError: () => toast.show({ id: 'settings-learn', kind: 'error', title: '설정을 변경하지 못했습니다' }) })
        }
      />
      <p className={styles.hint}>
        허용하면 수신 메일 본문에서 발신자의 소속 · 담당 업무를 추출하여 업무 분류와 알림에 반영합니다. 해제하면 추출하지 않습니다. 메일 본문은 저장하지 않습니다.
      </p>
    </div>
  );
}

export function SettingsPage() {
  const headingId = useId();
  return (
    <div className={styles.page}>
      <section className={styles.card} aria-labelledby={headingId}>
        <h1 id="page-title" className={styles.title} tabIndex={-1}>
          설정
        </h1>
        <h2 id={headingId} className={styles.section}>
          내 정보
        </h2>
        <MyInfo />
        <h2 className={styles.section}>{`${AGENT_NAME} 알림`}</h2>
        <BriefingTimes />
        <BrowserNotify />
        <h2 className={styles.section}>근무 · 방해 금지</h2>
        <WorkPolicy />
        <h2 className={styles.section}>메일 분석</h2>
        <ReadBody />
        <MailAnalysis />
        <h2 className={styles.section}>사람</h2>
        <People />
        <h2 className={styles.section}>답장 템플릿</h2>
        <Templates />
        <h2 className={styles.section}>화면</h2>
        <ReduceMotion />
      </section>
    </div>
  );
}
