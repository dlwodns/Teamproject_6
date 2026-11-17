"""예전 SQLite 파일을 BE-12 표 형태로 맞춘다. `Base.metadata.create_all()` 직후 자동으로 돈다(after_create 이벤트).

create_all은 없는 표만 만들고 있는 표의 칸 · 제약은 고치지 않는다(BE-D14). 그래서 BE-12가 바꾼 표 셋을 여기서 맞춘다.
- reminders · notifications: 칸 · 제약(task_id 비어도 됨, digest 종류)이 바뀌어 다시 만든다. main까지 이 두 표에 쓰는 코드가
  없었으므로 보통 비어 있다. **비어 있을 때만** 지우고 다시 만들고, 행이 있으면 멈추고 DB를 새로 만들라고 알린다(데이터를 버리지 않는다).
- templates: 답장 템플릿 이름표 칸(key)을 더한다(설정 화면).
- settings: 새 칸(work_start · work_end · work_days · away_until · reminder_mute · evening_time)을 ALTER TABLE ADD COLUMN으로 더한다.
  기존 행은 기본값을 받는다.
새 표(commitments · reminder_signals · reminder_feedback)는 create_all이 만든다. 이 밖의 표 변경은 하지 않는다.
"""
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Connection

from app.core.db import Base

SETTINGS_COLUMNS = {  # 칸 → ADD COLUMN 정의(기존 행이 받을 기본값 포함). 모델 app/models/user.py UserSettings와 같다
    "work_start": "VARCHAR(5) NOT NULL DEFAULT '09:00'",
    "work_end": "VARCHAR(5) NOT NULL DEFAULT '18:00'",
    "work_days": "VARCHAR(20) NOT NULL DEFAULT '1-5'",
    "away_until": "DATETIME",
    "reminder_mute": "JSON",
    "evening_time": "VARCHAR(5) NOT NULL DEFAULT '17:30'",
}


TEMPLATE_COLUMNS = {"key": "VARCHAR(40)"}  # 답장 템플릿 이름표(설정 화면)


class SchemaError(RuntimeError):
    pass


def _columns(conn: Connection, table: str) -> dict[str, dict]:
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _sql(conn: Connection, table: str) -> str:
    return conn.execute(text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :n"), {"n": table}).scalar() or ""


def _old_reminders(conn: Connection) -> bool:
    cols = _columns(conn, "reminders")
    return "user_id" not in cols or "subject_kind" not in cols or not cols["task_id"]["nullable"]


def _old_notifications(conn: Connection) -> bool:
    cols = _columns(conn, "notifications")
    return "reminder_keys" not in cols or "'digest'" not in _sql(conn, "notifications")


def upgrade(conn: Connection) -> list[str]:
    """맞춘 것을 한 줄씩 돌려준다. 이미 맞으면 빈 목록."""
    done: list[str] = []
    names = set(inspect(conn).get_table_names())
    old = [t for t, check in (("notifications", _old_notifications), ("reminders", _old_reminders))
           if t in names and check(conn)]
    for table in old:
        if conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar():
            raise SchemaError(f"{table} 표가 예전 형태인데 행이 있어 자동으로 바꾸지 않는다. "
                              "로컬 DB(ax.db 등)를 지우고 다시 만든다(backend/README.md 실행 절)")
    if old:
        # 외래 키 순서: 예전 notifications가 reminders를 가리키므로 먼저 지우고, 새 reminders가 notifications를 가리키므로 나중에 만든다
        for table in ("notifications", "reminders"):
            if table in old:
                conn.execute(text(f'DROP TABLE "{table}"'))
        for table in ("notifications", "reminders"):
            if table in old:
                Base.metadata.tables[table].create(conn)
                done.append(f"{table} 다시 만듦")
    if "settings" in names:
        have = _columns(conn, "settings")
        for name, ddl in SETTINGS_COLUMNS.items():
            if name not in have:
                conn.execute(text(f'ALTER TABLE settings ADD COLUMN "{name}" {ddl}'))
                done.append(f"settings.{name} 더함")
    if "templates" in names:
        have = _columns(conn, "templates")
        for name, ddl in TEMPLATE_COLUMNS.items():
            if name not in have:
                conn.execute(text(f'ALTER TABLE templates ADD COLUMN "{name}" {ddl}'))
                done.append(f"templates.{name} 더함")
    return done


@event.listens_for(Base.metadata, "after_create")
def _after_create(target, connection, **kw) -> None:
    upgrade(connection)
