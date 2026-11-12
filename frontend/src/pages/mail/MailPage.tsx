import { useParams } from 'react-router';
import { useAppOutlet } from '../../app/outlet.ts';
import { ComingSoon } from '../../components/ComingSoon.tsx';

// 메일 화면 자리(FE-5가 채운다). 주소 #/mail/:box/:mailId와 메일함 열고 닫기(Ctrl+B · ⌘B)는 앱 틀이 이미 준다.
export function MailPage() {
  const { box, mailId } = useParams();
  const { mailboxOpen } = useAppOutlet();
  return (
    <ComingSoon title="메일">
      <p>메일 화면은 아직 만들지 않았어요.</p>
      <ul>
        <li>메일함: {box ?? '받은편지함'}{mailId ? ` · 고른 메일 ${mailId}` : ''}</li>
        <li>왼쪽 메일함 {mailboxOpen ? '열림' : '닫힘'} — Ctrl+B · ⌘B로 열고 닫기</li>
      </ul>
    </ComingSoon>
  );
}
