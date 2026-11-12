// 에이전트 패널 G — 자리만(FE-13). 대화 · 단계 · 확인 카드 · 입력은 FE-7 · FE-8이 이 안을 채운다(components.md 4.4).
// 패널 안에 role="status" 영역을 처음부터 하나 두고 단계가 바뀔 때만 문구를 바꾼다(FE-7).
import { PANEL_WIDTH } from '../../app/panel.tsx';
import { ComingSoon } from '../../components/ComingSoon.tsx';
import { SidePanel } from '../../ui/index.ts';
import { AGENT_NAME } from './agentBrand.tsx';

interface Props {
  id: string;
  onClose: () => void;
}

export function AgentPanel({ id, onClose }: Props) {
  return (
    <SidePanel id={id} title={AGENT_NAME} width={PANEL_WIDTH.agent} onClose={onClose}>
      <ComingSoon>
        <p>말이나 글로 시키면 처리하는 기능을 준비하고 있어요.</p>
      </ComingSoon>
    </SidePanel>
  );
}
