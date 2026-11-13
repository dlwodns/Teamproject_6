"""문맥 기억 추출 프롬프트 v1 (PL-16, BE-D21). 분류 프롬프트(동결)와 따로 둔다 — 분류 정확도에 영향을 주지 않는다."""
from app.schemas.memory import MemoryExtractRequest

VERSION = "memory_v1"

SYSTEM = """너는 회사 메일에서 '보낸 사람'에 대한 업무 사실만 뽑는다. 다음 두 종류만 뽑고, 메일에 분명히 적힌 것만 쓴다.
- works_on: 보낸 사람이 맡고 있는 거래처 · 프로젝트 · 업무. 짧은 명사구(20자 이내). 예: "한빛은행 2단계 전환"
- org: 보낸 사람의 소속 회사 · 부서. 예: "한빛은행 IT기획부"
규칙:
1. 보낸 사람 본인에 대한 사실만. 받는 사람 · 다른 사람에 대한 사실은 뽑지 않는다.
2. evidence에는 그 사실이 적힌 본문 문장을 글자 하나 바꾸지 않고 그대로 옮긴다.
3. 추측하지 않는다. 가족 · 건강 · 생일 같은 사적인 사실은 뽑지 않는다.
4. 없으면 facts를 빈 목록으로 둔다.
JSON으로만 답한다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["works_on", "org"]},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["kind", "value", "evidence"],
            },
        }
    },
    "required": ["facts"],
}


def build_user(req: MemoryExtractRequest) -> str:
    me = " · ".join(x for x in (req.owner.name, req.owner.position, req.owner.team) if x) or "나"
    who = f"{req.sender_name} <{req.from_}>" if req.sender_name else req.from_
    return f"받는 사람(나): {me}\n보낸 사람: {who}\n제목: {req.subject}\n본문:\n{req.body}"
