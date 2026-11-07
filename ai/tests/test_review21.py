"""PR #21 리뷰 반영: 규칙 기한 우선의 같은 요청 판정 · 기한 문맥 찾기 · 설정 값 확인."""
from datetime import datetime

import pytest

from app.core.config import Settings, get_settings
from app.pipeline.classify import _context, _rule_due_first
from app.pipeline.dates import DueParse, parse_deadline
from app.pipeline.rules.mail_rules_v1 import RuleResult, RuleTask
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags, TaskOut

ME = "me@corp.example"
OWNER = OwnerProfile(email=ME, name="김나래", position="팀장", team="데이터1팀", member_of=[])
D20, D21, D22 = (datetime(2026, 11, d, 18) for d in (20, 21, 22))


def rules(*tasks):
    return RuleResult(["회신요청"], list(tasks), True, False, False, "to", 0.9)


def rtask(text, evidence, due):
    return RuleTask(text=text, action_type="회신요청", evidence=evidence, due=DueParse(due[0], due[1]))


def mtask(text, raw=None, at=None):
    return TaskOut(text=text, due_raw=raw, due_at=at)


def test_rule_due_does_not_overwrite_other_request():
    # 규칙은 요청 1개('견적서 회신')만 찾았고, 엑사원은 기한이 다른 요청 2개를 찾았다.
    # 규칙 요청 문장에 '자료'가 있어도 '발표 자료 공유'는 다른 요청이라 엑사원 기한을 둔다
    r = rules(rtask("견적서 회신", "견적서와 자료는 11/20까지 회신해 주세요", ("11/20까지", D20)))
    a, b = mtask("견적서 회신", "11/21까지", D21), mtask("발표 자료 공유", "11/22까지", D22)
    _rule_due_first(r, [a, b])
    assert a.due_at == D20 and b.due_at == D22


def test_rule_due_wins_when_one_to_one():
    # dev M-0060 원리: 할 일 1개씩이면 같은 요청이다. 요청 문장의 기한('오늘 중으로')을 쓴다
    r = rules(rtask("원본 파일 재전송", "고객이 내일 오전까지 원해서 오늘 중으로 받을 수 있을까요", ("오늘 중으로", D20)))
    t = mtask("다이어그램 원본 파일 재전송", "내일 오전까지", D21)
    _rule_due_first(r, [t])
    assert t.due_raw == "오늘 중으로" and t.due_at == D20


def test_rule_due_overwrites_only_one_model_task():
    # 규칙 할 일 하나는 가장 닮은 엑사원 할 일 하나만 덮는다
    r = rules(rtask("보고서 제출", "보고서는 11/20까지 제출해 주세요", ("11/20까지", D20)))
    a, b = mtask("보고서 제출", "11/21까지", D21), mtask("보고서 제출 결과 회신", "11/22까지", D22)
    _rule_due_first(r, [a, b])
    assert a.due_at == D20 and b.due_at == D22


def test_empty_model_due_is_filled_as_before():
    # 엑사원이 기한을 비운 할 일은 v3.2처럼 닮은 규칙 할 일 기한으로 채운다
    r = rules(rtask("견적서 회신", "견적서는 11/20까지 회신해 주세요", ("11/20까지", D20)))
    a, b = mtask("견적서 회신"), mtask("발표 자료 공유", "11/22까지", D22)
    _rule_due_first(r, [a, b])
    assert a.due_at == D20 and b.due_at == D22


@pytest.mark.parametrize("raw", ["10/22(목)", "10/22 (목)", "10/22 목"])
def test_context_ignores_spacing(raw):
    # 근거 확인(_squash)을 통과한 기한 글자는 띄어쓰기 · 괄호가 달라도 원문 자리를 찾아 마감 표지를 함께 본다
    req = ClassifyRequest(**{"from": "a@corp.example"}, mail_id="X-1", to=[ME], cc=[], subject="문의",
                          body="발표 자료는 10/22(목)까지 보내 주세요.", attachments=[], received_at="2026-10-19T09:00",
                          owner=OWNER, sender=SenderFlags())
    due = parse_deadline(_context(raw, req), datetime(2026, 10, 19, 9))
    assert due and due.due_at == datetime(2026, 10, 22, 18)


@pytest.mark.parametrize("name,value", [("ROUTER_MODE", "al"), ("LLM_BACKEND", "olama")])
def test_bad_setting_stops_start(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        get_settings()


def test_good_settings():
    assert Settings().router_mode == "all" and Settings(router_mode="gate").router_mode == "gate"
