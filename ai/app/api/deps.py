from functools import lru_cache

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.llm.client import LLMClient, build_client, with_timeout


@lru_cache
def settings_dep() -> Settings:
    return get_settings()


@lru_cache
def llm_dep() -> LLMClient:
    return build_client(settings_dep())


def llm_background_dep(llm: LLMClient = Depends(llm_dep), settings: Settings = Depends(settings_dep)) -> LLMClient:
    """백그라운드 엔드포인트(분류 · 기억 추출 · 신호)용: 같은 클라이언트에 LLM_BACKGROUND_TIMEOUT_S만 씌운다(AI-28).
    대화형(명령 해석 · 다듬기 · 요약)은 llm_dep 그대로 — backend 130초 · 화면 140초 안에서 끝나야 한다."""
    return with_timeout(llm, settings.llm_background_timeout_s)
