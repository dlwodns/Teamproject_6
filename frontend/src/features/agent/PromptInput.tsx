// 에이전트 입력 (components.md 4.4 PromptInput · 6절). 여러 줄 입력, Enter = 보내기, Shift+Enter = 줄바꿈,
// 한글 조합 중 Enter는 보내지 않는다(agentKeys.ts). 명령이 진행 중이면 [보내기]가 aria-disabled(포커스는 남는다) —
// 글은 미리 써 둘 수 있고, 끝난 뒤 보내면 된다.
import { useId, useState, type FormEvent, type KeyboardEvent, type Ref } from 'react';
import { Button, VisuallyHidden } from '../../ui/index.ts';
import { isSendKey } from './agentKeys.ts';
import styles from './PromptInput.module.css';

interface Props {
  busy: boolean;
  /** 보냈으면 true(입력칸을 비운다) */
  onSubmit: (text: string) => boolean;
  inputRef: Ref<HTMLTextAreaElement>;
}

export function PromptInput({ busy, onSubmit, inputRef }: Props) {
  const [text, setText] = useState('');
  const inputId = useId();
  const hintId = useId();

  const send = () => {
    if (busy || !text.trim()) return;
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
        rows={2}
        placeholder="예: 김 팀장님 건 다 처리했어"
        aria-describedby={hintId}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <VisuallyHidden id={hintId}>Enter로 보내고 Shift+Enter로 줄을 바꿔요</VisuallyHidden>
      {/* FE-8 VoiceButton 자리: 🎤 버튼(듣는 중 · 글자를 이 입력칸에 넣고 사용자가 보내기를 누른다). 브라우저 음성 인식이 없으면 숨긴다 */}
      <Button type="submit" variant="primary" className={styles.send} aria-disabled={busy || undefined}>
        보내기
      </Button>
    </form>
  );
}
