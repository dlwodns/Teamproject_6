// 에이전트 패널(진입 틀만, FE-D13 [제안]). '준비 중' 자리표시만 두고 입력창 · 결과 카드 · 음성 버튼 · API 호출은 넣지 않는다(FE-7 · FE-8).
// 모달이 아니다: 넓은 화면에서는 본문과 나란히, 좁은 화면에서는 본문 위에 겹쳐 보이며 배경 조작을 막지 않는다.
import { useEffect, useRef } from 'react';
import { AGENT_CLOSE_LABEL, AGENT_NAME, AgentIcon } from './agentBrand.tsx';

interface Props {
  onClose: () => void;
}

export function AgentPanel({ onClose }: Props) {
  const titleRef = useRef<HTMLHeadingElement>(null);

  // 열리면 패널 제목으로 포커스를 옮겨 화면 읽기 프로그램이 패널 이름을 읽게 한다
  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  return (
    <aside id="agent-panel" className="agent" aria-labelledby="agent-panel-title">
      <div className="agent-head">
        <span className="agent-head-icon">
          <AgentIcon size={18} />
        </span>
        <h2 id="agent-panel-title" ref={titleRef} tabIndex={-1}>
          {AGENT_NAME}
        </h2>
        <span className="badge-soon">준비 중</span>
        <button type="button" className="btn btn-icon btn-sm" aria-label={AGENT_CLOSE_LABEL} onClick={onClose}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="agent-body">
        <p>에이전트 기능은 준비 중입니다.</p>
        <p className="note">닫기 버튼이나 Esc로 닫을 수 있습니다.</p>
      </div>
    </aside>
  );
}
