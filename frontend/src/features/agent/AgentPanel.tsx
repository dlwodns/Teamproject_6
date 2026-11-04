// AI 에이전트 패널(준비 중 · 임시 UI). 입력은 받지만 보내지 않는다.
// 결과 카드 자리는 에이전트 응답 형식(#6 BE 명세 · AI-9)이 정해진 뒤 채운다. 가짜 실행 결과를 보여 주지 않는다.
import { useEffect, useId, useRef } from 'react';

interface Props {
  draft: string;
  onDraftChange: (value: string) => void;
  onClose: () => void;
}

export function AgentPanel({ draft, onDraftChange, onClose }: Props) {
  const titleId = useId();
  const inputId = useId();
  const hintId = useId();
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <aside id="agent-panel" className="agent" aria-labelledby={titleId}>
      <div className="agent-head">
        <h2 id={titleId}>AI 에이전트</h2>
        <span className="badge-soon">준비 중</span>
        <button type="button" className="btn btn-icon btn-sm" aria-label="에이전트 패널 닫기" onClick={onClose}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="agent-body">
        <p>글로 지시하면 업무 처리 · 대시보드 · 메일 관리를 돕는 기능이 들어올 자리입니다.</p>
        <p className="note">명령 해석과 실행은 아직 연결되지 않았습니다. 입력한 내용은 어디에도 보내지 않습니다.</p>
        <section className="result-slot" aria-label="결과 카드 자리">
          <strong>결과 카드 자리</strong>
          <span className="note">에이전트가 연결되면 실행 전 확인과 결과가 이 자리에 표시됩니다. 지금 모양은 임시이며 응답 형식이 정해지지 않았습니다.</span>
        </section>
      </div>
      <form className="agent-form" onSubmit={(e) => e.preventDefault()}>
        <label htmlFor={inputId}>에이전트에게 요청</label>
        <textarea
          id={inputId}
          ref={inputRef}
          value={draft}
          placeholder="예: 김 팀장님 건 오늘 할 일로 보여 줘"
          aria-describedby={hintId}
          onChange={(e) => onDraftChange(e.target.value)}
        />
        <div className="agent-form-row">
          <span id={hintId} className="note">
            보내기는 준비 중입니다 · Esc로 닫기
          </span>
          <button type="submit" className="btn btn-sm" disabled>
            보내기 (준비 중)
          </button>
        </div>
      </form>
    </aside>
  );
}
