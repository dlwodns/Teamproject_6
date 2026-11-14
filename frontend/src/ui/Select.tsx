// 선택 상자 (Base UI Select). 예: 답장 템플릿 · 보낸 계정. 이름 있는 <label>이 붙는다.
import { Select as BaseSelect } from '@base-ui/react/select';
import styles from './Select.module.css';
import { Check, ChevronDown } from './Icon.tsx';

export interface SelectOption<V extends string> {
  value: V;
  label: string;
}

interface Props<V extends string> {
  /** 보이는 이름(<label>) */
  label: string;
  options: readonly SelectOption<V>[];
  value: V | null;
  onValueChange: (value: V) => void;
  placeholder?: string;
  disabled?: boolean;
  name?: string;
}

export function Select<V extends string>({ label, options, value, onValueChange, placeholder = '고르기', disabled, name }: Props<V>) {
  return (
    <BaseSelect.Root<V>
      items={options}
      value={value}
      onValueChange={(next) => {
        if (next !== null) onValueChange(next);
      }}
      disabled={disabled}
      name={name}
    >
      <div className={styles.field}>
        <BaseSelect.Label className={styles.label}>{label}</BaseSelect.Label>
        <BaseSelect.Trigger className={styles.trigger}>
          <BaseSelect.Value className={styles.value} placeholder={placeholder} />
          <BaseSelect.Icon className={styles.icon}>
            <ChevronDown size={16} aria-hidden="true" />
          </BaseSelect.Icon>
        </BaseSelect.Trigger>
      </div>
      <BaseSelect.Portal>
        <BaseSelect.Positioner className={styles.positioner} sideOffset={4} alignItemWithTrigger={false}>
          <BaseSelect.Popup className={styles.popup}>
            <BaseSelect.List>
              {options.map((o) => (
                <BaseSelect.Item key={o.value} value={o.value} className={styles.item}>
                  <BaseSelect.ItemIndicator className={styles.indicator}>
                    <Check size={16} aria-hidden="true" />
                  </BaseSelect.ItemIndicator>
                  <BaseSelect.ItemText className={styles.itemText}>{o.label}</BaseSelect.ItemText>
                </BaseSelect.Item>
              ))}
            </BaseSelect.List>
          </BaseSelect.Popup>
        </BaseSelect.Positioner>
      </BaseSelect.Portal>
    </BaseSelect.Root>
  );
}
