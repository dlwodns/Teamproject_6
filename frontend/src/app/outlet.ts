// 앱 틀(AppLayout)이 화면에 넘기는 값. 화면은 useAppOutlet()으로 읽는다.
import { useOutletContext } from 'react-router';

export interface AppOutletContext {
  /** 메일 화면 왼쪽 메일함이 열려 있는가. Ctrl+B(⌘B) · [▥]로 바꾼다 */
  mailboxOpen: boolean;
  setMailboxOpen: (open: boolean) => void;
  toggleMailbox: () => void;
}

export function useAppOutlet(): AppOutletContext {
  return useOutletContext<AppOutletContext>();
}
