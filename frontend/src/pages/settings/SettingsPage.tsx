import { ComingSoon } from '../../components/ComingSoon.tsx';

// 설정 화면 자리(FE-6이 채운다). 이 화면에서는 에이전트 버튼 · 패널이 숨는다(앱 틀).
export function SettingsPage() {
  return (
    <ComingSoon title="설정">
      <p>설정 화면은 아직 만들지 않았어요.</p>
      <ul>
        <li>아침 알림 시각 · 무응답 기준일</li>
        <li>상급자 · 즐겨찾기</li>
      </ul>
    </ComingSoon>
  );
}
