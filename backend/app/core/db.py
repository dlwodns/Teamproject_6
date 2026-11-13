"""SQLite 연결. 테이블은 app/models, 생성은 시작할 때 create_all(마이그레이션 도구는 아직 없다).

create_all은 있는 테이블에 새 칸을 넣지 않는다. 이미 쓰던 DB가 새 코드에서 'no such column'으로 멈추지 않게,
비어 있어도 되는 새 칸만 ALTER TABLE ADD COLUMN으로 더한다(_add_missing_columns). 칸 이름 바꾸기 · 지우기 · 제약 변경은 하지 않는다.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs: dict = {"connect_args": {"check_same_thread": False}}  # FastAPI 스레드풀 · 스케줄러가 같이 쓴다
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool  # 메모리 DB는 연결 하나를 같이 써야 테이블이 보인다(테스트용)
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")  # SQLite는 기본으로 외래 키 검사를 끈다
        cur.close()

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    import app.models  # noqa: F401  테이블 정의를 Base.metadata에 올린다

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _literal(v: object) -> str | None:
    """옛 행을 채울 기본값의 SQL 글자. 숫자 · 참거짓 · 글자만 — 그 밖(함수 기본값 등)은 None."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int | float):
        return str(v)
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return None


def _add_missing_columns(eng: Engine) -> None:
    """모델에는 있고 DB 테이블에는 없는 칸을 더한다. NULL을 허용하는 칸, 또는 고정 기본값이 있는 칸만 —
    둘 다 아니면 옛 행을 채울 값이 없어 건너뛴다(그 표는 DB를 새로 만들어야 한다)."""
    insp = inspect(eng)
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have or col.primary_key:
                    continue
                ddl = f'"{col.name}" {col.type.compile(dialect=eng.dialect)}'
                if not col.nullable:
                    default = _literal(col.default.arg) if col.default is not None and col.default.is_scalar else None
                    if default is None:
                        continue
                    ddl += f" NOT NULL DEFAULT {default}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
