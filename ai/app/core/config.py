"""ai 서비스 설정. 환경 변수만 읽는다(.env는 실행 환경이 주입한다).

서비스 경로에서 부르는 외부 모델은 엑사원 API 하나뿐이다(D53). 다른 외부 LLM 키 설정은 두지 않는다.
"""
import os
from dataclasses import dataclass

DEFAULT_MODEL = "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M"  # 로컬 옵션 모델(D55), eval/README.md 1절
DEFAULT_API_MODEL = "k-exaone_v2.5"  # 엑사원 API 모델 이름(D51, docs.exaone.ai K-EXAONE 2.5)
REASONING_EFFORTS = ("", "low", "high", "max")  # 빈 값이면 보내지 않는다 = API 기본 max(docs.exaone.ai). 11-11 측정 32/40이 이 조건


@dataclass(frozen=True)
class Settings:
    llm_backend: str = "exaone_api"  # exaone_api(기본, D52) | ollama | llamacpp. 뒤의 둘은 로컬 실행기다
    exaone_api_base_url: str = "https://api.exaone.ai/v1"
    exaone_api_key: str = ""  # .env에만 둔다(D53). 비어 있으면 서비스는 뜨고 모델 호출만 실패한다 → 규칙 결과
    exaone_api_model: str = DEFAULT_API_MODEL  # EXAONE_MODEL(로컬 모델 이름)과 따로 둔다. 같이 쓰면 바꿔 끼울 때 이름이 섞인다
    exaone_reasoning_effort: str = ""  # low | high | max. 비우면 API 기본(max)
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
        llm_backend=env.get("LLM_BACKEND", Settings.llm_backend).split("#")[0].strip().lower() or Settings.llm_backend,
        exaone_api_base_url=env.get("EXAONE_API_BASE_URL", Settings.exaone_api_base_url).strip().rstrip("/"),
        exaone_api_key=env.get("EXAONE_API_KEY", "").strip(),
        exaone_api_model=env.get("EXAONE_API_MODEL", DEFAULT_API_MODEL).split("#")[0].strip() or DEFAULT_API_MODEL,
        exaone_reasoning_effort=env.get("EXAONE_REASONING_EFFORT", "").split("#")[0].strip().lower(),
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


LLM_BACKENDS = ("exaone_api", "ollama", "llamacpp")


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
        errors.append(f"LLM_BACKEND={s.llm_backend!r}: {' | '.join(LLM_BACKENDS)} 중 하나여야 한다(D52)")
    if s.llm_timeout_s <= 0:
        errors.append("LLM_TIMEOUT_S: 0보다 커야 한다")
    if s.exaone_reasoning_effort not in REASONING_EFFORTS:
        errors.append(f"EXAONE_REASONING_EFFORT={s.exaone_reasoning_effort!r}: low | high | max 중 하나이거나 비워 둔다")
    for name, url in (("OLLAMA_BASE_URL", s.ollama_base_url), ("LLAMACPP_BASE_URL", s.llamacpp_base_url),
                      ("EXAONE_API_BASE_URL", s.exaone_api_base_url)):
        if not url.startswith(("http://", "https://")):
            errors.append(f"{name}: http:// 또는 https://로 시작해야 한다")
    return errors


def ensure_settings() -> None:
    """설정이 틀리면 서비스를 띄우지 않는다. 엑사원 연결 실패와 달리 설정 오류는 고치기 전까지 계속 틀린다."""
    if errors := check_settings():
        raise RuntimeError("ai 설정 오류 — .env를 고친다(.env.example 참고):\n  - " + "\n  - ".join(errors))
