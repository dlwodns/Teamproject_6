"""메일 분류 프롬프트 v5 (사용자 항목 1 · 3, 11/3) — 형식 후보 안에서 고르게 한다. 실측 전 후보안이라 기본값이 아니다.

v3 → v5 (11/3 plan 4.5의 제외안 classify_v4(표 조립 · null 칸)와 다른 안이다):
- 9유형 정의 대신 메일 성격 21종(pipeline/kinds.py)의 한 줄 정의를 시스템 프롬프트에 둔다(고정 → 프리픽스 캐시).
- 메일마다 규칙이 뽑은 '형식 후보'(kind 점수 상위)와 '규칙이 찾은 나에게 온 요청'을 user 앞 두 줄로 넘긴다.
- JSON 스키마의 kind enum을 그 후보로 좁힌다 — 후보 밖 유형을 고를 수 없다(사용자 지적: AI가 이상하게 판단할 수 있다).
- 출력은 kind + tasks. action_types는 코드가 kind 부모 유형으로 만든다(classify._v5_out).
켜는 법: 환경 변수 CLASSIFY_PROMPT=v5. 시스템 프롬프트는 메일마다 같아야 캐시가 맞는다 — 메일마다 바뀌는 값은 user에만.
"""
from app.pipeline import kinds
from app.prompts.classify_v3 import WEEKDAYS, trim_body

PROMPT_VERSION = "classify_v5"
ACTION_TYPES = kinds.ACTION_TYPES  # 합치기가 모델 유형을 거르는 목록(classify._from_model)
TOP_K = 3  # 형식 후보 수

_DEFS = "\n".join(f"  {k.id} {k.name}: {k.definition}" for k in kinds.KINDS)

SYSTEM = f"""너는 업무 메일 분류기다. '나'에게 온 메일을 읽고 규칙을 지켜 JSON 하나만 출력한다.
규칙1 kind: '형식 후보' 중 메일에 가장 맞는 하나를 고른다. 형식 정의:
{_DEFS}
규칙2 tasks: 내가 해야 할 일만 적는다. 아래는 할 일이 아니므로 tasks를 비운다.
  - 완료 보고 · 자료 회신 · 수신 확인. 읽고 확인만 하면 되는 내용으로 '~ 확인' 할 일을 만들지 않는다.
  - '해당자는' · '미이수자는'처럼 내가 해당하는지 알 수 없는 대상, 다른 사람에게 한 요청, 사외 홍보 · 초청의 등록 안내
  공지라도 내 이름 · 우리 팀 · 내 직급("팀장님들께서는")을 지목한 요청은 할 일이다.
  '규칙이 찾은 요청'이 있으면 그 요청이 정말 나에게 온 것인지 본문으로 확인하고 적는다.
규칙3 서로 다른 요청이 둘이면 두 개로 나누고, 같은 일을 함께 당부하면 하나로 둔다. action은 해야 할 일 30자 이내.
  due_raw는 기한 표현을 그대로 옮긴다(예: "수요일까지", "10/23(금) 14시까지"). 없으면 "없음". 추측하지 않는다. 회의 참석은 회의 일시가 기한.
  format은 요청한 파일 형식(xlsx, pptx, pdf 등), 없으면 "없음".
예시1) 형식 후보: K01 / K06 · 규칙이 찾은 요청: 팀별 실적 양식 작성 / 본문: "첨부 양식에 팀별 실적을 작성해 수요일까지 엑셀로 회신 부탁드립니다."
→ {{"kind":"K01","tasks":[{{"action":"팀별 실적 양식 작성 후 엑셀 회신","due_raw":"수요일까지","format":"xlsx"}}]}}
예시2) 형식 후보: K12 / K13 · 규칙이 찾은 요청: 없음 / 제목: RE: [요청] 회의실 예약 / 본문: "요청하신 회의실 예약을 마쳤습니다."
→ {{"kind":"K12","tasks":[]}}
예시3) 형식 후보: K19 / K09 · 규칙이 찾은 요청: 사전 등록 / 본문: "12월 클라우드 세미나에 초대합니다. 사전 등록하시면 자료를 드립니다."
→ {{"kind":"K19","tasks":[]}}"""

_TASKS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"action": {"type": "string"}, "due_raw": {"type": "string"}, "format": {"type": "string"}},
        "required": ["action", "due_raw", "format"],
    },
}
# test_fields가 보는 기본 스키마(kind는 응답의 kind 칸, tasks는 tasks 칸). 메일마다 kind enum만 좁힌다(schema_for)
SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": [k.id for k in kinds.KINDS]}, "tasks": _TASKS},
          "required": ["kind", "tasks"]}


def candidates(k: "kinds.KindResult") -> list[str]:
    """형식 점수 상위 TOP_K. 맞는 형식이 없으면 전부."""
    ranked = [kid for kid, _ in sorted(k.scores.items(), key=lambda kv: -kv[1])][:TOP_K]
    return ranked or [x.id for x in kinds.KINDS]


def schema_for(k: "kinds.KindResult") -> dict:
    return {**SCHEMA, "properties": {**SCHEMA["properties"], "kind": {"type": "string", "enum": candidates(k)}}}


def render_user(req, recipient: str, k: "kinds.KindResult", rule_tasks: list[str]) -> str:
    who = {"to": "나", "cc": "다른 사람 (나는 참조)", "list": "단체 메일 (나는 배포 목록으로 받음)"}[recipient]
    owner = req.owner
    me = " · ".join(x for x in (owner.name, owner.position, owner.team) if x) or "나"
    r = req.received_at
    cand = " / ".join(f"{kid} {kinds.BY_ID[kid].name}" for kid in candidates(k)) if k.scores else "전부"
    return (
        f"형식 후보: {cand}\n규칙이 찾은 요청: {' · '.join(rule_tasks)[:60] or '없음'}\n"
        f"받은날짜: {r:%Y-%m-%d %H:%M}({WEEKDAYS[r.weekday()]})\n"
        f"나: {me}\n받는사람: {who}\n제목: {req.subject}\n첨부: {', '.join(req.attachments) or '없음'}\n본문:\n{trim_body(req.body)}"
    )
