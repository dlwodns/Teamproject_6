import { ComingSoon } from '../../components/ComingSoon.tsx';

export function MailPage() {
  return (
    <ComingSoon title="메일">
      <p>메일 화면은 아직 만들지 않았습니다.</p>
      <ul className="note">
        <li>메일 목록 · 원본 메일 보기</li>
        <li>답장 작성과 답장 후 완료 확인 팝업</li>
        <li>응답 대기 목록 — 담당 · 데이터가 정해진 뒤</li>
      </ul>
    </ComingSoon>
  );
}
