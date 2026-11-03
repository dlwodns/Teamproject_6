"""분류 결과 칸별 담당표 (AI-5). `ClassifyResponse`의 칸마다 누가 정하고, 무엇을 근거로 하고, 비면 무엇을 두는지 한 곳에 적는다.

담당
- rule: 규칙(`rules/mail_rules_v1.py`)만 정한다. 엑사원에 묻지 않는다
- model: 엑사원으로 간 메일은 엑사원 값을 쓰고, 아니면 규칙 값을 쓴다. 합치기는 `classify._from_model`
- code: 다른 칸에서 계산한다(날짜 해석 · 우선순위 · 유형 묶음). 규칙 · 모델 모두 직접 내지 않는다

엑사원에 묻는 칸은 `MODEL_FIELDS`뿐이다. 분류 프롬프트(`prompts/classify_v3`)의 JSON 스키마가 이 칸과 같아야 한다(test_fields).
칸을 늘리거나 담당을 바꾸면 이 표 · 프롬프트 · `tests/test_fields.py`가 함께 바뀐다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    owner: str  # rule | model | code
    source: str  # 근거 신호 · 계산식
    empty: str  # 값이 없을 때
    merge: str = ""  # 엑사원으로 간 메일에서 규칙 · 모델 값을 고르는 법


FIELDS: dict[str, FieldSpec] = {
    "category": FieldSpec("code", "주 유형 → D39 묶음(classify.CATEGORY). 할 일이 있으면 할 일 유형 중 첫 번째", "기타"),
    "action_types": FieldSpec(
        "model", "규칙: 요청 문장의 유형 단어(TYPE_RULES) → 제목 머리말(SUBJECT_TYPE) · 수신 방식(참조 · 단체) · 회신 제목", "['기타']",
        "둘 다 할 일을 찾으면 규칙 · 할 일 없음 유형이 서로 맞으면 규칙 · 참조 미지목은 참조 · 사외 공지는 기타"),
    "tasks": FieldSpec(
        "model", "규칙: 나를 향한 요청 문장(REQUEST · 지목 · 수신 방식). 공지의 '미이수자 · 해당자 · 전 직원' 당부는 할 일 아님", "[]",
        "모델이 비워도 규칙 할 일은 남긴다(D15 누락 방지) · 회신 · 참조 · 기타 머리 + 규칙 할 일 없음이면 모델 할 일 버림"),
    "tasks.text": FieldSpec("model", "규칙: 요청 문장에서 호칭 · 맺음말을 뺀 구절", "-"),
    "tasks.due_raw": FieldSpec(
        "model", "마감 표지(까지 · 전에 · 내로 · 이내) 앞 날짜 · 시각 표현을 그대로 옮긴 글자", "null",
        "모델이 비우면 회의 참석은 회의 일시, 아니면 문구가 닮은 규칙 할 일의 기한"),
    "tasks.due_at": FieldSpec("code", "due_raw를 받은 시각 기준으로 계산(dates.parse_due). 모델이 날짜를 계산하지 않는다", "null"),
    "tasks.format": FieldSpec("model", "규칙: 파일 형식 단어(FORMATS) · 양식 첨부의 확장자", "null"),
    "tasks.evidence": FieldSpec("rule", "할 일을 찾은 본문 문장", "null"),
    "mentioned_me": FieldSpec("rule", "받는사람이 나 · 본문에 내 이름 · 팀 · 직급 지목. 할 일이 없으면 false", "false"),
    "urgent": FieldSpec("rule", "URGENT 단어(본문 · 회신 아닌 제목)", "false"),
    "is_follow_up": FieldSpec("rule", "FOLLOW_UP 표현(다시 요청 · 아직 회신 · 리마인드)", "false"),
    "priority": FieldSpec("code", "priority.score: 상급자 · 기한 · 긴급 · 재요청 · 수신 방식 점수(D9)", "P3"),
    "confidence": FieldSpec("rule", "규칙 확신도. 0.8 미만이면 엑사원으로(라우터 AI-3)", "-"),
    "source": FieldSpec("code", "엑사원 결과를 썼으면 exaone", "rule"),
}

MODEL_FIELDS = [k for k, f in FIELDS.items() if f.owner == "model"]
