"""시연 데모 시드(app/dev/seed.py): 반복 적재 · 완료 상태 유지 · 실패 후 재시도 · 초기화 · 기대값 대조."""
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dev import seed
from app.models import Mail, Task

SOURCE = seed.DEFAULT_SOURCE
DATA = json.loads(SOURCE.read_text(encoding="utf-8"))


def _expected_module():
    # 기대값 스크립트는 시드 코드와 따로 원본 JSON만 읽는다
    path = Path(__file__).resolve().parents[1] / "scripts" / "demo_expected.py"
    spec = importlib.util.spec_from_file_location("demo_expected", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


expected_mod = _expected_module()
AS_OF_A = expected_mod.candidate_a(DATA)
AS_OF_B = datetime.fromisoformat(expected_mod.CANDIDATE_B)


@pytest.fixture
def engine(tmp_path):
    return seed.demo_engine(tmp_path / "demo_test.db")


def _counts(engine) -> tuple[int, int, int]:
    s = seed.summary(engine)
    return s["mails"], s["tasks"], s["contacts"]


@pytest.mark.parametrize("as_of", [AS_OF_A, AS_OF_B], ids=["A", "B"])
def test_db_matches_expected(engine, as_of):
    seed.load(engine, as_of)
    got = seed.summary(engine)
    want = expected_mod.expected(DATA, as_of)
    for key in ("mails", "tasks", "sender_pending_tasks", "sender_mail_ids", "M-0064_arrived"):
        assert got[key] == want[key], key


def test_second_load_adds_nothing(engine):
    first = seed.load(engine, AS_OF_B)
    before = _counts(engine)
    second = seed.load(engine, AS_OF_B)
    assert (second.added_mails, second.added_tasks, second.added_contacts) == (0, 0, 0)
    assert second.skipped_mails == first.added_mails
    assert _counts(engine) == before


def test_done_status_kept_on_reload(engine):
    seed.load(engine, AS_OF_A)
    with Session(engine) as s, s.begin():
        task = s.scalars(select(Task).join(Mail).where(Mail.source_id == "M-0026")).one()
        task.status, task.done_at = "done", datetime(2026, 10, 19, 17, 0)
        done_id = task.id
    seed.load(engine, AS_OF_A)
    seed.load(engine, AS_OF_B)  # 기준 시각을 늦춰도 이미 있는 업무는 그대로
    with Session(engine) as s:
        assert s.get(Task, done_id).status == "done"
    assert seed.summary(engine)["sender_pending_tasks"] == 2


def test_failure_mid_mail_then_retry(engine, monkeypatch):
    # 업무 2개인 메일의 두 번째 업무에서 실패 → 그 메일은 메일 · 업무 모두 없음 → 재시도로 채움
    multi, second = next((m["mail"]["id"], m["gold"]["tasks"][1]["action"])
                         for m in DATA["mails"] if len(m["gold"]["tasks"]) >= 2)
    real, calls = seed._task_row, {"n": 0}

    def flaky(mail_id, task, gold, type_=None):
        if task["action"] == second:
            calls["n"] += 1
            raise RuntimeError("저장 도중 실패")
        return real(mail_id, task, gold, type_)

    monkeypatch.setattr(seed, "_task_row", flaky)
    with pytest.raises(RuntimeError):
        seed.load(engine, AS_OF_B)
    assert calls["n"] == 1
    with Session(engine) as s:
        assert s.scalar(select(Mail.id).where(Mail.source_id == multi)) is None  # 반쯤 저장된 메일 없음

    monkeypatch.setattr(seed, "_task_row", real)
    seed.load(engine, AS_OF_B)
    want = expected_mod.expected(DATA, AS_OF_B)
    with Session(engine) as s:
        ids = s.scalars(select(Mail.source_id)).all()
        assert len(ids) == len(set(ids)) == want["mails"]
        assert len(s.scalars(select(Task.id)).all()) == want["tasks"]
        assert None not in s.scalars(select(Task.type)).all()  # 업무 유형이 모두 채워진다(캐치봇 리마인더 칸)


def test_reset_restores_fresh_state(engine):
    seed.load(engine, AS_OF_A)
    fresh = seed.summary(engine)
    with Session(engine) as s, s.begin():
        s.scalars(select(Task)).first().status = "done"
    seed.load(engine, AS_OF_B)
    seed.reset(engine)
    assert _counts(engine) == (0, 0, 0)
    seed.load(engine, AS_OF_A)
    assert seed.summary(engine) == fresh


def test_mail_level_fields_copied_to_each_task(engine):
    # D47: mentioned_me · priority는 메일 단위 → 업무마다 복사
    seed.load(engine, AS_OF_B)
    gold = {m["mail"]["id"]: m["gold"] for m in DATA["mails"]}
    with Session(engine) as s:
        for source_id, mentioned, priority in s.execute(
                select(Mail.source_id, Task.mentioned_me, Task.priority).join(Task, Task.mail_id == Mail.id)):
            assert (mentioned, priority) == (gold[source_id]["mentioned_me"], gold[source_id]["priority"])


def test_category_d39_grouping(engine):
    seed.load(engine, AS_OF_B)
    with Session(engine) as s:
        cat = dict(s.execute(select(Mail.source_id, Mail.category)).all())
    assert cat["M-0064"] == "검토"  # 검토승인요청
    assert cat["M-0010"] == "기타"  # 회신(내 요청에 대한 답)
    assert cat["M-0009"] == "요청"  # 공지 + 자료제출요청, 업무 있음 → 요청(D40)


def test_kst_naive_times(engine):
    seed.load(engine, AS_OF_B)
    with Session(engine) as s:
        assert s.scalar(select(Mail.sent_at).where(Mail.source_id == "M-0026")) == datetime(2026, 10, 19, 10, 36)
    assert seed.to_kst_naive("2026-10-19T01:36:00+00:00") == datetime(2026, 10, 19, 10, 36)


@pytest.mark.parametrize("name", ["ax.db", "prod.db", "demo.sqlite"])
def test_only_demo_db_allowed(tmp_path, name):
    with pytest.raises(seed.SeedError):
        seed.demo_engine(tmp_path / name)
    assert not (tmp_path / name).exists()


def test_cli_reset_needs_yes(tmp_path, capsys):
    db = tmp_path / "demo_cli.db"
    assert seed.main(["load", "--db", str(db), "--as-of", "2026-10-19T09:00"]) == 0
    assert seed.main(["reset", "--db", str(db)]) == 2
    assert seed.main(["reset", "--db", str(db), "--yes"]) == 0
    assert seed.main(["reset", "--db", str(tmp_path / "ax.db"), "--yes"]) == 2


def test_this_week_shift_keeps_weekday_and_moves_text_dates(tmp_path):
    """11-18: 더미 메일함(10/19 월)을 이번 주로 7일 단위로 옮긴다. 본문 날짜 글자 · 기한 · 받은 시각이 함께 옮겨진다."""
    from datetime import date

    assert seed.week_shift(date(2026, 11, 18)) == 28  # 수 → 그 주 월 11/16
    assert seed.week_shift(date(2026, 11, 16)) == 21  # 월 → 지난주 월 11/9(메일이 아직 다 오지 않았다)
    assert seed.week_shift(date(2026, 11, 18)) % 7 == 0
    assert seed.shift_text("10/23(금)까지, 10월 30일, 2026-10-19T08:10, 11/2", 28) == "11/20(금)까지, 11월 27일, 2026-11-16T08:10, 11/30"
    # 끝 날만 쓴 범위(10/26~27)도 끝 날을 옮긴다. 달이 바뀌면 끝에도 달을 쓴다
    assert seed.shift_text("연차(10/26~27) · 10/26~10/27 · 10/30~31", 28) == "연차(11/23~24) · 11/23~11/24 · 11/27~28"
    assert seed.shift_text("10/30~31", 1) == "10/31~11/1" and seed.shift_text("10/29~11/2", 0) == "10/29~11/2"
    assert seed.shift_text("1팀-2팀 · 4/4분기 · 3.10/2", 28) == "1팀-2팀 · 4/4분기 · 3.10/2"  # 10 · 11월이 아닌 것 · 소수는 두지 않는다
    out = seed.shifted_source(seed.DEFAULT_SOURCE, tmp_path / "x.mails.json", 28)
    import json
    data = json.loads(out.read_text(encoding="utf-8"))
    assert all(m["mail"]["received_at"] >= "2026-11-13" for m in data["mails"])
    due = [t["due_at"] for m in data["mails"] for t in m["gold"]["tasks"] if t.get("due_at")]
    assert due and min(due) >= "2026-11-13"
    assert {date.fromisoformat(m["mail"]["received_at"][:10]) for m in data["mails"]} <= {date(2026, 11, 13), date(2026, 11, 16)}  # 금 · 월 그대로


def test_cli_this_week_refuses_filled_db_and_as_of(tmp_path, capsys):
    """리뷰: 다른 주로 넣은 DB에 다시 돌리면 날짜가 섞인다 → 비운 뒤에만. --as-of와 함께 쓰지 않는다."""
    db = tmp_path / "demo_w.db"
    assert seed.main(["load", "--db", str(db), "--this-week"]) == 0
    assert seed.main(["load", "--db", str(db), "--this-week"]) == 2
    assert seed.main(["load", "--db", str(db), "--this-week", "--as-of", "2026-10-19T16:16"]) == 2
    assert "reset" in capsys.readouterr().err
