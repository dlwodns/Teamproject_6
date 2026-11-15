// 에이전트 입력 (components.md 4.4 PromptInput · 6절). 테두리 하나 안에 입력칸과 보내기 단추를 둔다(채팅 입력 관례).
// 입력칸은 글 길이에 맞춰 늘어나고(최대 6줄) 손잡이로 크기를 바꾸지 않는다. Enter = 보내기, Shift+Enter = 줄바꿈,
// 한글 조합 중 Enter는 보내지 않는다(agentKeys.ts). 명령이 진행 중이면 보내기가 aria-disabled(포커스는 남는다) —
// 글은 미리 써 둘 수 있고, 끝난 뒤 보내면 된다.
// 🎤(FE-8): 들은 말이 입력칸에 바로 써지고, 보내기는 사람이 누른다. 듣는 중에 글을 고치거나 보내면 듣기를 끊는다.
import { useCallback, useId, useRef, useState, type FormEvent, type KeyboardEvent, type Ref } from 'react';
import { ArrowUp, LiveRegion, VisuallyHidden } from '../../ui/index.ts';
import { useVoiceInput } from '../voice/useVoiceInput.ts';
import { VoiceButton } from '../voice/VoiceButton.tsx';
import { voiceHint } from '../voice/voiceText.ts';
import { isSendKey } from './agentKeys.ts';
import styles from './PromptInput.module.css';

interface Props {
  busy: boolean;
  /** 보냈으면 true(입력칸을 비운다) */
  onSubmit: (text: string) => boolean;
  inputRef: Ref<HTMLTextAreaElement>;
  /** 입력칸 안내 글자(캐치봇 화면은 '캐치봇에게 말하기…') */
  placeholder?: string;
}

export function PromptInput({ busy, onSubmit, inputRef, placeholder = '요청할 업무를 입력해 주십시오. 예: 김 팀장님 건 다 처리했어' }: Props) {
  const [text, setText] = useState('');
  const inputId = useId();
  const hintId = useId();
  const empty = !text.trim();
  const textRef = useRef(text);
  textRef.current = text;
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const setAreaRef = useCallback(
    (el: HTMLTextAreaElement | null) => {
      areaRef.current = el;
      if (typeof inputRef === 'function') inputRef(el);
      else if (inputRef) inputRef.current = el;
    },
    [inputRef],
  );

  const voice = useVoiceInput({
    getText: () => textRef.current,
    setText,
    onDone: (heard) => {
      const el = areaRef.current;
      if (!heard || !el) return;
      // 들은 글 끝에 커서를 두어 바로 고치거나 Enter로 보낼 수 있게
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    },
  });
  const hint = voiceHint(voice);

  const send = () => {
    if (busy || empty) return;
    voice.abort();
    if (onSubmit(text)) setText('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    const native = e.nativeEvent;
    if (e.key === 'Escape' && voice.listening && !native.isComposing) {
      // 듣기만 멈춘다
      e.preventDefault();
      voice.stop();
      return;
    }
    if (!isSendKey({ key: e.key, shiftKey: e.shiftKey, altKey: e.altKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, isComposing: native.isComposing, keyCode: native.keyCode })) return;
    e.preventDefault();
    send();
  };

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };

  return (
    <form
      className={styles.form}
      onSubmit={onFormSubmit}
      data-listening={voice.listening ? '' : undefined}
      onKeyDown={(e) => {
        // 포커스가 🎤 단추에 있을 때의 Esc
        if (e.key === 'Escape' && voice.listening && e.target !== areaRef.current) {
          e.preventDefault();
          voice.stop();
        }
      }}
    >
      <label htmlFor={inputId}>
        <VisuallyHidden>캐치봇에게 시킬 일</VisuallyHidden>
      </label>
      <textarea
        id={inputId}
        ref={setAreaRef}
        className={styles.input}
        value={text}
        rows={1}
        placeholder={voice.listening ? '말씀하세요…' : placeholder}
        aria-describedby={hintId}
        onChange={(e) => {
          // 듣는 중에 직접 고치면 사람이 이긴다: 듣기를 끊고 뒤늦은 글자는 버린다
          voice.abort();
          if (voice.error) voice.clearError();
          setText(e.target.value);
        }}
        onKeyDown={onKeyDown}
      />
      <div className={styles.bar}>
        <span id={hintId} className={styles.hint} data-tone={voice.error ? 'error' : voice.listening ? 'listening' : undefined}>
          {hint ?? 'Enter 보내기 · Shift+Enter 줄바꿈'}
        </span>
        {voice.supported && <VoiceButton listening={voice.listening} onToggle={voice.toggle} />}
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
      <LiveRegion>{voice.error ? hint : voice.announcement}</LiveRegion>
    </form>
  );
}
