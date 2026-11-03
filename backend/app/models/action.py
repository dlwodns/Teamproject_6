"""행동 기록 · 미리보기 (구조도 v3.1 5 · 6 · 9절, docs/30_backend/detail.md 4절).

action_log는 UI · 에이전트 · MCP가 같이 쓰고, 되돌리기는 before_json으로 한다.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base

ACTION_SOURCES = ("ui", "agent_rule", "agent_model", "mcp")


class ActionLog(Base):
    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50))  # 레지스트리 행동 id (T03 등) 또는 UI 동작
    params_json: Mapped[dict | None] = mapped_column(JSON)
    affected_ids: Mapped[list] = mapped_column(JSON, default=list)  # 바뀐 task id
    before_json: Mapped[dict | None] = mapped_column(JSON)  # 되돌리기용 이전 상태
    source: Mapped[str] = mapped_column(String(15))
    preview_id: Mapped[str | None] = mapped_column(String(36))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    input_mode: Mapped[str | None] = mapped_column(String(10))  # text | voice
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint(f"source IN ({', '.join(repr(s) for s in ACTION_SOURCES)})", name="ck_action_log_source"),
    )


class ActionPreview(Base):
    """확인이 필요한 행동의 미리보기. 한 번만 실행하고(used_at) 만료 시간이 있다."""

    __tablename__ = "action_previews"

    preview_id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50))
    target_ids: Mapped[list] = mapped_column(JSON, default=list)
    params_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
