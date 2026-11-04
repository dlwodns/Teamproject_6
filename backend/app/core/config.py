"""backend 설정. 환경 변수만 읽는다(.env는 실행 환경이 주입한다).

서비스 경로에는 외부 LLM 키 설정을 두지 않는다(D41).
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_mode: str = "dev"  # dev | prod. dev에서만 더미 적재 · 시간 이동 · 리마인더 강제 실행을 켠다
    database_url: str = "sqlite:///./ax.db"  # backend/ 에서 실행하면 backend/ax.db (.gitignore *.db)
    ai_service_url: str = "http://localhost:8001"
    mail_source: str = "dummy"  # dummy | outlook_graph | imap


def get_settings() -> Settings:
    env = os.environ
    return Settings(
        app_mode=env.get("APP_MODE", Settings.app_mode).strip().lower(),
        database_url=env.get("DATABASE_URL", Settings.database_url).strip(),
        ai_service_url=env.get("AI_SERVICE_URL", Settings.ai_service_url).rstrip("/"),
        mail_source=env.get("MAIL_SOURCE", Settings.mail_source).strip().lower(),
    )
