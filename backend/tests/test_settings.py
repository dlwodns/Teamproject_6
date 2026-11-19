"""설정 화면 칸 (api/settings.py): 근무 · 부재 · 본문 읽기 · 답장 템플릿."""
from sqlalchemy import create_engine, inspect, text

from app.reminders import schema
from tests.test_reminders import _base

H = {"X-User-Id": "1"}


def test_policy_fields_round_trip_and_validation(client, db):
    _base(db)
    db.commit()
    s = client.get("/api/settings", headers=H).json()
    assert (s["read_body"], s["work_start"], s["work_end"], s["work_days"], s["away_until"]) == (True, "09:00", "18:00", "1-5", None)
    r = client.patch("/api/settings", headers=H, json={"read_body": False, "work_start": "08:00", "work_days": "1-4",
                                                       "away_until": "2026-11-12T18:00:00+09:00",
                                                       "quiet_start": "22:00", "quiet_end": "07:00"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["read_body"], s["work_start"], s["work_days"], s["quiet_start"]) == (False, "08:00", "1-4", "22:00")
    assert s["away_until"] == "2026-11-12T18:00:00+09:00"
    assert client.patch("/api/settings", headers=H, json={"away_until": None}).json()["away_until"] is None  # 부재 해제
    assert client.patch("/api/settings", headers=H, json={"read_body": None}).json()["read_body"] is False  # null은 무시
    for bad in ({"work_start": "19:00"}, {"work_days": "0-9"}, {"work_days": "월-금"}, {"work_days": "7-6"}, {"read_body": "no"},
                {"quiet_start": None}):  # 시작 ≥ 끝 · 요일 형식 · 문자열 불린 · 조용한 시간 반쪽
        assert client.patch("/api/settings", headers=H, json=bad).status_code == 422, bad
    assert client.get("/api/settings", headers=H).json()["work_start"] == "08:00"  # 거절한 값은 저장되지 않는다


def test_templates_default_then_replace(client, db):
    _base(db)
    db.commit()
    t = client.get("/api/settings", headers=H).json()["templates"]
    assert [x["key"] for x in t] == ["basic", "material", "schedule", "ack"]
    assert t[0] == {"key": "basic", "name": "기본 회신",
                    "pattern": "{수신자명}님, 안녕하세요. {발신자명}입니다.\n\n{내용}\n\n감사합니다.\n{발신자명} 드림"}
    mine = [{"key": "short", "name": " 짧게 ", "pattern": "확인했습니다. 감사합니다."}]  # 자유 글(내용 자리 없음)
    r = client.patch("/api/settings", headers=H, json={"templates": mine}).json()
    assert r["templates"] == [{"key": "short", "name": "짧게", "pattern": "확인했습니다. 감사합니다."}]
    for bad in ([], [mine[0], mine[0]], [{**mine[0], "name": "  "}], [{**mine[0], "key": "한글"}],
                [{**mine[0], "greeting": "x"}], [{**mine[0], "pattern": "x" * 4001}]):
        assert client.patch("/api/settings", headers=H, json={"templates": bad}).status_code == 422
    assert [x["key"] for x in client.get("/api/settings", headers=H).json()["templates"]] == ["short"]


def test_old_templates_table_gets_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE templates (id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(10), name VARCHAR(100),"
                       " subject VARCHAR(255), body TEXT)"))
        assert "templates.key 더함" in schema.upgrade(c)
        assert "key" in {x["name"] for x in inspect(c).get_columns("templates")}


def test_old_half_quiet_row_does_not_block_other_patches(client, db):
    """리뷰: 예전에 반쪽만 저장된 조용한 시간이 있어도 상관없는 칸은 저장된다. 칸을 나누기 전 템플릿은 본문이 틀이다."""
    from app.models import Template, UserSettings
    _base(db, quiet_start="22:00")
    db.add(Template(user_id=1, kind="reply", name="옛 틀", body="확인했습니다."))
    db.commit()
    assert client.patch("/api/settings", headers=H, json={"reduce_motion": True}).status_code == 200
    assert db.get(UserSettings, 1).quiet_end is None
    assert client.get("/api/settings", headers=H).json()["templates"][0]["pattern"] == "확인했습니다."
