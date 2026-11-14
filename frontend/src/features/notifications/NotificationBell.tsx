// 상단 바 🔔 자리 — 빈 틀(FE-13). 알림 센터(FE-10, 이재운)가 이 파일 안을 채운다:
// 리마인더 수 CountBadge(10 이상 9+, 버튼 이름에도 "알림 센터, 리마인더 3개"), Tabs [리마인더 | 알림], 리마인더 줄 등(components.md 4.5).
// 리마인더 API(BE-12)가 없으면 실제 서버 모드에서 숫자 · 리마인더 탭을 숨긴다.
import { ComingSoon } from '../../components/ComingSoon.tsx';
import { Bell, IconButton, Popover } from '../../ui/index.ts';

export function NotificationBell() {
  return (
    <Popover title="알림 센터" trigger={<IconButton size="lg" label="알림 센터 열기" icon={<Bell size={20} aria-hidden="true" />} />}>
      <ComingSoon>
        <p>리마인더와 알림이 연결되면 여기에 보여요.</p>
      </ComingSoon>
    </Popover>
  );
}
