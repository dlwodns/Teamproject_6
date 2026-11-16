// 에이전트 화면 주소 (FE-16 · UX-D19). 순수 함수, node --test 대상.
//   #/agent                          → #/agent/reminders(바꿔 쓴다)
//   #/agent/reminders/:channel?/:key?  업무 유형 채널(all은 바로가기용, 화면이 항목의 채널로 바꿔 씀) · 고른 항목(키는 인코딩)
//   #/agent/briefing · chat · history  (11-15: 초안은 메일 답장 칸으로, '에이전트가 아는 것'은 설정의 켜고 끄기로 옮겼다)
// 메뉴 · 항목을 고르면 주소에 항목이 쌓여 뒤로 가기가 메뉴 이동을 되돌린다(메일 화면과 같은 방식, UX-D12).
import { CHANNELS, type ChannelFilter } from '../reminders/reminderModel.ts';

export const AGENT_MENUS = ['reminders', 'briefing', 'chat', 'history'] as const;
export type AgentMenu = (typeof AGENT_MENUS)[number];

export type AgentRoute =
  | { menu: 'reminders'; group: ChannelFilter; key: string | null }
  | { menu: Exclude<AgentMenu, 'reminders'> };

export const AGENT_BASE = '/agent';

/** 주소 뒷부분(`reminders/due/overdue%3Atask%3A1`) → 메뉴. 모르는 주소면 null(리마인더 전체로 바꿔 쓴다) */
export function parseAgentPath(splat: string): AgentRoute | null {
  const parts = splat.split('/').filter(Boolean);
  const [menu, a, b] = parts;
  if (menu === 'reminders') {
    if (parts.length > 3) return null;
    const group: ChannelFilter | null = a === undefined || a === 'all' ? 'all' : (CHANNELS as readonly string[]).includes(a) ? (a as ChannelFilter) : null;
    if (group === null) return null;
    let key: string | null = null;
    if (b !== undefined) {
      try {
        key = decodeURIComponent(b);
      } catch {
        return null;
      }
    }
    return { menu: 'reminders', group, key };
  }
  if (parts.length === 1 && (AGENT_MENUS as readonly string[]).includes(menu ?? '')) return { menu: menu as Exclude<AgentMenu, 'reminders'> };
  return null;
}

export function reminderPath(group: ChannelFilter = 'all', key: string | null = null): string {
  return key === null ? `${AGENT_BASE}/reminders/${group}` : `${AGENT_BASE}/reminders/${group}/${encodeURIComponent(key)}`;
}

export function menuPath(menu: AgentMenu): string {
  return menu === 'reminders' ? reminderPath() : `${AGENT_BASE}/${menu}`;
}

export const MENU_LABEL: Record<AgentMenu, string> = {
  reminders: '리마인더',
  briefing: '업무 요약 · 회고',
  chat: '대화',
  history: '기록',
};
