"""에이전트 실행 결과 (BE-11). 프론트 에이전트 패널의 카드 종류와 맞춘다(UX-D8 · wireframe 13-4절).

kind
- done: 결과 카드(과거형 제목 + 대상 + 실행 취소용 action_id)
- confirm: 확인 카드(질문 제목 + 대상 체크 목록 + preview_id). 실행은 POST /api/actions/execute {preview_id, task_ids?}
- query: 조회 결과(대상 목록)
- ask: 되묻기(ai가 애매하다고 했거나, 꼭 필요한 값이 비었거나, 대상 조건이 없을 때)
- empty: 해당하는 업무 없음
- unsupported: 지원하지 않는 요청 · 아직 준비 중인 행동
응답 시각은 +09:00(D47).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.actions import PreviewTarget


class AgentResult(BaseModel):
    kind: Literal["done", "confirm", "query", "ask", "empty", "unsupported"]
    action: str | None = None  # 행동 ID(T03 등)
    action_name: str | None = None
    source: str | None = None  # agent_rule · agent_model (단계 표시 '명령 이해 · 규칙/엑사원')
    title: str  # 카드 제목. 확인 카드는 질문, 결과 카드는 과거형
    targets: list[PreviewTarget] = []
    notes: list[str] = []  # '어떻게 해석했나요'(접힘)
    action_id: int | None = None  # done: 실행 취소에 쓴다
    preview_id: str | None = None  # confirm
    expires_at: datetime | None = None  # confirm: 이 시각까지 실행할 수 있다
