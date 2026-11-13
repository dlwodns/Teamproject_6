"""ai 서비스 설정. 환경 변수만 읽는다(.env는 실행 환경이 주입한다).

서비스 경로에는 외부 LLM 키 설정을 두지 않는다(D41).
"""
import os
from dataclasses import dataclass

DEFAULT_MODEL = "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M"  # D44, eval/README.md 1절


@dataclass(frozen=True)
class Settings:
    llm_backend: str = "ollama"  # ollama | llamacpp (llama.cpp llama-server, OpenAI 형식 /v1). 둘 다 로컬 실행기다(D41)
    ollama_base_url: str = "http://localhost:11434"
    ollama_uds: str = ""  # 비우지 않으면 이 Unix 소켓으로 ollama를 부른다(PC 엑사원 역방향 터널, scripts/exaone-pc.env)
    llamacpp_base_url: str = "http://127.0.0.1:30411"
    model: str = DEFAULT_MODEL
    model_digest: str = ""  # 고정값. 비우지 않으면 ollama의 모델 digest가 다를 때 호출하지 않는다
    ollama_version: str = ""  # 고정값. 비우지 않으면 ollama 버전이 다를 때 호출하지 않는다
    llm_timeout_s: float = 120.0  # PC CPU에서 메일 1통 약 37초, 첫 호출(모델 로딩) 117초(11/3 실측)
    ollama_keep_alive: str = "30m"  # 모델을 메모리에 두는 시간. ollama 기본 5분이면 쉬고 난 첫 메일마다 로딩이 다시 걸린다
    llm_enabled: bool = True  # False면 모델을 부르지 않는다(모델 없는 개발 환경). 분류는 '분류 실패'로 남아 다시 시도 대상이 된다(AI-D15)



def get_settings() -> Settings:
    env = os.environ
    return Settings(
        llm_backend=env.get("LLM_BACKEND", Settings.llm_backend).strip().lower(),
        ollama_base_url=env.get("OLLAMA_BASE_URL", Settings.ollama_base_url).rstrip("/"),
        ollama_uds=env.get("OLLAMA_UDS", "").strip(),
        llamacpp_base_url=env.get("LLAMACPP_BASE_URL", Settings.llamacpp_base_url).rstrip("/"),
        model=env.get("EXAONE_MODEL", DEFAULT_MODEL).split("#")[0].strip() or DEFAULT_MODEL,
        model_digest=env.get("EXAONE_MODEL_DIGEST", "").strip(),
        ollama_version=env.get("OLLAMA_VERSION", "").strip(),
        llm_timeout_s=float(env.get("LLM_TIMEOUT_S", Settings.llm_timeout_s)),
        ollama_keep_alive=env.get("OLLAMA_KEEP_ALIVE", Settings.ollama_keep_alive).strip(),
        llm_enabled=env.get("LLM_ENABLED", "true").lower() not in ("0", "false", "no"),
    )


LLM_BACKENDS = ("ollama", "llamacpp")


def check_settings() -> list[str]:
    """시작할 때 설정을 검사한다(INF-4, infra/plan.md 3-4). 문제마다 한 줄, 없으면 빈 목록."""
    env = os.environ
    errors = []
    for name in ("LLM_TIMEOUT_S",):
        try:
            float(env.get(name, "0"))
        except ValueError:
            errors.append(f"{name}={env[name]!r}: 숫자여야 한다")
    if errors:
        return errors
    s = get_settings()
    if s.llm_backend not in LLM_BACKENDS:
        errors.append(f"LLM_BACKEND={s.llm_backend!r}: {' | '.join(LLM_BACKENDS)} 중 하나여야 한다(로컬 실행기만, D41)")
    if s.llm_timeout_s <= 0:
        errors.append("LLM_TIMEOUT_S: 0보다 커야 한다")
    for name, url in (("OLLAMA_BASE_URL", s.ollama_base_url), ("LLAMACPP_BASE_URL", s.llamacpp_base_url)):
        if not url.startswith(("http://", "https://")):
            errors.append(f"{name}: http:// 또는 https://로 시작해야 한다")
    return errors


def ensure_settings() -> None:
    """설정이 틀리면 서비스를 띄우지 않는다. 엑사원 연결 실패와 달리 설정 오류는 고치기 전까지 계속 틀린다."""
    if errors := check_settings():
        raise RuntimeError("ai 설정 오류 — .env를 고친다(.env.example 참고):\n  - " + "\n  - ".join(errors))
