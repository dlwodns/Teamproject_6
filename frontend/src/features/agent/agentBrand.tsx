// 에이전트 이름 · 아이콘 자리. 이름과 로고는 기획(문규남)에서 정해 전달 예정이라 임시 값이다.
// 정해지면 이 파일만 바꾸면 원형 버튼 · 패널 제목에 함께 반영된다.

export const AGENT_NAME = '에이전트';
export const AGENT_OPEN_LABEL = `${AGENT_NAME} 열기`;
export const AGENT_CLOSE_LABEL = `${AGENT_NAME} 닫기`;

export function AgentIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8zM19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9z" />
    </svg>
  );
}
