"""메일 성격(kind) 표 무결성 · 대표 사례 (유형 체계 kinds-v1). 사례 메일은 데이터셋 문구가 아니라 여기서 새로 쓴 것이다."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from app.pipeline.kinds import ACTION_TYPES, BY_ID, KINDS, LANES, TASK_TYPES, all_signal_names, classify_kind, kind_types
from app.pipeline.signals import SIGNALS
from app.schemas.classify import ClassifyRequest, OwnerProfile

DUMMY = Path(__file__).resolve().parents[2] / "data/dummy"
OWNER = OwnerProfile(email="junho.lee@lgcns.example", name="이준호", position="팀장", team="클라우드전환1팀",
                     member_of=["all@lgcns.example"])
SIG = "\n\n감사합니다.\n\n*****\n홍길동 책임 / Gildong Hong\n클라우드사업부 / 품질관리팀\n*****"


def mail(subject, body, frm="gildong.hong@lgcns.example", to=None, cc=(), att=()):
    to = ["junho.lee@lgcns.example"] if to is None else to
    return ClassifyRequest(**{"from": frm}, mail_id="T-1", to=to, cc=list(cc), subject=subject, body=body, attachments=list(att),
                           received_at=datetime(2026, 11, 2, 9, 0), owner=OWNER)


def test_table_integrity():
    ids = [k.id for k in KINDS]
    assert ids == [f"K{i:02d}" for i in range(1, len(KINDS) + 1)]
    for k in KINDS:
        assert k.parent in ACTION_TYPES and k.lane in LANES and k.need and k.slots
        # 요청 유형이 부모면 할 일 칸이다. 공지 속 지목(K11)만 부모가 공지인 할 일 칸
        assert (k.parent in TASK_TYPES) == (k.lane == "할 일" and k.id != "K11")
    assert all_signal_names() <= set(SIGNALS)


def test_gold_labels_match_table_and_parent_type():
    gold = json.loads((DUMMY / "kinds_gold.json").read_text(encoding="utf-8"))
    sets = {"dev": "dummy_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json"}
    assert set(gold["labels"]) == set(sets)  # 테스트셋(test · test3)에는 라벨을 두지 않는다
    for s, f in sets.items():
        mails = json.loads((DUMMY / f).read_text(encoding="utf-8"))["mails"]
        labels, notes = gold["labels"][s], gold["notes"].get(s, {})
        assert set(labels) == {o["mail"]["id"] for o in mails}
        for o in mails:
            k = BY_ID[labels[o["mail"]["id"]]]
            if o["mail"]["id"] not in notes:  # 부모 유형이 기존 정답 주 유형과 다르면 notes에 이유가 있어야 한다
                assert k.parent == o["gold"]["action_types"][0], (s, o["mail"]["id"], k.id)


@pytest.mark.parametrize("req, want", [
    (mail("[클라우드 소식지] 12월호", "이번 달 소식지를 보내드립니다.\n- 서버리스 도입 사례\n수신을 원치 않으시면 수신거부를 눌러주세요.",
          frm="newsletter@cloudmag.example"), "K19"),
    (mail("RE: [요청] 테스트 계정 발급", "안녕하세요 IT운영팀 홍길동 책임입니다.\n\n요청하신 테스트 계정 발급을 마쳤습니다.\n초기 비밀번호는 문자로 보냈습니다." + SIG), "K12"),
    (mail("RE: [요청] 장비 대여 문의", "안녕하세요 홍길동 책임입니다.\n\n문의하신 장비는 다음 주까지 대여 가능합니다." + SIG), "K13"),
    (mail("RE: 회의 자료", "안녕하세요 홍길동 책임입니다.\n\n보내주신 회의 자료 잘 받았습니다. 따로 회신은 안 주셔도 됩니다." + SIG), "K14"),
    (mail("[공유] 고객 미팅 결과", "안녕하세요 홍길동 책임입니다.\n\n김민수 차장님, 어제 고객 미팅 결과 공유드립니다." + SIG,
          to=["minsu.kim@lgcns.example"], cc=["junho.lee@lgcns.example"]), "K15"),
    (mail("[회의] 분기 점검 회의 (11/10 15:00)", "안녕하세요 홍길동 책임입니다.\n\n분기 점검 회의를 엽니다.\n일시: 11/10(화) 15:00~16:00\n장소: 7층 회의실" + SIG), "K09"),
    (mail("[회의] 분기 점검 회의 시간 변경", "안녕하세요 홍길동 책임입니다.\n\n11/10 분기 점검 회의를 15:00에서 17:00로 변경합니다." + SIG), "K10"),
    (mail("[알림] 운영계 CPU 사용률 임계치 초과", "[자동발송] 운영계 서버 CPU 사용률이 90%를 초과했습니다.\n이 메일은 발신 전용입니다.",
          frm="alert@lgcns.example", to=["all@lgcns.example"]), "K21"),
    (mail("[품질] 상반기 점검 결과표 제출 안내", "안녕하세요 품질관리팀 홍길동 책임입니다.\n\n상반기 품질 점검을 실시합니다.\n"
          "아래 팀은 점검 결과표를 11/9까지 제출 바랍니다.\n- 클라우드전환1팀\n- 데이터플랫폼팀" + SIG, to=["all@lgcns.example"]), "K11"),
    (mail("[요청] 운영 매뉴얼 오탈자 수정", "안녕하세요 홍길동 책임입니다.\n\n팀장님, 보내주신 운영 매뉴얼에 오탈자가 있습니다.\n수정해서 다시 보내주실 수 있을까요?" + SIG), "K02"),
    (mail("[결재 요청] 출장비 정산", "안녕하세요 홍길동 책임입니다.\n\n팀장님, 출장비 정산서를 전자결재에 올렸습니다. 금주 중 결재 부탁드립니다." + SIG), "K04"),
])
def test_representative(req, want):
    assert classify_kind(req).kind.id == want


def test_kind_types():
    req = mail("[품질] 상반기 점검 결과표 제출 안내", "안녕하세요 품질관리팀 홍길동 책임입니다.\n\n상반기 품질 점검을 실시합니다.\n"
               "아래 팀은 점검 결과표를 11/9까지 제출 바랍니다.\n- 클라우드전환1팀" + SIG, to=["all@lgcns.example"])
    res = classify_kind(req)
    assert kind_types(res, ["공지", "자료제출요청"]) == ["공지", "자료제출요청"]
    promo = classify_kind(mail("[초청] 클라우드 포럼", "클라우드 포럼에 초청합니다. 사전 등록해 주세요.", frm="info@forum.example"))
    assert promo.kind.id == "K19" and kind_types(promo, ["회신요청"]) == ["기타"]
    # 규칙이 '등록해 주세요'를 할 일로 잡으면 충돌 → 엑사원행(할 일을 kind가 직접 지우지 않는다, D15)
    assert promo.needs_model and any("규칙 할 일 있음" in w for w in promo.why)
