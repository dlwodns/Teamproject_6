// 음성 입력의 글자 규칙 (FE-8 · FE-D28). 화면 없이 테스트한다(voiceText.test.ts).
import type { SttErrorCode } from './stt.ts';

/** 브라우저가 돌려준 조각을 한 줄로: 줄바꿈 · 겹친 띄어쓰기를 한 칸으로 */
export function tidySpoken(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/**
 * 듣기 전에 입력칸에 있던 글 뒤에 들은 말을 붙인다. 앞 글이 공백으로 끝나지 않으면 한 칸 띄운다.
 * 들은 말이 없으면 앞 글을 그대로 둔다(듣기를 눌렀다고 사용자가 쓴 글이 바뀌지 않는다).
 */
export function joinSpoken(before: string, finalText: string, interimText: string): string {
  const spoken = tidySpoken(`${finalText} ${interimText}`);
  if (!spoken) return before;
  if (!before.trim()) return spoken;
  return /\s$/.test(before) ? `${before}${spoken}` : `${before} ${spoken}`;
}

/** 실패 문구: 무슨 일인지 + 사용자가 할 일. 다시 하려면 🎤를 한 번 더 누르면 된다.
 *  화면 문구에는 그림 문자(🎤)를 쓰지 않는다 — 글꼴에 따라 네모로 깨지고 색이 하나 더 생긴다 */
export function voiceErrorText(code: SttErrorCode): string {
  switch (code) {
    case 'not-allowed':
      return '마이크 권한이 꺼져 있어요. 주소창 왼쪽 아이콘에서 마이크를 허용해 주세요';
    case 'insecure':
      return '보안 연결(https)이 아닌 주소라 브라우저가 마이크를 막았어요. https 주소로 열어 주세요';
    case 'no-speech':
      return '말소리를 듣지 못했어요. 마이크를 다시 눌러 말해 주세요';
    case 'audio-capture':
      return '마이크를 찾지 못했어요. 연결을 확인해 주세요';
    case 'network':
      return '음성인식 서버에 닿지 못했어요. 인터넷 연결을 확인해 주세요';
    default:
      return '음성을 글자로 바꾸지 못했어요. 다시 눌러 주세요';
  }
}

/** 입력칸 아래 안내 줄. 오류가 있으면 오류, 듣는 중이면 듣는 중, 아니면 키 안내 */
export function voiceHint(state: { listening: boolean; error: SttErrorCode | null }): string | null {
  if (state.error) return voiceErrorText(state.error);
  // 패널 폭(360px)에서 한 줄에 들어가게 짧게. 멈추는 법(다시 누름 · Esc)은 🎤 말풍선이 말한다
  if (state.listening) return '듣는 중… 말을 멈추면 끝나요';
  return null;
}
