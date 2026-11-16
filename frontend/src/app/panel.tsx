// 패널 자리 (components.md 4.1): 더보기 사이드바. 11-15 캐치봇 패널을 없애 이제 더보기 하나다(reminders.md 12.8). 열린 패널 종류는 앱 상태로 두고 주소에는 넣지 않는다.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type PanelKind = 'more';

/** 더보기 사이드바(LP)에 넘기는 것: 칸 이름 · 건수가 든 제목과 그 칸 전부 */
export interface MorePanelPayload {
  title: string;
  content: ReactNode;
}

export interface PanelState {
  kind: PanelKind | null;
  payload: MorePanelPayload | null;
}

export interface PanelApi extends PanelState {
  open: (kind: 'more', payload: MorePanelPayload) => void;
  close: () => void;
}

/** 패널 폭 토큰. 1280px 이상에서 본문을 이만큼 민다 */
export const PANEL_WIDTH: Record<PanelKind, string> = {
  more: 'var(--drawer-width)',
};

/** 패널 요소 id(여는 버튼의 aria-controls) */
export const PANEL_ID = 'app-panel';

const PanelContext = createContext<PanelApi | null>(null);

export function PanelProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PanelState>({ kind: null, payload: null });

  const open = useCallback((kind: PanelKind, payload: MorePanelPayload) => setState({ kind, payload }), []);

  const close = useCallback(() => setState({ kind: null, payload: null }), []);

  const api = useMemo<PanelApi>(() => ({ ...state, open, close }), [state, open, close]);
  return <PanelContext.Provider value={api}>{children}</PanelContext.Provider>;
}

export function usePanel(): PanelApi {
  const ctx = useContext(PanelContext);
  if (!ctx) throw new Error('usePanel은 PanelProvider 안에서만 쓴다');
  return ctx;
}
