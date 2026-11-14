"""분류 결과 칸별 담당표 (AI-5 · AI-D15). `ClassifyResponse`의 칸마다 누가 정하고, 무엇을 근거로 하고, 비면 무엇을 두는지 한 곳에 적는다.

담당 (11/7 사용자 결정: 판단은 모델, 규칙은 조건만, 둘이 겹치지 않는다)
- model: 모델이 판단한다. 규칙이 덮어쓰지 않는다
- rule: 메일에 글자 · 주소로 드러난 조건만 본다(`pipeline/conditions.py`). 뜻을 해석하지 않는다
- code: 다른 칸에서 계산한다(날짜 · 우선순위 · 묶음 · 칸)

모델에 묻는 칸은 `MODEL_FIELDS`뿐이다. 분류 프롬프트(`prompts/classify_v8`)의 JSON 스키마가 이 칸과 같아야 한다(test_fields).
칸을 늘리거나 담당을 바꾸면 이 표 · 프롬프트 · `tests/test_fields.py`가 함께 바뀐다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    owner: str  # rule | model | code
    source: str  # 근거
    empty: str  # 값이 없을 때


FIELDS: dict[str, FieldSpec] = {
    "category": FieldSpec("code", "D39 5분류 묶음(classify.CATEGORY). 할 일이 있으면 첫 할 일 유형, 없으면 메일 유형", "기타"),
    "action_types": FieldSpec("code", "할 일 유형(나온 순서) + 메일 성격이 공지면 '공지' + 참조로 받았으면 '참조'. "
                              "할 일이 없으면 참조(CC 조건) 아니면 모델 메일 성격(classify.mail_types)", "['기타']"),
    "mail_type": FieldSpec("model", "메일 성격: 요청 · 회신 · 공유 · 공지 · 기타. 응답에는 action_types로 나간다", "-"),
    "tasks": FieldSpec("model", "내가 해야 할 일. 본문이 조건 없이 필요 없다고 밝힌 종류는 확인 칸으로 옮긴다(conditions.NO_ACTION)", "[]"),
    "tasks.type": FieldSpec("model", "할 일 유형 6개(자료제출 · 회신 · 검토승인 · 수정재전송 · 일정참석 · 조치)", "회신요청"),
    "tasks.text": FieldSpec("model", "할 일 문구(모델 출력 action)", "-"),
    "tasks.due_raw": FieldSpec("model", "기한 표현 원문. 메일에 그 글자가 없으면 버린다. 회의 참석이 비면 회의 일시", "null"),
    "tasks.due_at": FieldSpec("code", "due_raw를 받은 시각 기준으로 계산(dates). 회의 참석 외에는 마감 표지가 붙은 날짜만(AI-D11)", "null"),
    "tasks.due_time_stated": FieldSpec("code", "due_at의 시각이 메일에 글자로 있었나(보정 전 원래 값, dates.DueParse.time_stated). "
                                       "날짜만 있어 18:00 · 12:00 · 09:00으로 채웠으면 false. 캘린더 자동 등록 조건(AI-20 · D50)", "false"),
    "tasks.end_at": FieldSpec("code", "일정참석만: 시작 시각으로 시작하는 범위('14:00~15:30')의 끝(dates.parse_event_end). 지어내지 않는다", "null"),
    "tasks.format": FieldSpec("model", "결과물 파일 형식", "null"),
    "tasks.deliver_to": FieldSpec("model", "결과를 보낼 사람 · 곳(모델 출력 to). '요청자'면 비운다(DE-D21)", "null"),
    "tasks.evidence": FieldSpec("code", "할 일 문구와 가장 닮은 본문 문장(evidence.attach, AI-D14)", "null"),
    "checks": FieldSpec("code", "할 일이 없는 메일만. 나에게 온 회신 · 공유 · 공지, 필요 없다고 밝혀 옮긴 모델 할 일, 분류 실패(pipeline/checks.py)", "[]"),
    "checks.text": FieldSpec("code", "제목 요지. 옮긴 할 일은 그 문구", "-"),
    "checks.reason": FieldSpec("code", "회신 · 공유 · 공지 · 요청 문장 있음 · 필요 없다고 밝힘 · 분류 실패", "-"),
    "checks.evidence": FieldSpec("code", "요청 어미 문장 · 필요 없다고 밝힌 문장", "null"),
    "checks.source": FieldSpec("code", "모델 할 일을 옮겼으면 exaone", "rule"),
    "lane": FieldSpec("code", "할 일이 있으면 할 일, 확인 항목이 있으면 확인, 아니면 참고", "참고"),
    "mentioned_me": FieldSpec("code", "할 일이 있으면 지목(단체 · 참조 메일은 내 이름 · 우리 팀 · 내 역할을 불러 맡길 때만 할 일이 된다, 11/7)", "false"),
    "urgent": FieldSpec("model", "긴급 단어가 있고(조건: 본문 · 회신이 아닌 제목) 모델이 나에게 서두르라는 뜻으로 볼 때. 모델 실패면 단어만", "false"),
    "is_follow_up": FieldSpec("model", "재요청 단어가 있고(조건) 모델이 전 요청을 다시 보낸 재촉으로 볼 때(모델 출력 follow_up). 모델 실패면 단어만", "false"),
    "priority": FieldSpec("code", "priority.score: 상급자 · 기한 · 긴급 · 재요청 · 수신 방식 점수(D9)", "P3"),
    "confidence": FieldSpec("code", "쓰지 않는다(라우터 없음). 응답 호환용 칸", "null"),
    "source": FieldSpec("code", "모델 판단을 썼으면 exaone, 모델 호출 실패면 rule", "exaone"),
}

MODEL_FIELDS = [k for k, f in FIELDS.items() if f.owner == "model"]
