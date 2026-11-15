// 업무 줄 · 확인사항 줄을 누르면 메일 화면의 그 메일로 간다(UX-D12 · wireframe 13-3).
// 주소에 항목을 쌓아(push) 뒤로 가기 · Alt+←로 대시보드에 돌아온다. 메일 화면은 state.from으로 [← 대시보드] 버튼을 보인다.
// 더보기 사이드바 안 줄이면 사이드바를 닫는다.
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { usePanel } from '../../app/panel.tsx';
import type { MailId } from '../../api/types.ts';

/** 메일 화면이 받는 이동 상태. 에이전트 화면(FE-15) 결과물 칸에서 열면 'agent'([← 에이전트]) */
export interface FromDashboardState {
  from: 'dashboard' | 'agent';
}

export function mailPath(mailId: MailId): string {
  return `/mail/inbox/${mailId}`;
}

export function useOpenMail(from: FromDashboardState['from'] = 'dashboard'): (mailId: MailId) => void {
  const navigate = useNavigate();
  const { kind, close } = usePanel();
  return useCallback(
    (mailId: MailId) => {
      if (kind === 'more') close();
      const state: FromDashboardState = { from };
      void navigate(mailPath(mailId), { state });
    },
    [navigate, kind, close, from],
  );
}
