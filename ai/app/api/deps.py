from functools import lru_cache

from app.core.config import Settings, get_settings
from app.llm.client import LLMClient, build_client


@lru_cache
def settings_dep() -> Settings:
    return get_settings()


@lru_cache
def llm_dep() -> LLMClient:
    return build_client(settings_dep())
