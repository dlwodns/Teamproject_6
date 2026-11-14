// 에이전트 입력 (components.md 4.4 PromptInput · 6절). 테두리 하나 안에 입력칸과 보내기 단추를 둔다(채팅 입력 관례).
// 입력칸은 글 길이에 맞춰 늘어나고(최대 6줄) 손잡이로 크기를 바꾸지 않는다. Enter = 보내기, Shift+Enter = 줄바꿈,
// 한글 조합 중 Enter는 보내지 않는다(agentKeys.ts). 명령이 진행 중이면 보내기가 aria-disabled(포커스는 남는다) —
// 글은 미리 써 둘 수 있고, 끝난 뒤 보내면 된다.
import { useId, useState, type FormEvent, type KeyboardEvent, type Ref } from 'react';
import { ArrowUp, VisuallyHidden } from '../../ui/index.ts';
import { isSendKey } from './agentKeys.ts';
import styles from './PromptInput.module.css';

interface Props {
  busy: boolean;
  /** 보냈으면 true(입력칸을 비운다) */
  onSubmit: (text: string) => boolean;
  inputRef: Ref<HTMLTextAreaElement>;
  /** 빈 칸에 글을 쓰기 시작했을 때(패널이 대화 탭으로 옮긴다) */
  onTyping?: () => void;
  /** 입력칸 안내 글자(에이전트 화면은 '에이전트에게 말하기…') */
  placeholder?: string;
}

export function PromptInput({ busy, onSubmit, inputRef, onTyping, placeholder = '요청할 업무를 입력해 주십시오. 예: 김 팀장님 건 다 처리했어' }: Props) {
  const [text, setText] = useState('');
  const inputId = useId();
  const hintId = useId();
  const empty = !text.trim();

  const send = () => {
    if (busy || empty) return;
    if (onSubmit(text)) setText('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    const native = e.nativeEvent;
    if (!isSendKey({ key: e.key, shiftKey: e.shiftKey, altKey: e.altKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, isComposing: native.isComposing, keyCode: native.keyCode })) return;
    e.preventDefault();
    send();
  };

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };

  return (
    <form className={styles.form} onSubmit={onFormSubmit}>
      <label htmlFor={inputId}>
        <VisuallyHidden>에이전트에게 시킬 일</VisuallyHidden>
      </label>
      <textarea
        id={inputId}
        ref={inputRef}
        className={styles.input}
        value={text}
        rows={1}
        placeholder={placeholder}
        aria-describedby={hintId}
        onChange={(e) => {
          if (!text && e.target.value) onTyping?.();
          setText(e.target.value);
        }}
        onKeyDown={onKeyDown}
      />
      <div className={styles.bar}>
        <span id={hintId} className={styles.hint}>
          Enter 보내기 · Shift+Enter 줄바꿈
        </span>
        {/* FE-8 VoiceButton 자리: 🎤 단추(보내기 왼쪽). 브라우저 음성 인식이 없으면 숨긴다 */}
        <button
          type="submit"
          className={styles.send}
          aria-label="보내기"
          aria-disabled={busy || empty || undefined}
          data-ready={!busy && !empty ? '' : undefined}
        >
          <ArrowUp size={18} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
