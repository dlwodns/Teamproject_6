"""ai 서비스 설정. 환경 변수만 읽는다(.env는 실행 환경이 주입한다).

서비스 경로에는 외부 LLM 키 설정을 두지 않는다(D41).
"""
import os
from dataclasses import dataclass

DEFAULT_MODEL = "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M"  # D44, eval/README.md 1절


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://localhost:11434"
    model: str = DEFAULT_MODEL
    llm_timeout_s: float = 120.0  # CPU에서 메일 1통 약 25초, 첫 호출 로딩 10초
    router_threshold: float = 0.8  # 규칙 확신도가 이 값 미만이면 엑사원으로 보낸다. 기준값은 측정 후 결정(구조도 13절)
    llm_enabled: bool = True  # False면 규칙 결과만 낸다(모델 없는 개발 환경 · 장애 시)


def get_settings() -> Settings:
    env = os.environ
    return Settings(
        ollama_base_url=env.get("OLLAMA_BASE_URL", Settings.ollama_base_url).rstrip("/"),
        model=env.get("EXAONE_MODEL", DEFAULT_MODEL).split("#")[0].strip() or DEFAULT_MODEL,
        llm_timeout_s=float(env.get("LLM_TIMEOUT_S", Settings.llm_timeout_s)),
        router_threshold=float(env.get("ROUTER_THRESHOLD", Settings.router_threshold)),
        llm_enabled=env.get("LLM_ENABLED", "true").lower() not in ("0", "false", "no"),
    )
