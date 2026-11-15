"""개인정보 가리기 (BE-6 · D34): ai로 보내기 전에 가리고, 응답은 되돌린다. 판단에 쓰는 부분(도메인 · 성 · 자동 발신)은 남긴다."""
from datetime import datetime

import pytest

from app.models import Contact, User
from app.privacy import Masker, enabled, masker_for
from app.schemas.ai import ClassifyResult


# ---------- 메일 주소 ----------

def test_email_keeps_domain_and_is_consistent():
    m = Masker()
    out = m.mask_obj({"from": "Minjun.Kim@lgcns.example", "to": ["minjun.kim@lgcns.example", "park@bank.example"],
                      "body": "minjun.kim@lgcns.example로 보내 주세요"})
    a, b = out["to"]
    assert out["from"] == a == "user1@lgcns.example" and b == "user2@bank.example"  # 대소문자가 달라도 같은 사람
    assert out["body"] == "user1@lgcns.example로 보내 주세요"


@pytest.mark.parametrize("addr", ["noreply@lgcns.example", "no-reply@x.example", "info@x.example",
                                  "newsletter@x.example", "Admin@x.example"])
def test_automatic_sender_local_part_is_kept(addr):
    assert Masker().mask_text(addr) == addr  # ai 자동 메일 판별(AUTO_SENDER)이 그대로 된다


# ---------- 전화번호 · 주민번호 · 카드 ----------

@pytest.mark.parametrize("raw", ["010-1234-5678", "01012345678", "010 1234 5678", "02-123-4567", "031-987-6543",
                                 "+82-10-1234-5678", "070-1234-5678"])
def test_phone_numbers(raw):
    assert Masker().mask_text(f"연락처 {raw} 입니다") == "연락처 [전화번호 1] 입니다"


@pytest.mark.parametrize("text", ["2026-10-20까지", "2026-11-12T18:00", "1,000,000원", "10:30 회의", "문서번호 2024-0001",
                                  "3.5억", "v2.3.10", "견적 12,345,678원", "PR #93", "20261020"])
def test_dates_amounts_ids_are_not_phones(text):
    assert Masker().mask_text(text) == text


def test_rrn_and_card():
    m = Masker()
    assert m.mask_text("주민번호 900101-1234567") == "주민번호 [주민번호 1]"
    assert m.mask_text("카드 1234-5678-9012-3456 결제") == "카드 [카드번호 1] 결제"


# ---------- 이름 ----------

def test_names_keep_surname_longest_first():
    m = Masker(["김민", "김민준", "이준호", "X"])  # 한 글자는 가리지 않는다
    out = m.mask_text("김민준 팀장님, 이준호님께서 김민 대리에게 X를 전달")
    assert out == "김◯◯ 팀장님, 이◯◯님께서 김◯◯2 대리에게 X를 전달"  # 성이 같은 둘째 사람은 번호
    assert m.mask_text("이 팀장님께서도") == "이 팀장님께서도"  # 성 + 직책 지목('이 팀장') 판별은 그대로


def test_same_surname_people_stay_apart_and_restore():
    """김◯◯ 하나로 합치면 ai가 두 사람을 섞고 되돌릴 때도 누구인지 모른다 → 둘째부터 번호."""
    m = Masker(["김민준", "김서연", "박지훈"])
    masked = m.mask_text("김민준님이 김서연님께, 박지훈님 참조. 다시 김민준님")
    assert masked == "김◯◯님이 김◯◯2님께, 박◯◯님 참조. 다시 김◯◯님"
    assert m.unmask_text("김◯◯2님에게 김◯◯님 자료 전달") == "김서연님에게 김민준님 자료 전달"
    assert m.mask_text("[전화번호 1]") == "[전화번호 1]"  # 대체어는 다시 가리지 않는다


def test_numbers_are_numbered_per_kind_and_restored():
    m = Masker()
    text = "010-1111-2222 / 010-3333-4444 / 900101-1234567 / 1234-5678-9012-3456 / 010-1111-2222"
    masked = m.mask_text(text)
    assert masked == "[전화번호 1] / [전화번호 2] / [주민번호 1] / [카드번호 1] / [전화번호 1]"
    assert m.unmask_text(masked) == text


def test_name_inside_a_longer_word_is_not_masked():
    assert Masker(["민준"]).mask_text("이민준 · 민준님") == "이민준 · 민◯◯님"


# ---------- 되돌리기 ----------

def test_unmask_round_trip_and_longer_token_first():
    m = Masker(["김민준"])
    addrs = [f"p{i}@a.example" for i in range(1, 13)]
    masked = m.mask_obj({"to": addrs, "body": "김민준 010-1111-2222"})
    assert masked["to"][0] == "user1@a.example" and masked["to"][11] == "user12@a.example"
    assert m.unmask_obj(masked) == {"to": addrs, "body": "김민준 010-1111-2222"}
    assert m.unmask_text("user12@a.example · user1@a.example") == "p12@a.example · p1@a.example"


def test_unmask_model_restores_task_text_and_evidence():
    m = Masker(["정태성"])
    body = m.mask_text("정태성 담당입니다. 견적서를 회신 부탁드립니다.")
    r = ClassifyResult.model_validate({
        "mail_id": "1", "category": "회신", "action_types": ["회신요청"],
        "tasks": [{"text": "정◯◯ 담당에게 회신", "evidence": body,
                                                     "due_at": "2026-11-12T18:00:00"}],
        "mentioned_me": True, "urgent": False, "is_follow_up": False, "priority": "P1", "source": "exaone",
        "rules_version": "conditions_v1"})
    back = m.unmask_model(r)
    assert back.tasks[0].text == "정태성 담당에게 회신" and back.tasks[0].evidence.startswith("정태성 담당입니다")
    assert back.tasks[0].due_at == datetime(2026, 11, 12, 18, 0) and back.mail_id == 1


def test_masked_count_has_no_values():
    m = Masker(["김민준"])
    m.mask_text("김민준 010-1111-2222 a.b@c.example")
    assert m.masked == 3


# ---------- 켜기 · 끄기 · 사용자별 ----------

@pytest.mark.parametrize(("raw", "on"), [("", True), ("1", True), ("0", False), ("off", False), ("FALSE", False)])
def test_switch(monkeypatch, raw, on):
    monkeypatch.setenv("PII_MASK", raw)
    assert enabled() is on


def test_masker_for_uses_my_name_and_contacts(db, monkeypatch):
    db.add(User(id=1, name="이준호"))
    db.add(User(id=2, name="박서연"))
    db.flush()
    db.add(Contact(user_id=1, email="a@x.example", name="정태성"))
    db.add(Contact(user_id=1, email="b@x.example", name=None))
    db.add(Contact(user_id=2, email="c@x.example", name="장민호"))  # 다른 사용자 연락처는 쓰지 않는다
    db.commit()
    assert masker_for(db, 1).mask_text("이준호 · 정태성 · 장민호") == "이◯◯ · 정◯◯ · 장민호"
    monkeypatch.setenv("PII_MASK", "0")
    assert masker_for(db, 1).mask_text("이준호 010-1111-2222") == "이준호 010-1111-2222"


def test_leftover_tokens_are_logged_without_values(caplog):
    """모델이 ◯를 ○로 바꾸거나 주소 도메인을 빼면 되돌리지 못한다 → 개수만 경고로 남긴다(#94 리뷰 1번)."""
    m = Masker(["김민준"])
    m.mask_text("김민준 a.b@c.example")
    assert Masker.leftover({"x": ["김○○에게 user1로 회신", "[전화번호 2]"]}) == 3
    assert Masker.leftover("김민준 담당, 3시") == 0
    with caplog.at_level("WARNING", logger="app.privacy"):
        m.unmask_model(ClassifyResult.model_validate({
            "mail_id": "1", "category": "회신", "action_types": ["회신요청"],
            "tasks": [{"text": "김○○ 담당에게 회신", "evidence": "김민준 담당입니다."}],
            "mentioned_me": True, "urgent": False, "is_follow_up": False, "priority": "P1", "source": "exaone",
            "rules_version": "conditions_v1"}))
    assert "되돌리지 못한 대체어 1개" in caplog.text and "김" not in caplog.text
