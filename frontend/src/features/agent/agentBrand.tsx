// 에이전트 이름 · 아이콘 자리. 이름과 로고가 정해지면 이 파일만 바꾸면 상단 바 버튼 · 패널 제목에 함께 반영된다.
import { Sparkles } from '../../ui/index.ts';

export const AGENT_NAME = '캐치봇'; // 11-14 이름 확정

/** ✦ 에이전트 아이콘(장식) */
export function AgentIcon({ size = 16 }: { size?: 16 | 20 }) {
  return <Sparkles size={size} aria-hidden="true" />;
}
