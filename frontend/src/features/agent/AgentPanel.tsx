// 에이전트 패널 G (components.md 4.4 · wireframe 13-4 · UX-D8 · D37). 앱 틀(AppLayout)이 <AgentPanel id onClose />로 연다.
// 안의 대화 · 탭 · 입력은 AgentWorkspace가 그리고, 패널은 제목 줄(크게 보기 · ✕)만 맡는다.
// 데이터는 api.runAgentCommand(POST /api/agent/command) 하나다. 모의 · 실제는 클라이언트(api/selectApi.ts)만 바뀐다.
//
// FE-11(PL-16 · D50): 패널 위쪽에 [대화 · 제안 · 기록] 탭. 11-15: '에이전트가 아는 것' 화면은 없앴다(설정의 '메일 내용 분석' 켜고 끄기만).
// FE-15: 제목 줄 [크게 보기] → 에이전트 화면(#/agent)으로 옮긴다. 대화는 하나라 그대로 이어지고, 패널은 앱 틀이 닫는다.
import { useNavigate } from 'react-router';
import { PANEL_WIDTH } from '../../app/panel.tsx';
import { IconButton, Maximize, SidePanel } from '../../ui/index.ts';
import { AGENT_NAME } from './agentBrand.tsx';
import { AgentWorkspace } from './AgentWorkspace.tsx';
import { AGENT_PATH } from './useAgentCompletion.ts';

interface Props {
  id: string;
  onClose: () => void;
}

export function AgentPanel({ id, onClose }: Props) {
  const navigate = useNavigate();

  const headerExtra = (
    <IconButton
      label="크게 보기"
      icon={<Maximize size={18} aria-hidden="true" />}
      onClick={() => {
        onClose();
        void navigate(AGENT_PATH);
      }}
    />
  );

  return (
    <SidePanel id={id} title={AGENT_NAME} width={PANEL_WIDTH.agent} onClose={onClose} headerExtra={headerExtra}>
      <AgentWorkspace />
    </SidePanel>
  );
}
