// 분할 버튼 (Base UI Toggle Group, 하나만 선택 · 비울 수 없음). 예: N1 기간 [오늘 | 이번 주 | 날짜]
import { Toggle } from '@base-ui/react/toggle';
import { ToggleGroup } from '@base-ui/react/toggle-group';
import styles from './SegmentedControl.module.css';

export interface SegmentOption<V extends string> {
  value: V;
  label: string;
}

interface Props<V extends string> {
  /** 묶음 이름(화면 읽기용, 예: "기간") */
  label: string;
  options: readonly SegmentOption<V>[];
  value: V;
  onValueChange: (value: V) => void;
}

export function SegmentedControl<V extends string>({ label, options, value, onValueChange }: Props<V>) {
  return (
    <ToggleGroup<V>
      className={styles.group}
      aria-label={label}
      value={[value]}
      onValueChange={(next) => {
        // 이미 고른 칸을 다시 누르면 빈 배열이 온다 → 무시해서 선택이 비지 않게 한다
        const picked = next[0];
        if (picked !== undefined && picked !== value) onValueChange(picked);
      }}
    >
      {options.map((o) => (
        <Toggle key={o.value} value={o.value} className={styles.item}>
          {o.label}
        </Toggle>
      ))}
    </ToggleGroup>
  );
}
