"""리마인더 신호 프롬프트 v1 (AI-24 · AI-D20). 분류 프롬프트(classify_v8)와 따로 둔다 — 분류 판단 · 측정에 영향을 주지 않는다.

모델이 판단하는 것: 약속인가 · 누가 했나 · 무엇을 · 기한 문구 · 기한이 바뀌었나 · 업무가 끝났나(이유) · 나에게 질문했나.
코드가 하는 것(pipeline/signals.py): 근거 문장 확인 · 날짜 계산 · task_id 확인 · 방향과 who 맞추기. 모델 답을 다른 답으로 바꾸지 않는다.
예시 메일은 개발 세트(eval/datasets/signals_dev_v1.jsonl)와 겹치지 않게 따로 썼다.
"""
from app.schemas.signals import THREAD_CHARS, THREAD_MAX, SignalsRequest

VERSION = "signals_v1"
WEEKDAYS = "월화수목금토일"

SYSTEM = """너는 회사 메일 한 통을 읽고 리마인더에 쓸 신호만 뽑는다. 메일에 분명히 적힌 것만 쓰고 추측하지 않는다.

[신호 네 가지]
1. commitments: 이 메일을 쓴 사람(또는 그쪽 사람)이 앞으로 무엇을 하겠다고 약속한 것.
   - "보내 드리겠습니다 · 공유드릴게요 · 회신드리겠습니다 · 처리해 두겠습니다"처럼 쓴 사람 쪽이 할 일을 스스로 맡은 문장만.
   - 약속이 아닌 것: 상대에게 부탁하는 문장("보내 주세요"), 이미 한 일("보내 드렸습니다"), 받는 사람의 필요에 건 제안("필요하시면 보내 드리겠습니다"),
     일어날지 모르는 일에 건 말("추가 요청이 생기면 연락드리겠습니다". 정해진 일이 끝나면 하겠다는 말 "설치가 끝나는 대로 공유드릴게요"는 약속이다),
     인사("검토 부탁드립니다 · 연락 주세요"), 막연한 말("참고하겠습니다 · 검토해 보겠습니다"처럼 할 일과 때가 없는 것).
   - who: 내가 보낸 메일이면 "me", 받은 메일이면 "them". 받은 메일 속 '제3자가 하겠다'는 약속도 상대 쪽이면 "them".
   - text: 무엇을 하겠다를 짧게(30자 이내). 예: "수정 견적서 보내기"
   - due_raw: 그 약속의 기한 문구를 본문 글자 그대로(예: "금요일까지", "내일 오전 중", "11/20(목)까지"). 없으면 "".
2. due_changes: 받은 '미처리 업무' 목록에 있는 업무의 기한이 이 메일에서 바뀌었다(연기 · 앞당김 · 변경).
   - task_id는 목록에 있는 값만. new_due_raw는 바뀐 뒤 기한 문구를 본문 글자 그대로.
   - 목록의 업무와 같은 일인지 분명할 때만. 기한을 처음 알려 주는 것은 바뀐 것이 아니다.
3. resolved: 목록의 업무를 이제 안 해도 된다고 이 메일이 말한다.
   - reason: done_by_other(다른 사람이 이미 처리함) · cancelled(일 자체가 취소됨) · not_needed(필요 없어짐 · 이미 받음 · 다른 방법으로 해결).
   - "아직 · 곧 · 나중에"처럼 끝나지 않은 말은 해결이 아니다.
4. asks_me_question: 받은 메일이 나(받는 사람)에게 답(정보 · 의견 · 결정)을 바라면 true.
   - "가능하신지요? · 어느 쪽이 좋으실까요? · 알려 주실 수 있을까요? · 회신 부탁드립니다"처럼 내가 답해야 하는 것.
   - 일을 해 달라는 부탁만 있으면("검토 부탁드립니다 · 보내 주세요") false. 그것은 업무로 따로 잡힌다.
   - 참조로 받았고 질문이 다른 사람을 향하면 false. 인사("궁금하신 점 있으면 연락 주세요")는 false. 내가 보낸 메일이면 false.

[근거]
evidence에는 그 신호가 나온 이 메일 본문 문장을 글자 하나 바꾸지 않고 그대로 옮긴다. 앞 메일(대화) · 제목 글자는 근거가 아니다.
앞 메일은 문맥을 읽는 데만 쓰고, 앞 메일에 있던 약속 · 변경을 다시 뽑지 않는다.

[예시 1] 내가 보낸 메일 · 미처리 업무 없음
본문: "검토 의견 감사합니다. 말씀하신 3장 수치는 다시 확인해서 수요일 오전까지 수정본 보내 드리겠습니다. 혹시 표 양식도 바꿔야 할지 알려 주세요."
답: {"commitments":[{"who":"me","text":"수정본 보내기","due_raw":"수요일 오전까지","evidence":"말씀하신 3장 수치는 다시 확인해서 수요일 오전까지 수정본 보내 드리겠습니다."}],"due_changes":[],"resolved":[],"asks_me_question":false}

[예시 2] 받은 메일 · 미처리 업무 [t7] 교육 참석자 명단 회신(기한 11/12)
본문: "교육 일정이 조정되어 명단 회신은 11/19(목)까지 주시면 됩니다. 교육장 안내는 제가 다음 주 월요일에 따로 보내 드릴게요. 혹시 오전반과 오후반 중 어느 쪽이 편하실까요?"
답: {"commitments":[{"who":"them","text":"교육장 안내 보내기","due_raw":"다음 주 월요일","evidence":"교육장 안내는 제가 다음 주 월요일에 따로 보내 드릴게요."}],"due_changes":[{"task_id":"t7","new_due_raw":"11/19(목)까지","evidence":"교육 일정이 조정되어 명단 회신은 11/19(목)까지 주시면 됩니다."}],"resolved":[],"asks_me_question":true}

[예시 3] 받은 메일 · 미처리 업무 [41] 장애 보고서 초안 작성 · [42] 고객 통화 일정 잡기
본문: "보고서 초안은 운영팀 정 책임님이 어제 이미 올려 주셔서 따로 안 쓰셔도 됩니다. 고객 통화는 아직 날짜가 안 잡혔습니다. 필요하시면 지난번 통화 메모도 보내 드릴게요."
답: {"commitments":[],"due_changes":[],"resolved":[{"task_id":"41","reason":"done_by_other","evidence":"보고서 초안은 운영팀 정 책임님이 어제 이미 올려 주셔서 따로 안 쓰셔도 됩니다."}],"asks_me_question":false}
(고객 통화는 끝나지 않았으니 해결이 아니고, '필요하시면 보내 드릴게요'는 내 필요에 건 제안이라 약속이 아니다.)

[예시 4] 받은 메일 · 미처리 업무 [9] 워크숍 장소 예약
본문: "이번 달 워크숍은 내부 사정으로 열지 않기로 했습니다. 지난주에 공유드린 자료는 참고만 해 주세요."
답: {"commitments":[],"due_changes":[],"resolved":[{"task_id":"9","reason":"cancelled","evidence":"이번 달 워크숍은 내부 사정으로 열지 않기로 했습니다."}],"asks_me_question":false}

없으면 빈 목록과 false. JSON으로만 답한다."""

_SIGNAL_ITEM = {"evidence": {"type": "string"}}
SCHEMA = {
    "type": "object",
    "properties": {
        "commitments": {"type": "array", "items": {
            "type": "object",
            "properties": {"who": {"type": "string", "enum": ["me", "them"]}, "text": {"type": "string"},
                           "due_raw": {"type": "string"}, **_SIGNAL_ITEM},
            "required": ["who", "text", "due_raw", "evidence"]}},
        "due_changes": {"type": "array", "items": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}, "new_due_raw": {"type": "string"}, **_SIGNAL_ITEM},
            "required": ["task_id", "new_due_raw", "evidence"]}},
        "resolved": {"type": "array", "items": {
            "type": "object",
            "properties": {"task_id": {"type": "string"},
                           "reason": {"type": "string", "enum": ["done_by_other", "cancelled", "not_needed"]}, **_SIGNAL_ITEM},
            "required": ["task_id", "reason", "evidence"]}},
        "asks_me_question": {"type": "boolean"},
    },
    "required": ["commitments", "due_changes", "resolved", "asks_me_question"],
}


def _when(dt) -> str:
    return f"{dt:%Y-%m-%d}({WEEKDAYS[dt.weekday()]}) {dt:%H:%M}" if dt else "모름"


def build_user(req: SignalsRequest) -> str:
    m, me = req.mail, req.me
    mine = f"{me.name} <{me.email}>" if me.name else me.email
    em = me.email.lower()
    how = "받는 사람" if em in [a.lower() for a in m.recipients] else "참조" if em in [a.lower() for a in m.cc] else "배포 목록 · 기타"
    head = (["이 메일: 내가 보낸 메일"] if m.direction == "sent" else [f"이 메일: 받은 메일(나는 {how})"])
    lines = [*head, f"나: {mine}", f"보낸 사람: {m.sender}", f"받는 사람: {', '.join(m.recipients) or '없음'}",
             f"참조: {', '.join(m.cc) or '없음'}", f"보낸 시각: {_when(m.sent_at)}", f"제목: {m.subject}"]
    thread = req.thread[-THREAD_MAX:]
    if thread:
        lines.append("\n[같은 대화의 앞 메일 — 문맥만, 근거로 쓰지 않음]")
        for t in thread:
            lines.append(f"- {_when(t.sent_at)} {t.sender} · {t.subject}: {' '.join(t.body[:THREAD_CHARS].split())}")
    lines.append("\n[미처리 업무]")
    lines += [f"[{t.task_id}] {t.text} (기한 {_when(t.due_at) if t.due_at else '없음'})" for t in req.open_tasks] or ["없음"]
    lines += ["\n[본문]", m.body]
    return "\n".join(lines)
