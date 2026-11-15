// 🎤 음성 입력 단추 (components.md 4.4 VoiceButton · FE-8). 보내기 왼쪽, 보내기와 같은 32px 동그라미.
// 평소에는 회색 아이콘만, 듣는 중에는 연한 빨강 바탕 + 빨강 아이콘 + 바깥으로 번지는 고리(동작 줄이기면 고리 없음).
// 한 번 누르면 듣고, 다시 누르면 멈춘다(aria-pressed). 쓸 수 없는 브라우저면 부모가 그리지 않는다.
import { Mic } from '../../ui/index.ts';
import { BaseTooltip, TooltipPopup } from '../../ui/Tooltip.tsx';
import styles from './VoiceButton.module.css';

interface Props {
  listening: boolean;
  onToggle: () => void;
}

export function VoiceButton({ listening, onToggle }: Props) {
  const label = listening ? '듣기 멈추기' : '음성으로 입력';
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger
        type="button"
        className={styles.voice}
        aria-label={label}
        aria-pressed={listening}
        data-listening={listening ? '' : undefined}
        onClick={onToggle}
      >
        <Mic size={18} aria-hidden="true" />
      </BaseTooltip.Trigger>
      <TooltipPopup
        side="top"
        content={
          listening ? (
            '듣기 멈추기 (Esc)'
          ) : (
            <>
              음성으로 입력
              <span className={styles.tipNote}>말한 소리는 브라우저 회사 서버에서 글자로 바뀔 수 있어요</span>
            </>
          )
        }
      />
    </BaseTooltip.Root>
  );
}
