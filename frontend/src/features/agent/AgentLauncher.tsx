// 오른쪽 아래 원형 버튼(FE-D13 [제안]). 설정 화면에서는 App이 그리지 않는다.
// 패널(#agent-panel)이 열려 있는 동안 이 버튼은 그리지 않으므로(App.tsx) aria-controls로 패널을 가리키지 않는다.
import type { Ref } from 'react';
import { AGENT_OPEN_LABEL, AgentIcon } from './agentBrand.tsx';

interface Props {
  onOpen: () => void;
  buttonRef: Ref<HTMLButtonElement>;
}

export function AgentLauncher({ onOpen, buttonRef }: Props) {
  return (
    <button ref={buttonRef} type="button" className="agent-fab" aria-label={AGENT_OPEN_LABEL} onClick={onOpen}>
      <AgentIcon />
      <span className="agent-fab-tip" aria-hidden="true">
        {AGENT_OPEN_LABEL}
      </span>
    </button>
  );
}
