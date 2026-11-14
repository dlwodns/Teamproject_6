"""리마인더 신호 /signals (AI-24 · AI-D20). 엑사원 대신 FakeLLM — 모델 판단은 주어진 것으로 두고 코드가 지키는 형식만 본다."""
import copy

from fastapi.testclient import TestClient

from app.api.deps import llm_dep
from app.llm.client import LLMError, LLMQuotaError, parse_json
from app.main import app
from app.pipeline.signals import ground_evidence
from tests.conftest import FakeLLM

# 2026-11-12(목) 10:00 보낸 메일
SENT_BODY = ("안녕하세요, 클라우드전환1팀 이준호입니다.\n"
             "요청하신 이관 일정표는 금요일까지 정리해서 보내 드리겠습니다.\n"
             "비용 비교표도 다음 주에 함께 공유드릴게요.\n"
             "감사합니다.\n"
             "-----\n이준호 드림")
REQ = {
    "mail_id": 31,
    "mail": {"direction": "sent", "sender": "junho.lee@lgcns.example", "recipients": ["minho.jang@hanbitbank.example"],
             "cc": [], "subject": "RE: 이관 일정 문의", "body": SENT_BODY, "sent_at": "2026-11-12T10:00:00+09:00"},
    "me": {"email": "junho.lee@lgcns.example", "name": "이준호"},
    "thread": [{"sender": "minho.jang@hanbitbank.example", "sent_at": "2026-11-11T16:20:00+09:00",
                "subject": "이관 일정 문의", "body": "이관 일정표를 받아볼 수 있을까요? " * 40}],
    "open_tasks": [{"task_id": 12, "text": "이관 일정표 보내기", "due_at": "2026-11-13T18:00:00"}],
}

RECV_BODY = ("안녕하세요, 한빛은행 장민호입니다.\n"
             "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다.\n"
             "보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다.\n"
             "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다.\n"
             "혹시 다음 주 화요일 회의 참석 가능하신지요?")


def _recv(**over):
    r = copy.deepcopy(REQ)
    r["mail"].update({"direction": "received", "sender": "minho.jang@hanbitbank.example",
                      "recipients": ["junho.lee@lgcns.example"], "subject": "RE: 이관 일정", "body": RECV_BODY})
    r["open_tasks"] = [{"task_id": 12, "text": "이관 일정표 보내기", "due_at": "2026-11-13T18:00:00"},
                       {"task_id": "13", "text": "계정 목록 보내기", "due_at": None}]
    r["mail"].update(over)
    return r


def _call(replies, req=REQ):
    fake = FakeLLM(replies)
    app.dependency_overrides[llm_dep] = lambda: fake
    try:
        with TestClient(app) as c:
            r = c.post("/signals", json=req)
            assert r.status_code == 200, r.text
            return r.json(), fake
    finally:
        app.dependency_overrides.clear()


def _model(commitments=(), due_changes=(), resolved=(), asks=False):
    return {"commitments": list(commitments), "due_changes": list(due_changes), "resolved": list(resolved),
            "asks_me_question": asks}


# ── 계약 ─────────────────────────────────────────────────────

def test_contract_shape_sent_mail():
    out, fake = _call([_model(commitments=[
        {"who": "me", "text": "이관 일정표 보내기", "due_raw": "금요일까지",
         "evidence": "요청하신 이관 일정표는 금요일까지 정리해서 보내 드리겠습니다."}])])
    assert set(out) == {"mail_id", "commitments", "due_changes", "resolved", "asks_me_question", "source", "model",
                        "prompt_version", "elapsed_ms", "dropped", "fallback", "detail"}
    assert out["mail_id"] == "31" and out["source"] == "exaone" and out["model"] == "fake-exaone"
    assert out["prompt_version"] == "signals_v1" and out["fallback"] is None and out["dropped"] == 0
    assert isinstance(out["elapsed_ms"], int)
    assert out["commitments"] == [{"who": "me", "text": "이관 일정표 보내기", "due_raw": "금요일까지",
                                   "due_at": "2026-11-13T18:00:00",
                                   "evidence": "요청하신 이관 일정표는 금요일까지 정리해서 보내 드리겠습니다."}]
    assert out["due_changes"] == [] and out["resolved"] == [] and out["asks_me_question"] is False


def test_prompt_has_context_and_thread_is_cut():
    _, fake = _call([_model()])
    user = fake.calls[0]["user"]
    assert "이 메일: 내가 보낸 메일" in user and "2026-11-12(목) 10:00" in user
    assert "[12] 이관 일정표 보내기 (기한 2026-11-13(금) 18:00)" in user
    thread_line = next(ln for ln in user.splitlines() if ln.startswith("- 2026-11-11"))
    assert len(thread_line) < 400 + 80  # 앞 메일은 400자까지만
    assert user.rstrip().endswith("이준호 드림")


def test_thread_keeps_latest_five_and_accepts_snippet_alias():
    req = copy.deepcopy(REQ)
    req["thread"] = [{"sender": f"s{i}@x.example", "sent_at": f"2026-11-0{i + 1}T09:00:00", "subject": f"제목{i}",
                      "snippet": f"앞 메일 {i}"} for i in range(7)]
    _, fake = _call([_model()], req)
    user = fake.calls[0]["user"]
    assert "앞 메일 0" not in user and "앞 메일 1" not in user and "앞 메일 2" in user and "앞 메일 6" in user


def test_full_received_mail():
    out, _ = _call([_model(
        commitments=[{"who": "them", "text": "보안 점검 결과 보내기", "due_raw": "내일 오전 중",
                      "evidence": "보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다."}],
        due_changes=[{"task_id": "12", "new_due_raw": "11/20까지",
                      "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."}],
        resolved=[{"task_id": "13", "reason": "done_by_other",
                   "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."}],
        asks=True)], _recv())
    assert out["commitments"][0]["who"] == "them" and out["commitments"][0]["due_at"] == "2026-11-13T12:00:00"
    assert out["due_changes"] == [{"task_id": "12", "new_due_raw": "11/20까지", "new_due_at": "2026-11-20T18:00:00",
                                   "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."}]
    assert out["resolved"] == [{"task_id": "13", "reason": "done_by_other",
                                "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."}]
    assert out["asks_me_question"] is True and out["dropped"] == 0


# ── 근거는 본문에 글자 그대로 ─────────────────────────────────

def test_evidence_must_be_in_body():
    out, _ = _call([_model(commitments=[
        {"who": "me", "text": "일정표 보내기", "due_raw": "금요일까지", "evidence": "금요일까지 일정표를 드리겠습니다."},  # 바꿔 씀
        {"who": "me", "text": "인사", "due_raw": "", "evidence": "감사"},  # 너무 짧음
        {"who": "me", "text": "비용 비교표 공유", "due_raw": "다음 주",
         "evidence": "비용 비교표도   다음 주에\n함께 공유드릴게요."}])])  # 공백만 다름 → 본문 문장 그대로 돌려줌
    assert [c["text"] for c in out["commitments"]] == ["비용 비교표 공유"]
    assert out["commitments"][0]["evidence"] == "비용 비교표도 다음 주에 함께 공유드릴게요."
    assert out["dropped"] == 2


def test_evidence_from_thread_subject_or_signature_is_dropped():
    out, _ = _call([_model(commitments=[
        {"who": "me", "text": "회신", "due_raw": "", "evidence": "이관 일정표를 받아볼 수 있을까요?"},  # 앞 메일 글자
        {"who": "me", "text": "회신", "due_raw": "", "evidence": "RE: 이관 일정 문의"},  # 제목
        {"who": "me", "text": "서명", "due_raw": "", "evidence": "이준호 드림"}])])  # 구분선 아래
    assert out["commitments"] == [] and out["dropped"] == 3


def test_evidence_spanning_two_sentences_returns_both():
    sents = ["요청하신 이관 일정표는 금요일까지 정리해서 보내 드리겠습니다.", "비용 비교표도 다음 주에 함께 공유드릴게요."]
    got = ground_evidence("보내 드리겠습니다. 비용 비교표도", sents)
    assert got == "\n".join(sents)
    assert ground_evidence("없는 문장입니다", sents) is None



# 답장 · 전달로 붙은 앞 메일(인용)은 이 메일이 쓴 글이 아니다. 내가 보낸 약속이 상대 약속으로 잡히면 안 된다
QUOTED_PROMISE = "수정본은 금요일까지 보내 드리겠습니다."


def test_quoted_reply_is_not_evidence():
    quotes = [
        "네, 확인했습니다.\n\n________________________________\n보낸 사람: 이준호\n보낸 날짜: 2026년 11월 11일 수요일 오후 3:00\n\n",
        "네, 확인했습니다.\n\nFrom: 이준호 <junho.lee@lgcns.example>\nSent: Wednesday, November 11, 2026 3:00 PM\n\n",
        "네, 확인했습니다.\n\n2026년 11월 11일 (수) 오후 3:00, 이준호 <junho.lee@lgcns.example>님이 작성:\n> ",
        "네, 확인했습니다.\n\nOn Wed, Nov 11, 2026 at 3:00 PM 이준호 wrote:\n> ",
    ]
    for q in quotes:
        out, _ = _call([_model(commitments=[{"who": "them", "text": "수정본 보내기", "due_raw": "금요일까지",
                                              "evidence": QUOTED_PROMISE}])], _recv(body=q + QUOTED_PROMISE))
        assert out["commitments"] == [] and out["dropped"] == 1, q


def test_body_without_own_sentence_does_not_call_model():
    for body in ["감사합니다.\n-----\n이준호 드림",
                 "-----Original Message-----\nFrom: 이준호\n" + QUOTED_PROMISE,
                 "\n\n________________________________\n보낸 사람: 이준호\n\n" + QUOTED_PROMISE]:
        out, fake = _call([], _recv(body=body))
        assert fake.calls == [] and out["source"] == "none" and out["fallback"] == "empty_body", body


def test_evidence_matches_despite_invisible_and_fullwidth_chars():
    sents = ["견적서는\u200b 11/20（목）까지 보내 드리겠습니다."]  # 폭 없는 공백 · 전각 괄호가 든 본문
    assert ground_evidence("견적서는 11/20(목)까지 보내 드리겠습니다.", sents) == sents[0]
    nfd = "\u1100\u1161\u11ab\u1103\u1161\u11ab\u1112\u1175 \uc790\ub8cc \ubcf4\ub0b4 \ub4dc\ub9b4\uac8c\uc694."  # 맥 메일의 풀어 쓴 한글
    assert ground_evidence("간단히 자료 보내 드릴게요.", [nfd]) == nfd


def test_evidence_of_non_adjacent_sentences_returns_each():
    sents = ["견적서는 금요일까지 보내 드리겠습니다.", "회의실은 3층입니다.", "일정표도 함께 드릴게요."]
    got = ground_evidence("견적서는 금요일까지 보내 드리겠습니다.\n일정표도 함께 드릴게요.", sents)
    assert got == "견적서는 금요일까지 보내 드리겠습니다.\n일정표도 함께 드릴게요."
    assert ground_evidence("견적서는 금요일까지 보내 드리겠습니다.\n없는 문장입니다.", sents) is None

# ── 날짜: sent_at 기준, 못 정하면 null ───────────────────────

def _due(raw, sent_at="2026-11-12T10:00:00+09:00", body=None):
    req = copy.deepcopy(REQ)
    req["mail"]["sent_at"] = sent_at
    ev = f"자료는 {raw} 보내 드리겠습니다."
    req["mail"]["body"] = body or ev
    out, _ = _call([_model(commitments=[{"who": "me", "text": "자료 보내기", "due_raw": raw, "evidence": ev}])], req)
    c = out["commitments"][0]
    return c["due_raw"], c["due_at"]


def test_dates_relative_to_sent_at():
    assert _due("금요일까지") == ("금요일까지", "2026-11-13T18:00:00")  # 목요일에 보낸 메일 → 다음 날
    assert _due("금요일까지", "2026-11-13T10:00:00+09:00")[1] == "2026-11-20T18:00:00"  # 금요일에 보낸 메일 → 다음 주
    assert _due("내일 오전") == ("내일 오전", "2026-11-13T12:00:00")
    assert _due("11/20") == ("11/20", "2026-11-20T18:00:00")
    assert _due("11/20(금) 오후 3시까지") == ("11/20(금) 오후 3시까지", "2026-11-20T15:00:00")
    assert _due("오늘 중으로") == ("오늘 중으로", "2026-11-12T18:00:00")
    assert _due("다음 주 초에") == ("다음 주 초에", "2026-11-17T18:00:00")


def test_unparseable_due_keeps_raw():
    assert _due("다음 주") == ("다음 주", None)  # 날짜를 정할 수 없다 — 지어내지 않는다
    assert _due("최대한 빨리") == ("최대한 빨리", None)  # ASAP


def test_sent_at_utc_is_converted_to_kst():
    assert _due("내일 오전", "2026-11-12T16:00:00Z")[1] == "2026-11-14T12:00:00"  # UTC 16시 = KST 13일 01시


def test_hallucinated_due_is_removed_but_commitment_kept():
    out, _ = _call([_model(commitments=[{"who": "me", "text": "이관 일정표 보내기", "due_raw": "11/30까지",
                                         "evidence": "요청하신 이관 일정표는 금요일까지 정리해서 보내 드리겠습니다."}])])
    c = out["commitments"][0]
    assert c["due_raw"] is None and c["due_at"] is None


def test_due_only_in_quoted_mail_is_removed():
    # 기한 문구가 앞 메일(인용)에만 있으면 이 메일의 약속 기한으로 붙이지 않는다(#83 리뷰)
    body = ("네, 자료는 정리해서 보내 드리겠습니다.\n\nFrom: 이준호 <junho.lee@lgcns.example>\n"
            "Sent: Wednesday, November 11, 2026 3:00 PM\n\n11/30까지 부탁드립니다.")
    out, _ = _call([_model(commitments=[{"who": "them", "text": "자료 보내기", "due_raw": "11/30까지",
                                         "evidence": "네, 자료는 정리해서 보내 드리겠습니다."}])], _recv(body=body))
    c = out["commitments"][0]
    assert c["due_raw"] is None and c["due_at"] is None


# ── task_id는 open_tasks 안에서만 ─────────────────────────────

def test_task_id_must_be_in_open_tasks():
    out, _ = _call([_model(
        due_changes=[{"task_id": "99", "new_due_raw": "11/20까지",
                      "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."},
                     {"task_id": "12", "new_due_raw": "11/20까지",
                      "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."},
                     {"task_id": "12", "new_due_raw": "11/20까지",  # 같은 업무 두 번째
                      "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."}],
        resolved=[{"task_id": "t13", "reason": "done_by_other",
                   "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."},
                  {"task_id": "13", "reason": "finished",  # 없는 이유
                   "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."}])], _recv())
    assert [d["task_id"] for d in out["due_changes"]] == ["12"]
    assert out["resolved"] == [] and out["dropped"] == 4


def test_due_change_needs_grounded_new_due_and_must_differ():
    req = _recv()
    req["open_tasks"][0]["due_at"] = "2026-11-20T18:00:00"
    out, _ = _call([_model(due_changes=[
        {"task_id": "12", "new_due_raw": "11/20까지",  # 지금 기한과 같음
         "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."},
        {"task_id": "13", "new_due_raw": "11/27까지",  # 메일에 없는 기한
         "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."}])], req)
    assert out["due_changes"] == [] and out["dropped"] == 2


def test_no_open_tasks_drops_task_signals():
    req = _recv()
    req["open_tasks"] = []
    out, fake = _call([_model(resolved=[{"task_id": "13", "reason": "done_by_other",
                                         "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."}])], req)
    assert out["resolved"] == [] and "[미처리 업무]\n없음" in fake.calls[0]["user"]


# ── 보낸 메일 · 받은 메일 ─────────────────────────────────────

def test_who_must_match_direction():
    ev = "보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다."
    out, _ = _call([_model(commitments=[{"who": "me", "text": "보안 점검 결과", "due_raw": "", "evidence": ev}])], _recv())
    assert out["commitments"] == [] and out["dropped"] == 1  # 받은 메일의 약속은 상대(them) 것
    ev = "요청하신 이관 일정표는 금요일까지 정리해서 보내 드리겠습니다."
    out, _ = _call([_model(commitments=[{"who": "them", "text": "일정표", "due_raw": "", "evidence": ev}])])
    assert out["commitments"] == [] and out["dropped"] == 1  # 보낸 메일의 약속은 내(me) 것


def test_sent_mail_never_asks_me():
    out, _ = _call([_model(asks=True)])
    assert out["asks_me_question"] is False


def test_received_prompt_says_how_i_received():
    _, fake = _call([_model()], _recv(recipients=["a@x.example"], cc=["junho.lee@lgcns.example"]))
    assert "받은 메일(나는 참조)" in fake.calls[0]["user"]


# ── 모델 실패 · 이상한 답 · 빈 본문 ───────────────────────────

def test_model_failure_is_fallback_not_error():
    out, _ = _call([LLMError("엑사원 API 호출 실패: HTTP 503(다시 부르기 3회)")])
    assert out["source"] == "none" and out["fallback"] == "model_failed" and "HTTP 503" in out["detail"]
    assert out["commitments"] == [] and out["due_changes"] == [] and out["resolved"] == []
    out, _ = _call([LLMQuotaError("엑사원 API 하루 호출 한도 소진(x-day-rate-limit 100)")])
    assert out["fallback"] == "quota"


def test_invalid_json_is_model_failed():
    try:  # 실제 호출부는 JSON이 아닌 답을 parse_json에서 LLMError로 올린다
        parse_json("모르겠습니다. 이 메일에는 약속이 없어 보입니다")
    except LLMError as e:
        err = e
    out, _ = _call([err])
    assert out["source"] == "none" and out["fallback"] == "model_failed"


def test_garbage_shape_is_bad_output():
    for garbage in ({"answer": "없음"}, {"commitments": "없음", "due_changes": [], "resolved": [], "asks_me_question": False},
                    {"commitments": [], "due_changes": [], "resolved": [], "asks_me_question": "yes"}):
        out, _ = _call([garbage])
        assert out["source"] == "none" and out["fallback"] == "bad_output", garbage


def test_garbage_items_are_dropped():
    out, _ = _call([_model(commitments=["문자열", None, {"who": "me"}, {"who": "me", "text": "", "evidence": "x"}],
                           due_changes=[42], resolved=[[]])])
    assert out["source"] == "exaone" and out["commitments"] == [] and out["dropped"] == 6


def test_empty_body_does_not_call_model():
    req = copy.deepcopy(REQ)
    req["mail"]["body"] = "  \n "
    out, fake = _call([], req)
    assert fake.calls == [] and out["source"] == "none" and out["fallback"] == "empty_body"


def test_bad_request_is_422():
    req = copy.deepcopy(REQ)
    req["mail"]["direction"] = "forwarded"
    app.dependency_overrides[llm_dep] = lambda: FakeLLM([])
    try:
        assert TestClient(app).post("/signals", json=req).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_classify_untouched_by_signals_router():
    paths = set(app.openapi()["paths"])
    assert {"/classify", "/signals", "/memory/extract"} <= paths
