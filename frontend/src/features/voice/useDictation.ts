// 브라우저 음성 받아쓰기(11-15, 메일 답장 칸). Web Speech API(SpeechRecognition)만 쓴다 — 서버 · 라이브러리 없음.
// 크롬 · 엣지 · 사파리는 webkit 접두어로 있고, 파이어폭스에는 없다 → supported=false면 부르는 쪽이 마이크 단추를 숨긴다.
// 확정된 문장(isFinal)만 onText로 넘긴다. 말하는 중간 글자는 넘기지 않는다(입력칸이 흔들리지 않게).
import { useCallback, useEffect, useRef, useState } from 'react';

interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}
type RecognitionCtor = new () => Recognition;

function ctor(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function useDictation(onText: (text: string) => void, onError?: (code: string) => void) {
  const supported = ctor() !== null;
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const handlers = useRef({ onText, onError });
  handlers.current = { onText, onError };

  const stop = useCallback(() => rec.current?.stop(), []);
  const start = useCallback(() => {
    const C = ctor();
    if (!C || rec.current) return;
    const r = new C();
    r.lang = 'ko-KR';
    r.continuous = true;
    r.interimResults = false;
    r.onresult = (e) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const res = e.results[i];
        if (res?.isFinal) text += res[0]?.transcript ?? '';
      }
      if (text.trim()) handlers.current.onText(text.trim());
    };
    r.onerror = (e) => handlers.current.onError?.(e.error);
    r.onend = () => {
      rec.current = null;
      setListening(false);
    };
    rec.current = r;
    r.start();
    setListening(true);
  }, []);

  useEffect(() => () => rec.current?.stop(), []);
  return { supported, listening, start, stop };
}
