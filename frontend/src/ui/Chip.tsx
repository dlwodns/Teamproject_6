// 칩 (components.md 3절 · UX-D13). 색이 아니라 글자가 뜻을 말한다.
// - flag: 상급자 · 즐겨찾기 · 거래처(아이콘 + 글자). 좁은 목록에서는 compact로 아이콘만 + aria-label + 말풍선
// - reason: 확인 사유(정보 파랑) · category: 분류(회색)
import type { ReactNode } from 'react';
import styles from './Chip.module.css';
import { Building, RankIcon, Star } from './Icon.tsx';
import { Tooltip } from './Tooltip.tsx';

export type FlagKind = 'superior' | 'favorite' | 'client';

/** 한 줄에 붙이는 순서: 상급자 → 즐겨찾기 → 거래처 */
export const FLAG_ORDER: readonly FlagKind[] = ['superior', 'favorite', 'client'];

export const FLAG_LABELS: Record<FlagKind, string> = { superior: '상급자', favorite: '즐겨찾기', client: '거래처' };

function FlagIcon({ flag }: { flag: FlagKind }) {
  if (flag === 'superior') return <RankIcon size={16} className={styles.icon} />;
  if (flag === 'favorite') return <Star size={14} fill="currentColor" className={styles.icon} aria-hidden="true" />;
  return <Building size={14} className={styles.icon} aria-hidden="true" />;
}

export type ChipProps =
  | { kind: 'flag'; flag: FlagKind; compact?: boolean }
  | { kind: 'reason' | 'category'; children: ReactNode };

export function Chip(props: ChipProps) {
  if (props.kind !== 'flag') {
    return (
      <span className={styles.chip} data-kind={props.kind}>
        {props.children}
      </span>
    );
  }
  const label = FLAG_LABELS[props.flag];
  if (props.compact) {
    return (
      <Tooltip content={label}>
        <span className={styles.chip} data-kind="flag" data-compact="" role="img" aria-label={label} tabIndex={0}>
          <FlagIcon flag={props.flag} />
        </span>
      </Tooltip>
    );
  }
  return (
    <span className={styles.chip} data-kind="flag">
      <FlagIcon flag={props.flag} />
      {label}
    </span>
  );
}

/** 플래그 여러 개를 정해진 순서로 붙인다(최대 3개) */
export function FlagChips({ flags, compact }: { flags: readonly FlagKind[]; compact?: boolean }) {
  const ordered = FLAG_ORDER.filter((f) => flags.includes(f));
  if (ordered.length === 0) return null;
  return (
    <span className={styles.group}>
      {ordered.map((f) => (
        <Chip key={f} kind="flag" flag={f} compact={compact} />
      ))}
    </span>
  );
}
