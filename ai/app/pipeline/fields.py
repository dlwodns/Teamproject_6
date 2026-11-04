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
        "model", "v3.2: kind가 확신하면 kind 부모 유형(kinds.kind_types, 요청 2개면 규칙 순서). 아니면 규칙: 요청 문장의 유형 단어(TYPE_RULES) → "
        "제목 머리말(SUBJECT_TYPE) · 수신 방식(참조 · 단체) · 회신 제목", "['기타']",
        "kind 확신이면 엑사원 유형을 받지 않는다. kind가 애매하면 엑사원 주 유형이 kind 후보(1 · 2등 · 부모가 다른 1등의 부모) 안일 때만 받고, "
        "밖이면 kind 1등. 참조 미지목은 참조 · 사외 공지는 기타(classify._with_kind)"),
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
    # 확인 칸(사용자 항목 2). 지금은 후처리(code)다. 프롬프트에 checks 출력 칸을 붙이면 owner를 model로 바꾸고
    # 프롬프트 스키마 · test_fields가 함께 바뀐다(MODEL_FIELDS)
    "checks": FieldSpec(
        "code", "할 일이 없는 메일만(pipeline/checks.py). 나에게 온 완료 알림 · 회신, 단체 메일의 대상자 당부, 엑사원 할 일 중 옮긴 읽을거리", "[]",
        "엑사원 할 일 중 규칙 근거가 없고 기한 없는 '~ 확인 · 참고'뿐인 것과 '회신 · 참조 · 기타' 머리에 붙은 것은 버리지 않고 여기로 옮긴다. "
        "기한이 있거나 규칙이 나를 향한 요청을 찾은 할 일은 옮기지 않는다(D15)"),
    "checks.text": FieldSpec("code", "제목 요지(회신 표시 · 머리말 · 끝 괄호 뺌). 엑사원 할 일을 옮긴 것은 그 문구", "-"),
    "checks.reason": FieldSpec("code", "완료 보고(완료 · 반영 · 처리 알림) → 결과 회신(받는사람이 나인 회신) → 해당 여부 확인(대상자 당부) · 읽고 확인(옮긴 할 일)", "-"),
    "checks.evidence": FieldSpec("code", "완료 · 회신 · 당부 문장", "null"),
    "checks.source": FieldSpec("code", "엑사원 할 일을 옮겼으면 exaone(채점에서 재현율 피해를 따로 센다)", "rule"),
    # 메일 성격(사용자 항목 1 · 3, v3.2). 형식(필수 · 보조 · 배제 신호) 점수로 정하고 엑사원에 묻지 않는다
    "kind": FieldSpec("code", "kinds.score: signals.py 구조 신호 · 범주 어휘로 21종 형식 점수 → 1등. 부모가 다른 kind와 차이 < 1.0 · 1등 < 2.0 · "
                      "요청 형식인데 규칙 할 일 없음 · 그 반대면 애매(kind_sure false) → 엑사원행", "null"),
    "kind_name": FieldSpec("code", "kinds.KINDS 이름", "null"),
    "kind_sure": FieldSpec("code", "kind가 애매하지 않다. true면 action_types 주 유형은 kind 부모(엑사원 유형을 받지 않음)", "false"),
    "lane": FieldSpec("code", "할 일이 있으면 할 일, 확인 항목이 있으면 확인, 아니면 참고", "참고"),
    "mentioned_me": FieldSpec("rule", "받는사람이 나 · 본문에 내 이름 · 팀 · 직급 지목. 할 일이 없으면 false", "false"),
    "urgent": FieldSpec("rule", "URGENT 단어(본문 · 회신 아닌 제목)", "false"),
    "is_follow_up": FieldSpec("rule", "FOLLOW_UP 표현(다시 요청 · 아직 회신 · 리마인드)", "false"),
    "priority": FieldSpec("code", "priority.score: 상급자 · 기한 · 긴급 · 재요청 · 수신 방식 점수(D9)", "P3"),
    "confidence": FieldSpec("rule", "규칙(할 일) 확신도. 라우터(classify.route, v3.2 문지기): kind 애매 → 엑사원, 0.8 미만이어도 kind가 "
                            "'할 일 없음'을 확신하고 나를 향한 요청이 없으면 건너뜀(지목 불확실한 요청은 확인 칸 kind일 때만)", "-"),
    "source": FieldSpec("code", "엑사원 결과를 썼으면 exaone", "rule"),
}

MODEL_FIELDS = [k for k, f in FIELDS.items() if f.owner == "model"]
