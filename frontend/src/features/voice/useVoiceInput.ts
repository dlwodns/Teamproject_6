// 음성 입력 상태 (FE-8 · FE-D28). 듣기 시작 때 입력칸 글을 기억해 두고, 들은 말을 그 뒤에 붙여 계속 바꿔 쓴다.
// 사용자가 글을 고치거나 보내면 듣기를 바로 끊고 뒤늦은 글자는 버린다(보낸 칸이 다시 채워지지 않게).
import { useCallback, useEffect, useRef, useState } from 'react';
import { createBrowserStt } from './adapters/browserStt.ts';
import { sttModeOf, type SttAdapter, type SttErrorCode, type SttSession } from './stt.ts';
import { joinSpoken } from './voiceText.ts';

const LANG = 'ko-KR';

/** 설정값(VITE_STT_MODE)에 맞는 어댑터. 서버 방식(ai /stt)은 아직 없어서 null → 🎤를 숨긴다 */
function pickAdapter(): SttAdapter | null {
  const mode = sttModeOf(import.meta.env.VITE_STT_MODE);
  if (mode === 'server') return null; // AI-8 · BE /voice/stt가 생기면 serverStt 어댑터를 여기서 고른다
  return createBrowserStt(typeof window === 'undefined' ? undefined : window);
}

interface Options {
  /** 지금 입력칸 글 */
  getText: () => string;
  setText: (text: string) => void;
  /** 듣기가 끝나고 글자가 들어왔을 때(입력칸으로 포커스를 돌린다) */
  onDone?: (heard: boolean) => void;
}

export interface VoiceInput {
  /** 이 브라우저 · 설정에서 쓸 수 있으면 true. false면 🎤를 그리지 않는다 */
  supported: boolean;
  listening: boolean;
  error: SttErrorCode | null;
  /** 화면 읽기에 한 번 읽힐 문구 */
  announcement: string;
  toggle: () => void;
  /** 듣기를 멈추고 들은 말은 남긴다(Esc · 🎤 다시 누름) */
  stop: () => void;
  /** 바로 끊고 뒤늦은 글자는 버린다(직접 고침 · 보내기) */
  abort: () => void;
  clearError: () => void;
}

export function useVoiceInput({ getText, setText, onDone }: Options): VoiceInput {
  const [adapter] = useState(pickAdapter);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<SttErrorCode | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const session = useRef<SttSession | null>(null);
  // 콜백이 늘 최신 함수를 부르도록(듣는 동안 부모가 다시 그려져도)
  const latest = useRef({ getText, setText, onDone });
  latest.current = { getText, setText, onDone };

  const start = useCallback(() => {
    if (!adapter || session.current) return;
    const before = latest.current.getText();
    let heard = false;
    let failed = false;
    setError(null);
    setListening(true);
    setAnnouncement('듣는 중이에요. 말씀하세요');
    const s = adapter.start(LANG, {
      onText: (finalText, interimText) => {
        if (session.current !== s) return;
        if (finalText || interimText) heard = true;
        latest.current.setText(joinSpoken(before, finalText, interimText));
      },
      onError: (code) => {
        if (session.current !== s) return;
        failed = true;
        setError(code);
      },
      onEnd: () => {
        if (session.current !== s) return;
        session.current = null;
        setListening(false);
        if (!heard && !failed) setError('no-speech');
        setAnnouncement(heard ? '받아 적었어요. 확인하고 보내 주세요' : '듣기를 멈췄어요');
        latest.current.onDone?.(heard);
      },
    });
    session.current = s;
  }, [adapter]);

  const stop = useCallback(() => {
    session.current?.stop();
  }, []);

  const abort = useCallback(() => {
    const s = session.current;
    if (!s) return;
    session.current = null; // 먼저 끊어 두면 abort가 부르는 onEnd도 무시된다
    s.abort();
    setListening(false);
  }, []);

  const toggle = useCallback(() => {
    if (session.current) stop();
    else start();
  }, [start, stop]);

  const clearError = useCallback(() => setError(null), []);

  useEffect(() => () => {
    const s = session.current;
    session.current = null;
    s?.abort();
  }, []);

  return { supported: adapter !== null, listening, error, announcement, toggle, stop, abort, clearError };
}
