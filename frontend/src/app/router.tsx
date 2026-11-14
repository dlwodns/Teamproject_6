// 주소 (components.md 4.1 · FE-D16): React Router 8 해시 라우터. 배포 서버 설정 없이 새로고침이 된다.
// 메일을 고르면 주소에 항목이 쌓여 뒤로 가기 · Alt+←가 별도 코드 없이 동작한다(UX-D12).
// 모르는 주소와 #/는 대시보드로 바꾼다(replace — 뒤로 가기에 남기지 않음).
import { createHashRouter, Navigate } from 'react-router';
import { AgentPage } from '../pages/agent/AgentPage.tsx';
import { CalendarPage } from '../pages/calendar/CalendarPage.tsx';
import { DashboardPage } from '../pages/dashboard/DashboardPage.tsx';
import { MailPage } from '../pages/mail/MailPage.tsx';
import { SettingsPage } from '../pages/settings/SettingsPage.tsx';
import { AppLayout } from './AppLayout.tsx';

export const router = createHashRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'mail', element: <MailPage /> },
      { path: 'mail/:box', element: <MailPage /> },
      { path: 'mail/:box/:mailId', element: <MailPage /> },
      { path: 'calendar', element: <CalendarPage /> }, // FE-12 · D56
      { path: 'agent/*', element: <AgentPage /> }, // FE-16: 메뉴 · 리마인더 묶음 · 고른 항목(features/agent/agentRoutes.ts)
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/dashboard" replace /> },
    ],
  },
]);
