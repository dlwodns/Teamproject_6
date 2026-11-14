// 브라우저 음성인식 어댑터 (D29 1차 · FE-D28): Web Speech API(SpeechRecognition, 크롬 · 엣지는 webkit 접두사).
// 크롬은 소리를 구글 서버로 보내 글자로 바꾼다 — 그래서 🎤 말풍선에 그 사실을 적는다(기획 detail 1.2절 '음성').
// 말을 멈추고 SILENCE_MS가 지나면 스스로 멈추고, 아무리 길어도 MAX_MS에서 끊는다.
import type { SttAdapter, SttErrorCode, SttHandlers, SttSession } from '../stt.ts';

export const SILENCE_MS = 2000;
export const MAX_MS = 60_000;

// lib.dom의 SpeechRecognition 타입은 브라우저마다 달라서, 쓰는 것만 좁게 적는다
interface ResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  readonly [index: number]: { readonly transcript: string } | undefined;
}
interface ResultEventLike {
  readonly results: { readonly length: number; readonly [index: number]: ResultLike | undefined };
}
export interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: ResultEventLike) => void) | null;
  onerror: ((e: { readonly error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
export type RecognitionCtor = new () => RecognitionLike;

interface SpeechGlobal {
  SpeechRecognition?: RecognitionCtor;
  webkitSpeechRecognition?: RecognitionCtor;
  isSecureContext?: boolean;
}

/** 이 브라우저의 SpeechRecognition 생성자. 없으면 null(🎤를 숨긴다) */
export function recognitionCtorOf(scope: SpeechGlobal | undefined): RecognitionCtor | null {
  return scope?.SpeechRecognition ?? scope?.webkitSpeechRecognition ?? null;
}

/** 브라우저 오류 이름 → 화면이 구분하는 이유. 'aborted'(우리가 끊음)는 오류가 아니다 */
export function errorCodeOf(error: string): SttErrorCode | null {
  switch (error) {
    case 'aborted':
      return null;
    case 'not-allowed':
    case 'service-not-allowed':
      return 'not-allowed';
    case 'no-speech':
      return 'no-speech';
    case 'audio-capture':
      return 'audio-capture';
    case 'network':
      return 'network';
    default:
      return 'unknown';
  }
}

/** 결과 목록 전체를 확정 글자와 아직 바뀌는 글자로 나눈다(continuous 모드는 목록이 누적된다) */
export function splitResults(results: ResultEventLike['results']): { finalText: string; interimText: string } {
  let finalText = '';
  let interimText = '';
  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    const text = r?.[0]?.transcript ?? '';
    if (r?.isFinal) finalText += ` ${text}`;
    else interimText += ` ${text}`;
  }
  return { finalText: finalText.trim(), interimText: interimText.trim() };
}

interface Timers {
  set: (fn: () => void, ms: number) => unknown;
  clear: (id: unknown) => void;
}
const realTimers: Timers = {
  set: (fn, ms) => setTimeout(fn, ms),
  clear: (id) => clearTimeout(id as ReturnType<typeof setTimeout>),
};

/** scope는 보통 window. 음성인식이 없는 브라우저면 null */
export function createBrowserStt(scope: SpeechGlobal | undefined = globalThis as SpeechGlobal, timers: Timers = realTimers): SttAdapter | null {
  const Ctor = recognitionCtorOf(scope);
  if (!Ctor) return null;
  return {
    mode: 'browser',
    start(lang: string, h: SttHandlers): SttSession {
      let ended = false;
      let silenceTimer: unknown = null;
      let maxTimer: unknown = null;
      const finish = () => {
        if (ended) return;
        ended = true;
        timers.clear(silenceTimer);
        timers.clear(maxTimer);
        h.onEnd();
      };

      // http 주소(공유 서버 IP 등)에서는 크롬이 권한도 묻지 않고 not-allowed로 끝낸다 → 이유를 따로 알린다
      if (scope?.isSecureContext === false) {
        queueMicrotask(() => {
          h.onError('insecure');
          finish();
        });
        const noop = () => {};
        return { stop: noop, abort: noop };
      }

      const rec = new Ctor();
      rec.lang = lang;
      rec.continuous = true; // 말 사이에 잠깐 쉬어도 끊지 않는다. 끝은 SILENCE_MS로 정한다
      rec.interimResults = true; // 말하는 동안 입력칸에 글자가 바로 보인다
      rec.maxAlternatives = 1;

      const armSilence = () => {
        timers.clear(silenceTimer);
        silenceTimer = timers.set(() => rec.stop(), SILENCE_MS);
      };
      maxTimer = timers.set(() => rec.stop(), MAX_MS);

      rec.onresult = (e) => {
        if (ended) return;
        const { finalText, interimText } = splitResults(e.results);
        h.onText(finalText, interimText);
        armSilence();
      };
      rec.onerror = (e) => {
        if (ended) return;
        const code = errorCodeOf(e.error);
        if (code) h.onError(code);
      };
      rec.onend = finish;

      try {
        rec.start();
      } catch {
        // 이미 듣는 중인 인스턴스 등 — 드문 경우라 일반 실패로 알린다
        h.onError('unknown');
        finish();
      }

      return {
        stop: () => {
          if (!ended) rec.stop();
        },
        abort: () => {
          if (ended) return;
          rec.onresult = null;
          rec.onerror = null;
          rec.abort();
          finish();
        },
      };
    },
  };
}
