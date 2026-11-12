"""backend 설정. 환경 변수만 읽는다(.env는 실행 환경이 주입한다).

서비스 경로에는 외부 LLM 키 설정을 두지 않는다(D41).
"""
import os
from dataclasses import dataclass

from app.core.clock import parse_clock_start


@dataclass(frozen=True)
class Settings:
    app_mode: str = "dev"  # dev | prod. dev에서만 더미 적재 · 시간 이동 · 리마인더 강제 실행을 켠다
    database_url: str = "sqlite:///./ax.db"  # backend/ 에서 실행하면 backend/ax.db (.gitignore *.db)
    ai_service_url: str = "http://localhost:8001"
    mail_source: str = "dummy"  # dummy | outlook_graph
    clock_start: str = ""  # 시연 시작 시각(ISO 8601, 시간대 없으면 KST). 비면 실제 시각. app/core/clock.py


def get_settings() -> Settings:
    env = os.environ
    return Settings(
        app_mode=env.get("APP_MODE", Settings.app_mode).strip().lower(),
        database_url=env.get("DATABASE_URL", Settings.database_url).strip(),
        ai_service_url=env.get("AI_SERVICE_URL", Settings.ai_service_url).rstrip("/"),
        mail_source=env.get("MAIL_SOURCE", Settings.mail_source).strip().lower(),
        clock_start=env.get("CLOCK_START", Settings.clock_start).strip(),
    )


APP_MODES = ("dev", "prod")
# IMAP은 이번 단계 범위 밖이다(docs/30_backend/plan.md 2절). 커넥터가 생기면 꼭 있어야 하는 값과 함께 여기에 다시 넣는다
MAIL_SOURCES = ("dummy", "outlook_graph")
# 메일 원본별로 꼭 있어야 하는 값. 비밀값이라 Settings에 담지 않고 있는지만 본다(값은 메시지 · 로그에 넣지 않는다)
REQUIRED_BY_MAIL_SOURCE = {
    "outlook_graph": ("MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_REDIRECT_URI", "TOKEN_ENCRYPTION_KEY"),
}


def check_settings(s: Settings | None = None) -> list[str]:
    """시작할 때 설정을 검사한다(INF-4, infra/plan.md 3-4). 문제마다 한 줄, 없으면 빈 목록."""
    s = s or get_settings()
    env = os.environ
    errors = []
    if s.app_mode not in APP_MODES:
        errors.append(f"APP_MODE={s.app_mode!r}: {' | '.join(APP_MODES)} 중 하나여야 한다")
    if s.mail_source not in MAIL_SOURCES:
        errors.append(f"MAIL_SOURCE={s.mail_source!r}: {' | '.join(MAIL_SOURCES)} 중 하나여야 한다")
    # 지금은 SQLite만 쓴다. 배포 방식(INF-11)이 정해지면 이 검사와 기본값이 바뀔 수 있다
    if not s.database_url.startswith("sqlite"):
        errors.append("DATABASE_URL: SQLite 주소(sqlite:///...)여야 한다")
    if not s.ai_service_url.startswith(("http://", "https://")):
        errors.append("AI_SERVICE_URL: http:// 또는 https://로 시작해야 한다")
    for name in REQUIRED_BY_MAIL_SOURCE.get(s.mail_source, ()):
        if not env.get(name, "").strip():
            errors.append(f"{name}: MAIL_SOURCE={s.mail_source}이면 값이 있어야 한다(.env)")
    try:
        parse_clock_start(s.clock_start)
    except ValueError:
        errors.append(f"CLOCK_START={s.clock_start!r}: ISO 8601 시각이어야 한다(예: 2026-10-20T09:00, 비우면 실제 시각)")
    return errors


def ensure_settings() -> None:
    """설정이 틀리면 서비스를 띄우지 않는다. 잘못된 값으로 떠서 나중에 조용히 실패하는 것보다 낫다."""
    if errors := check_settings():
        raise RuntimeError("backend 설정 오류 — .env를 고친다(.env.example 참고):\n  - " + "\n  - ".join(errors))
