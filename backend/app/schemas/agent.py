"""에이전트 실행 결과 (BE-11). 프론트 에이전트 패널의 카드 종류와 맞춘다(UX-D8 · wireframe 13-4절).

kind
- done: 결과 카드(과거형 제목 + 대상 + 실행 취소용 action_id)
- confirm: 확인 카드(질문 제목 + 대상 체크 목록 + preview_id). 실행은 POST /api/actions/execute {preview_id, task_ids?}
- query: 조회 결과(대상 목록)
- ask: 되묻기(ai가 애매하다고 했거나, 꼭 필요한 값이 비었거나, 대상 조건이 없을 때)
- empty: 해당하는 업무 없음
- unsupported: 지원하지 않는 요청 · 아직 준비 중인 행동
- summary: 하루 요약 · 회고(T01). 브리핑과 같은 내용을 채팅에서 바로 본다(11-14)
- person: 사람 조회(T17). 그 사람의 맡은 일 · 소속(메일 내용 분석을 켰을 때만) · 보낸 메일 · 업무(targets, 끝난 것 포함)
응답 시각은 +09:00(D47).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.actions import PreviewTarget
from app.schemas.awaiting import AwaitingView


class AgentTarget(PreviewTarget):
    """에이전트 결과 대상. 업무 id와 함께 메일 id를 싣는다.
    다음 명령의 직전 결과(context.last_result_ids)는 **메일 id**다 — ai가 target.mail_ids에 그대로 넣어 돌려준다(#31 리뷰).
    프론트는 targets[].mail_id를 직전 결과로 보낸다(업무 id를 보내면 다른 업무를 고른다)."""

    mail_id: int
    snoozed_until: datetime | None = None  # '나중에' 업무면 미룬 시각(+09:00). 조회에서 '나중에(11/14 09:00)'로 구분해 보여 준다


class AgentResult(BaseModel):
    kind: Literal["done", "confirm", "query", "ask", "empty", "unsupported", "summary", "person", "awaiting"]
    action: str | None = None  # 행동 ID(T03 등)
    action_name: str | None = None
    source: str | None = None  # agent_rule · agent_model (단계 표시 '명령 이해 · 규칙/엑사원')
    title: str  # 카드 제목. 확인 카드는 질문, 결과 카드는 과거형
    targets: list[AgentTarget] = []
    notes: list[str] = []  # '어떻게 해석했나요'(접힘)
    action_id: int | None = None  # done: 실행 취소에 쓴다
    preview_id: str | None = None  # confirm
    expires_at: datetime | None = None  # confirm: 이 시각까지 실행할 수 있다
    summary: "AgentSummary | None" = None  # summary
    person: "AgentPerson | None" = None  # person
    awaiting: list[AwaitingView] | None = None  # awaiting(T06 응답 대기, BE-13). GET /api/awaiting와 같은 줄
    sends: "list[AgentSend] | None" = None  # confirm(T14 재촉 메일): 보낼 메일 미리보기. 확인은 execute(preview_id, mail_ids)
    # 11-18 사용자 목적별 확장: 업무가 아닌 메일 목록(T19 메일 찾기 · T20 메일 요약 · T18 답을 찾은 메일)과
    # 카드 본문 줄(T08 근거 문장 · T13 일정 · T20 요청한 것). 둘 다 query 카드에 접지 않고 보인다
    mails: "list[AgentMail] | None" = None
    lines: list[str] = []


class AgentMail(BaseModel):
    mail_id: int
    subject: str
    who: str  # 받은 메일은 보낸 사람, 보낸 메일은 받는 사람(이름 직급, 연락처에 없으면 주소)
    direction: Literal["received", "sent"]
    at: datetime | None = None  # 받은 · 보낸 시각(+09:00)


class AgentPersonFact(BaseModel):
    kind: Literal["works_on", "org"]
    label: str  # 맡은 일 · 소속
    value: str
    evidence: str | None = None  # 메일 본문에 글자 그대로 있던 문장
    mail_id: int | None = None


class AgentPersonMail(BaseModel):
    mail_id: int
    subject: str
    received_at: datetime | None = None


class AgentPerson(BaseModel):
    contact_id: int | None = None  # 연락처에 없는 분(메일의 쓴 사람으로만 찾음, AI-44)이면 비어 있다
    name: str | None = None
    email: str
    position: str | None = None
    is_superior: bool = False
    is_favorite: bool = False
    facts: list[AgentPersonFact] = []  # 메일 내용 분석이 꺼져 있으면 비운다(learn_off=True)
    learn_off: bool = False
    mails: list[AgentPersonMail] = []  # 그 사람이 보낸 메일, 최근 순
    mail_total: int = 0


class AgentSend(BaseModel):
    """T14 재촉 메일 미리보기 한 통(기획 detail 7절 '수신자 · 제목 · 본문 미리보기')."""
    mail_id: int  # 재촉할 내 보낸 요청 메일(응답 대기)
    to: str  # 받는 사람 표시('박지호 매니저', 여럿이면 '… 외 N명')
    subject: str
    body: str


class AgentSummaryItem(BaseModel):
    task_id: int
    mail_id: int
    text: str
    due_at: datetime | None = None
    due_raw: str | None = None
    section: str | None = None  # 브리핑 묶음 id(done_today 등). 회고의 완료 업무를 화면이 '완료'로 보인다


class AgentSummary(BaseModel):
    text: str  # 브리핑 한 줄(건수, 정해진 문장)
    items: list[AgentSummaryItem]
    hint: str | None = None


AgentResult.model_rebuild()
