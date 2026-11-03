"""메일 성격(kind) 표와 형식 맞추기 점수기 (유형 체계 kinds-v1, 2026-11-03).

기존 9유형(action_types)에 메일을 바로 끼우지 않고, dev · dev2 · dev3 메일 207통을 읽어 실제로 갈리는 성격 21개를 먼저 정했다.
kind마다 부모 유형(9유형 중 하나, 호환 · 채점용) · 칸(할 일 / 확인 / 참고) · 형식(필수 · 보조 · 배제 신호) · 뽑을 칸을 둔다.
신호는 signals.py의 이름만 쓴다(유형 무관 구조 신호 · 범주 어휘).

점수: 필수 묶음(need) 중 하나라도 모두 참이고 배제(exclude)가 하나도 참이 아니면 후보다. 점수 = 1 + 참인 보조 신호 가중치 합.
확신: 1등과, 부모 유형이 다른 kind 중 1등의 차이(margin). 차이가 작거나, kind는 할 일인데 규칙이 할 일을 못 찾았거나(누락 의심), 그 반대이면 엑사원행으로 표시한다.
할 일 탐지(재현율)는 규칙 v1.5를 그대로 쓴다. kind는 유형 · 칸만 정한다(누락을 만들지 않는다, D15).

신호 표기: 'a&b&!c' = a 그리고 b 그리고 c 아님. 가중치는 dev + dev2로 맞췄고 dev3는 검증용이다(eval/runners/run_kinds.py).
dev3 첫 채점(주 유형 88.3%) 뒤 오답을 보고 한 번 고쳤다('~주시면' 요청 · 단체 회의 참석 요청 · 초대 시각 · 할 일 문장 범위) → dev3도 일부 맞춘 세트다.
"""
from dataclasses import dataclass, field

from app.pipeline.signals import SIGNALS, Signals, extract

ACTION_TYPES = ["자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석", "공지", "참조", "회신", "기타"]
TASK_TYPES = {"자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석"}
LANES = ("할 일", "확인", "참고")

MARGIN_MIN = 1.0  # 1등과 '부모 유형이 다른 1등'의 차이가 이보다 작으면 애매 → 엑사원행 (dev + dev2에서 0.5~2.0을 재 보고 고름)
SCORE_MIN = 2.0  # 1등 점수가 이보다 낮으면 형식 근거가 약하다 → 엑사원행

REQ = ("request_loose", "follow_up&subj_request", "rule_task")  # 요청 계열 필수: 나를 향한 요청이 있거나 재요청
NO_REQ = {"request_loose": -1.5, "rule_task": -1.5}  # 할 일 없는 kind는 나를 향한 요청이 있으면 깎인다
PROMO_OUT = {"external&promo_word": -2.0}  # 사외 홍보 · 초청의 '등록해 주세요'는 할 일 요청이 아니다
NOTICE_FRAME = {"list_me&subj_notice": -1.0}  # 단체 공지 틀 안의 요청은 공지 속 지목(K11)이 먼저다
REQ_COMMON = {**PROMO_OUT, **NOTICE_FRAME}


@dataclass(frozen=True)
class Kind:
    id: str
    name: str
    definition: str
    parent: str  # 9유형 중 하나. 요청 계열은 요청 유형, 할 일 없는 계열은 그 유형
    lane: str  # 할 일 | 확인 | 참고
    need: tuple[str, ...]
    support: dict[str, float]
    exclude: tuple[str, ...] = ()
    slots: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()  # kinds_gold.json 기준 메일 ID(세트:ID)


KINDS: list[Kind] = [
    # ---------- 요청 계열 (칸: 할 일) ----------
    Kind("K01", "자료 제출 요청", "자료 · 양식 · 문서 · 목록 · 파일을 작성하거나 있는 것을 보내 달라", "자료제출요청", "할 일", REQ,
         {"obj_artifact": 1.5, "obj_send": 1.0, "obj_create": 0.5, "subj_artifact": 0.7, "obj_message_form": -0.7, "obj_opinion": -0.5,
          "obj_review": -1.0, "obj_approve": -1.0, "obj_revise&ref_prior_mine": -1.0, "subj_resend": -0.7, "obj_reply_verb&!obj_create": -0.5,
          **REQ_COMMON},
         slots=("산출물", "형식(xlsx · pptx · pdf …)", "양식 첨부 여부", "제출처", "기한"),
         examples=("dev:M-0001", "dev:M-0077", "dev3:M-0013", "dev3:M-0057")),
    Kind("K02", "정정 · 재전송 요청", "내가 보낸 것의 오류 · 누락 · 형식을 고쳐 다시 보내거나 원본을 달라", "수정재전송요청", "할 일", REQ,
         {"obj_revise": 1.0, "obj_again": 1.0, "ref_prior_mine": 1.0, "subj_resend": 2.0, **REQ_COMMON},
         slots=("대상 문서", "고칠 곳", "원하는 형식", "기한"), examples=("dev:M-0006", "dev:M-0031", "dev3:M-0022")),
    Kind("K03", "문서 검토 요청", "초안 · 자료를 봐 달라, 검토 의견을 달라", "검토승인요청", "할 일", REQ,
         {"obj_review": 2.0, "subj_review": 1.0, "has_attachment": 0.3, "obj_approve": -0.5, **REQ_COMMON},
         slots=("검토 대상", "볼 부분", "기한"), examples=("dev:M-0019", "dev3:M-0001", "dev3:M-0042")),
    Kind("K04", "결재 · 승인 요청", "전자결재 · 품의 · 승인 · 서명을 해 달라", "검토승인요청", "할 일", REQ,
         {"obj_approve": 2.0, "subj_approve": 1.5, **REQ_COMMON},
         slots=("결재 대상", "결재 시스템", "금액 · 기간", "기한"), examples=("dev:M-0015", "dev3:M-0021", "dev3:M-0025")),
    Kind("K05", "의견 · 판단 요청", "의견 · 아이디어 · 방향 · 진행 여부를 정해 달라", "회신요청", "할 일", REQ,
         {"obj_opinion": 1.5, "obj_whether": 0.7, "subj_opinion": 0.7, "obj_message_form": 0.3, "obj_reply_verb": 0.3, "obj_artifact": -0.5,
          "obj_schedule": -1.0, "obj_attend": -1.0, **REQ_COMMON},
         slots=("물어본 것", "선택지", "기한"), examples=("dev:M-0014", "dev2:M-0046", "dev3:M-0032")),
    Kind("K06", "사실 · 현황 회신 요청", "현황 · 명단 · 인원 · 원인 같은 사실을 회신하거나 짧게 보고해 달라", "회신요청", "할 일", REQ,
         {"obj_info": 1.5, "obj_message_form": 0.7, "obj_reply_verb&!obj_artifact": 0.7, "obj_opinion": -0.3,
          "obj_artifact&obj_create": -0.7, **REQ_COMMON},
         slots=("알려 줄 내용", "형식(메일 · 한 줄)", "기한"), examples=("dev:M-0023", "dev:M-0073", "dev3:M-0030")),
    Kind("K07", "개인 사정 가부 문의", "팀원이 연차 · 재택 · 교육 같은 자기 일의 허락을 묻는다", "회신요청", "할 일", REQ,
         {"wish_first_person": 2.5, "obj_whether": 0.5, "addressed_me": 0.3, **REQ_COMMON},
         exclude=("external",),
         slots=("묻는 사람", "날짜", "사유", "답 기한"), examples=("dev:M-0057", "dev2:M-0045", "dev3:M-0027")),
    Kind("K08", "일정 조율", "가능한 날짜 · 시간 · 희망 일자를 알려 달라", "회신요청", "할 일", REQ,
         {"obj_schedule": 2.5, "meeting_word&obj_whether&!has_time": 1.5, **REQ_COMMON},
         slots=("모임", "후보 날짜", "답 기한"), examples=("dev:M-0100", "dev3:M-0036", "dev3:M-0056")),
    Kind("K09", "회의 · 행사 초대", "회의 · 행사 일시를 알리고 참석(또는 참석 여부 회신)을 바란다", "일정참석", "할 일",
         ("meeting_word&has_time", "meeting_block"),
         {"meeting_block": 1.5, "invite_word": 0.7, "invite_word&has_time": 0.7, "obj_attend": 1.0, "obj_attend&obj_whether": 0.5, "tag_meeting": 0.7, "subj_change": -1.0, "reply": -1.5,
          "done_word": -1.0, "answer_word": -1.0},
         exclude=("external&promo_word", "minutes_word&!rule_task"),
         slots=("일시", "장소", "참석 여부 회신 필요", "회신 기한"), examples=("dev:M-0026", "dev:M-0055", "dev3:M-0049")),
    Kind("K10", "일정 변경 알림", "이미 잡힌 회의의 시간 · 장소가 바뀌었다", "일정참석", "할 일", ("meeting_word&schedule_change",),
         {"subj_change": 1.5, "schedule_change": 1.0, "has_time": 0.5, "tag_meeting": 0.5, "reply": -1.0},
         exclude=("external&promo_word",),
         slots=("회의", "바뀐 일시 · 장소", "이전 일시"), examples=("dev:M-0070", "dev:M-0092", "dev3:M-0044")),
    Kind("K11", "공지 속 지목 요청", "단체 공지 안에서 내 이름 · 팀 · 직급을 지목해 무언가를 요청한다", "공지", "할 일",
         ("list_me&mentions_me&request_loose", "list_me&list_mentions_me&rule_task"),
         {"subj_notice": 1.0, "notice_word": 0.7, "list_mentions_me": 1.0, "role_mention_me": 1.0, "mentions_me": 0.5, "tag_notice": 0.5,
          "list_me": 1.0, "meeting_word&has_time&obj_attend": -1.5},  # 단체로 온 회의 참석 요청은 회의 초대(K09)다(라벨 관례)
         exclude=("external",),
         slots=("공지 요지", "나에게 한 요청", "지목 근거(이름 · 팀 · 직급 · 목록)", "기한"), examples=("dev:M-0009", "dev:M-0059", "dev3:M-0046")),
    # ---------- 할 일 없는 계열 ----------
    Kind("K12", "완료 보고", "맡긴 · 요청한 일을 처리했다고 알린다", "회신", "확인", ("done_word",),
         {"reply": 1.0, "done_word": 1.5, "tag_share": 0.5, "subj_done": 1.0, **NO_REQ},
         slots=("완료된 일", "후속 안내(접속 시각 · 수령 방법)"), examples=("dev:M-0041", "dev2:M-0047", "dev3:M-0008")),
    Kind("K13", "자료 · 답변 회신", "내 요청 · 문의에 자료를 첨부하거나 답을 준다", "회신", "확인",
         ("reply&answer_word", "answer_word&!request_loose"),
         {"reply": 1.0, "answer_word": 1.5, "ref_prior_mine": 0.3, "done_word": -1.0, **NO_REQ},
         slots=("받은 자료 · 답", "내 원래 요청"), examples=("dev:M-0010", "dev:M-0071", "dev2:M-0019")),
    Kind("K14", "수신 확인", "보낸 것을 받았다 · 확인했다고 알린다. 추가 조치 없음", "회신", "참고", ("ack_word",),
         {"reply": 1.0, "no_reply_needed": 1.0, "ack_word": 1.5, **NO_REQ},
         slots=("받은 것",), examples=("dev3:M-0052", "dev3:M-0054")),
    Kind("K15", "공유 · 참조", "참고용 자료 · 결과 · 메모를 공유하거나, 남에게 보낸 메일에 나를 참조로 넣었다", "참조", "참고",
         ("cc_me", "share_word&!request_loose", "tag_share&!request_loose"),
         {"cc_me": 1.5, "addressed_other": 1.0, "share_word": 0.7, "tag_share": 0.5, "cc_note": 0.5, "no_reply_needed": 0.5, "minutes_word": -1.0,
          **NO_REQ},
         slots=("공유한 것", "원래 받는 사람"), examples=("dev:M-0008", "dev:M-0036", "dev3:M-0012")),
    Kind("K16", "회의록", "회의록 공유. 결정 사항 · 액션이 나에게 걸리지 않았다", "참조", "참고", ("minutes_word",),
         {"tag_minutes": 1.5, "minutes_word": 2.5, "share_word": 0.3, **NO_REQ},
         slots=("회의", "결정 사항"), examples=("dev:M-0025", "dev3:M-0043")),
    Kind("K17", "사내 안내 공지", "사내 부서가 여러 팀에 보내는 제도 · 일정 · 점검 · 시설 안내(조치 당부 없음)", "공지", "참고",
         ("list_me&!external",),
         {"subj_notice": 1.0, "notice_word": 1.0, "tag_notice": 0.5, "opt_in": 0.3, "request_any": -0.8, **NO_REQ},
         slots=("안내 요지", "적용 일시"), examples=("dev:M-0004", "dev:M-0028", "dev3:M-0010")),
    Kind("K18", "대상자 당부 공지", "단체 안내에서 해당자 · 미이수자 · 전 직원에게 조치를 당부한다(나를 지목하지 않음)", "공지", "확인",
         ("list_me&request_any&!external",),
         {"subj_notice": 0.7, "notice_word": 0.5, "general_audience": 1.5, "request_any": 1.0, "tag_notice": 0.3, "opt_in": -1.0, **NO_REQ},
         slots=("대상", "조치", "기한"), examples=("dev:M-0078", "dev2:M-0025", "dev3:M-0059")),
    Kind("K19", "사외 홍보 · 초청", "사외 업체 · 단체의 세미나 · 웨비나 · 포럼 초청, 영업 · 갱신 안내, 뉴스레터", "기타", "참고", ("external",),
         {"promo_word": 2.0, "role_account": 0.7, "no_greeting": 0.5, "bulk_mark": 1.0, "tag_promo": 0.7,
          "request_loose": -0.5, "rule_task": -0.5},
         slots=("행사 · 상품", "일시", "등록 기한"), examples=("dev:M-0033", "dev3:M-0005", "dev3:M-0029")),
    Kind("K20", "사내 소식", "사내 뉴스레터 · 동호회 · 복지 · 이벤트 소식", "기타", "참고",
         ("news_word&!external", "role_account&no_greeting&!external"),
         {"news_word": 2.0, "role_account": 0.7, "no_greeting": 0.7, "tag_promo": 1.0, "opt_in": 0.3, "request_loose": -0.5, "rule_task": -0.5},
         slots=("소식 요지",), examples=("dev:M-0003", "dev2:M-0023")),
    Kind("K21", "시스템 자동 알림", "모니터링 · 시스템이 자동 발송한 알림", "기타", "확인",
         ("alert_word&bulk_mark", "alert_word&no_greeting", "alert_word&role_account"),
         {"alert_word": 1.5, "bulk_mark": 1.0, "no_greeting": 0.5, "tag_alert": 1.0, "request_loose": -0.5, "rule_task": -0.5},
         slots=("대상 시스템", "지표 · 값", "발생 시각"), examples=("dev3:M-0004",)),
]
BY_ID = {k.id: k for k in KINDS}


def _holds(expr: str, sig: Signals) -> bool:
    return all(term in sig for term in expr.split("&"))


def terms(expr: str) -> list[str]:
    """'a&!b' → ['a', 'b'] (신호 이름 확인용)."""
    return [t.lstrip("!") for t in expr.split("&")]


@dataclass
class KindResult:
    kind: Kind | None
    second: Kind | None
    score: float
    margin: float
    scores: dict[str, float]
    signals: Signals
    needs_model: bool
    why: list[str] = field(default_factory=list)  # 엑사원행 사유

    @property
    def lane(self) -> str | None:
        return self.kind.lane if self.kind else None


def score(sig: Signals) -> KindResult:
    scores = {}
    for k in KINDS:
        if any(_holds(e, sig) for e in k.exclude) or not any(_holds(e, sig) for e in k.need):
            continue
        scores[k.id] = 1.0 + sum(w for e, w in k.support.items() if _holds(e, sig))
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return KindResult(None, None, 0.0, 0.0, scores, sig, True, ["맞는 형식 없음"])
    (top, s1), second = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0.0)
    kind = BY_ID[top]
    # 여유는 부모 유형이 다른 kind 중 1등과 잰다. 같은 부모끼리(의견 vs 사실 회신 등) 헷갈림은 유형 · 할 일을 바꾸지 않아 엑사원에 묻지 않는다
    rival = next(((i, v) for i, v in ranked[1:] if BY_ID[i].parent != kind.parent), (None, 0.0))
    margin = s1 - rival[1]
    why = []
    if margin < MARGIN_MIN:
        why.append(f"애매({top} {s1:.1f} vs {rival[0]} {rival[1]:.1f})")
    if s1 < SCORE_MIN:
        why.append(f"형식 근거 약함({s1:.1f})")
    if kind.lane == "할 일" and "rule_task" not in sig.on and kind.id not in ("K09", "K10"):
        why.append("요청 형식인데 규칙 할 일 없음(누락 의심)")
    if kind.lane != "할 일" and "rule_task" in sig.on:
        why.append("할 일 없는 형식인데 규칙 할 일 있음")
    return KindResult(kind, BY_ID.get(second[0]) if second[0] else None, s1, margin, scores, sig, bool(why), why)


def classify_kind(req, rule=None) -> KindResult:
    return score(extract(req, rule))


def kind_types(res: KindResult, rule_types: list[str]) -> list[str]:
    """kind로 정한 action_types. 주 유형은 kind 부모, 뒤에는 규칙이 찾은 다른 요청 유형(요청 2개 메일)."""
    if res.kind is None:
        return list(rule_types)
    p = res.kind.parent
    rest = [t for t in rule_types if t in TASK_TYPES and t != p]
    if res.kind.lane == "할 일" and "rule_tasks_2" in res.signals:  # 요청 여럿: 주 유형은 규칙 관례(산출물 우선)
        return list(rule_types)
    if p in TASK_TYPES or (p == "공지" and res.kind.lane == "할 일"):
        return [p, *rest]
    return [p]


def all_signal_names() -> set[str]:
    """표가 쓰는 신호 이름(test_kinds가 SIGNALS 안에 있는지 확인)."""
    out = set()
    for k in KINDS:
        for e in (*k.need, *k.support, *k.exclude):
            out.update(terms(e))
    return out


assert all_signal_names() <= set(SIGNALS), all_signal_names() - set(SIGNALS)
