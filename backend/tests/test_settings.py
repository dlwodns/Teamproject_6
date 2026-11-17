"""설정 화면 칸 (api/settings.py): 근무 · 부재 · 본문 읽기 · 답장 템플릿 · 연락처 목록."""
from sqlalchemy import create_engine, inspect, text

from app.models import Contact
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
    for bad in ({"work_start": "19:00"}, {"work_days": "0-9"}, {"work_days": "월-금"}, {"read_body": "no"},
                {"quiet_start": None}):  # 시작 ≥ 끝 · 요일 형식 · 문자열 불린 · 조용한 시간 반쪽
        assert client.patch("/api/settings", headers=H, json=bad).status_code == 422, bad
    assert client.get("/api/settings", headers=H).json()["work_start"] == "08:00"  # 거절한 값은 저장되지 않는다


def test_templates_default_then_replace(client, db):
    _base(db)
    db.commit()
    t = client.get("/api/settings", headers=H).json()["templates"]
    assert [x["key"] for x in t] == ["basic", "material", "schedule", "ack"]
    assert t[0]["pattern"] == "{수신자명}님, 안녕하세요. {발신자명}입니다.\n\n{내용}\n\n감사합니다.\n{발신자명} 드림"
    mine = [{"key": "short", "name": "짧게", "greeting": "", "closing": "감사합니다.", "signature": "", "pattern": "무시"}]
    r = client.patch("/api/settings", headers=H, json={"templates": mine}).json()
    assert r["templates"] == [{"key": "short", "name": "짧게", "greeting": "", "closing": "감사합니다.", "signature": "",
                               "pattern": "{내용}\n\n감사합니다."}]
    for bad in ([], [mine[0], mine[0]], [{**mine[0], "name": "  "}], [{**mine[0], "key": "한글"}]):
        assert client.patch("/api/settings", headers=H, json={"templates": bad}).status_code == 422
    assert [x["key"] for x in client.get("/api/settings", headers=H).json()["templates"]] == ["short"]


def test_contacts_list_superior_first(client, db):
    _base(db)
    db.add_all([Contact(user_id=1, email="a@cne.com", name="가나다"),
                Contact(user_id=1, email="b@cne.com", name="한상우", position="사업단장", is_superior=True)])
    db.commit()
    rows = client.get("/api/contacts", headers=H).json()
    assert [c["email"] for c in rows] == ["b@cne.com", "a@cne.com"] and rows[0]["is_superior"] is True


def test_old_templates_table_gets_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE templates (id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(10), name VARCHAR(100),"
                       " subject VARCHAR(255), body TEXT)"))
        assert set(schema.upgrade(c)) >= {"templates.key 더함", "templates.signature 더함"}
        assert {"key", "greeting", "closing", "signature"} <= {x["name"] for x in inspect(c).get_columns("templates")}
