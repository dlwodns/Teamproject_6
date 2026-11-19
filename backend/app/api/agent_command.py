"""에이전트 명령 API (BE-11 2단계, 구조도 v3.1 6 · 8절 ⑥, docs/30_backend/detail.md 4절).

POST /api/agent/command {text, selected_mail_ids?, last_result_ids?, task_ids?, reminder_key?}
  (task_ids: 캐치봇에서 고른 리마인더의 업무. 대상 규칙은 executor.run, BE-18)
  → ai /agent/plan(행동 레지스트리 목록 + 지금 시각 + 선택 · 직전 결과 메일 id)
  → executor.run(검증 → 대상 해석 → 확인 판정 → 실행 · 미리보기) → AgentResult
- 상태 변경 · 기록 · 되돌리기는 BE-4 서비스(task_status)만 쓴다. 이 파일에는 상태 변경 로직이 없다.
- 확인이 필요하면(2건 이상 · 후보 여럿) kind=confirm + preview_id를 돌려주고, 실행은 POST /api/actions/execute {preview_id, task_ids?}.
- FE는 응답 뒤 GET /api/dashboard를 다시 불러 화면을 갱신한다(BE-3).
- ai가 꺼져 있거나 늦거나 계약과 다른 응답이면 500 없이 503 "지금은 명령을 처리할 수 없어요"(구조도 12절 #17 취지). 상태는 바뀌지 않는다.
- 직전 결과(last_result_ids) · 선택 메일(selected_mail_ids)은 **메일 id**다(구조도 8절 ID, #31 리뷰). FE는 결과 targets[].mail_id를 보낸다.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import privacy
from app.agent import executor
from app.agent.tools.registry import actions_for_ai
from app.ai_client.client import AIClient, AIError, get_ai_client
from app.core import clock
from app.core.db import get_db
from app.core.user import MAX_ID, current_user_id
from app.schemas.agent import AgentResult

router = APIRouter(prefix="/api")
UNAVAILABLE = "지금은 명령을 처리할 수 없어요. 잠시 뒤 다시 말해 주세요"


class AgentCommand(BaseModel):
    text: str = Field(min_length=1, max_length=500)  # 앞뒤 공백을 지운 뒤의 길이로 본다
    selected_mail_ids: list[int] = Field(default_factory=list, max_length=200)  # 메일 화면에서 고른 메일('이거')
    last_result_ids: list[int] = Field(default_factory=list, max_length=200)  # 직전 결과의 targets[].mail_id('그 2건')
    # 캐치봇에서 고른 리마인더(docs/10_planning/reminders.md 131행 '아래 입력'). FE는 FE-16부터 보냈는데 받지 않고 버리고 있었다(11-18)
    task_ids: list[Annotated[int, Field(ge=1, le=MAX_ID)]] = Field(default_factory=list, max_length=200)  # 범위 밖이면 500 대신 422
    reminder_key: str | None = Field(default=None, max_length=200)  # 지금은 기록용. 대상은 task_ids로 정한다

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, v):
        # 공백만 있는 명령은 ai를 부르기 전에 422(엑사원 해석이 수십 초 걸린다, #50 리뷰)
        return v.strip() if isinstance(v, str) else v


@router.post("/agent/command", response_model=AgentResult)
def agent_command(body: AgentCommand, db: Session = Depends(get_db), ai: AIClient = Depends(get_ai_client),
                  user_id: int = Depends(current_user_id)) -> AgentResult:
    # 요청한 사용자는 #44 core/user.py 한 곳에서 정한다(BE-D16): 헤더 없으면 개발 모드만 1번, 없는 사용자는 401
    # 개인정보 가리기(BE-6): 명령 글도 ai로 나가므로 가리고, ai가 돌려준 대상(보낸 사람 이름 · 키워드 등)은 되돌린 뒤
    # 연락처를 찾는다. 가린 이름(김◯◯)은 ai 규칙이 보낸 사람으로 읽는다(ai rules_v1 SENDER)
    masker = privacy.masker_for(db, user_id)
    try:
        plan = masker.unmask_model(ai.plan(masker.mask_text(body.text), actions_for_ai(), now=clock.now(),
                                           selected_mail_ids=body.selected_mail_ids,
                                           last_result_ids=body.last_result_ids))
    except AIError as e:  # timeout · unavailable · bad_response(계약과 다른 형식 포함)
        raise HTTPException(503, UNAVAILABLE) from e
    result = executor.run(db, user_id, plan.model_dump(), scope_task_ids=body.task_ids or None)  # ai 응답은 PlanResult 검증을 거친 값만 넘긴다(#31 리뷰)
    db.commit()
    return result
