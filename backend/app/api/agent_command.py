"""에이전트 명령 API (BE-11 2단계, 구조도 v3.1 6 · 8절 ⑥, docs/30_backend/detail.md 4절).

POST /api/agent/command {text, selected_mail_ids?, last_result_ids?}
  → ai /agent/plan(행동 레지스트리 목록 + 지금 시각 + 선택 · 직전 결과 메일 id)
  → executor.run(검증 → 대상 해석 → 확인 판정 → 실행 · 미리보기) → AgentResult
- 상태 변경 · 기록 · 되돌리기는 BE-4 서비스(task_status)만 쓴다. 이 파일에는 상태 변경 로직이 없다.
- 확인이 필요하면(2건 이상 · 후보 여럿) kind=confirm + preview_id를 돌려주고, 실행은 POST /api/actions/execute {preview_id, task_ids?}.
- FE는 응답 뒤 GET /api/dashboard를 다시 불러 화면을 갱신한다(BE-3).
- ai가 꺼져 있거나 늦거나 계약과 다른 응답이면 500 없이 503 "지금은 명령을 처리할 수 없어요"(구조도 12절 #17 취지). 상태는 바뀌지 않는다.
- 직전 결과(last_result_ids) · 선택 메일(selected_mail_ids)은 **메일 id**다(구조도 8절 ID, #31 리뷰). FE는 결과 targets[].mail_id를 보낸다.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import executor
from app.agent.tools.registry import actions_for_ai
from app.ai_client.client import AIClient, AIError, get_ai_client
from app.core import clock
from app.core.db import get_db
from app.models import User
from app.schemas.agent import AgentResult

router = APIRouter(prefix="/api")
UNAVAILABLE = "지금은 명령을 처리할 수 없어요. 잠시 뒤 다시 말해 주세요"


class AgentCommand(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    selected_mail_ids: list[int] = Field(default_factory=list, max_length=200)  # 메일 화면에서 고른 메일('이거')
    last_result_ids: list[int] = Field(default_factory=list, max_length=200)  # 직전 결과의 targets[].mail_id('그 2건')


def _user_id(db: Session, x_user_id: int | None) -> int:
    """명령을 낸 사용자. 로그인이 아직 없어(BE-6) 시연용 단일 사용자를 쓴다 `[임시]`.
    X-User-Id가 있으면 그 사용자(있는지만 확인, 인증 아님), 없으면 사용자가 한 명일 때 그 사람. #44 core/user.py가 들어오면 그것으로 바꾼다."""
    if x_user_id is not None:
        if db.get(User, x_user_id) is None:
            raise HTTPException(404, "없는 사용자입니다")
        return x_user_id
    ids = list(db.scalars(select(User.id).limit(2)))
    if len(ids) != 1:
        raise HTTPException(400, "사용자를 정할 수 없습니다(X-User-Id 필요)")
    return ids[0]


@router.post("/agent/command", response_model=AgentResult)
def agent_command(body: AgentCommand, db: Session = Depends(get_db), ai: AIClient = Depends(get_ai_client),
                  x_user_id: int | None = Header(default=None)) -> AgentResult:
    user_id = _user_id(db, x_user_id)
    try:
        plan = ai.plan(body.text, actions_for_ai(), now=clock.now(),
                       selected_mail_ids=body.selected_mail_ids, last_result_ids=body.last_result_ids)
    except AIError as e:  # timeout · unavailable · bad_response(계약과 다른 형식 포함)
        raise HTTPException(503, UNAVAILABLE) from e
    result = executor.run(db, user_id, plan.model_dump())  # ai 응답은 PlanResult 검증을 거친 값만 넘긴다(#31 리뷰)
    db.commit()
    return result
