// 음성인식 어댑터 약속 (D29 · FE-D28). 브라우저 방식과 서버 방식이 같은 모양을 따라서, 화면은 어느 쪽인지 모른다.
// 음성은 글자로 바뀐 뒤 글로 친 명령과 같은 길(입력칸 → 보내기)을 탄다. 보내기는 언제나 사람이 누른다.

/** 화면이 구분하는 실패 이유. 문구는 voiceText.ts의 voiceErrorText가 정한다 */
export type SttErrorCode =
  | 'not-allowed' // 마이크 권한을 막음
  | 'insecure' // http 주소라 브라우저가 마이크를 열지 않음
  | 'no-speech' // 말소리를 듣지 못함
  | 'audio-capture' // 마이크 장치가 없음
  | 'network' // 음성인식 서버에 닿지 못함
  | 'unknown';

export interface SttHandlers {
  /** 이번 듣기에서 지금까지 확정된 글자와, 아직 바뀔 수 있는 글자(둘 다 누적) */
  onText: (finalText: string, interimText: string) => void;
  onError: (code: SttErrorCode) => void;
  /** 듣기가 끝났다(스스로 멈춤 · stop · 오류 모두). 한 번만 온다 */
  onEnd: () => void;
}

export interface SttSession {
  /** 듣기를 멈춘다. 이미 들은 말은 마저 글자로 바꿔 onText로 보낸 뒤 onEnd */
  stop: () => void;
  /** 바로 끊는다. 뒤늦은 글자는 버린다 */
  abort: () => void;
}

export interface SttAdapter {
  readonly mode: SttMode;
  start: (lang: string, handlers: SttHandlers) => SttSession;
}

export type SttMode = 'browser' | 'server';

/** VITE_STT_MODE 값 → 방식. 비었거나 모르는 값이면 브라우저 방식(D29 1차) */
export function sttModeOf(raw: string | undefined): SttMode {
  return raw?.trim().toLowerCase() === 'server' ? 'server' : 'browser';
}
