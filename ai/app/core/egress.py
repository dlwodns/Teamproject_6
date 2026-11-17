"""외부 송신 허용 목록 · 송신 기록 (구조도 10절 · D41 → D53 · 기획 detail 시연 ⑧ "로컬 모드면 외부 LLM 호출 0건").

ai 서비스가 밖으로 보내는 HTTP(모델 호출)는 모두 여기 hooks()를 건 httpx 클라이언트로 나간다.
- 로컬(localhost · 127.x · ::1 · 사설망 10 · 172.16~31 · 192.168 · *.internal · 점 없는 컨테이너 이름)은 그대로 보낸다.
- 외부는 허용 목록에 있을 때만 보낸다. 허용 목록은 설정에서 나온다: LLM_BACKEND=exaone_api면 엑사원 API 호스트 하나.
  로컬 모드(ollama · llamacpp)면 허용 목록이 비어 외부 송신은 모두 막힌다(EgressBlocked = 연결 오류 → 규칙 결과로 대신).
- 기록: 외부 송신은 INFO, 막힌 송신은 WARNING 한 줄(호스트 · 경로 · 결과만. 본문 · 머리글 · 키는 남기지 않는다).
  건수는 프로세스 시작부터 세어 GET /health의 egress에 보인다.
"""
import ipaddress
import logging
import threading
from collections import Counter
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("app.egress")
_lock = threading.Lock()
_counts: Counter = Counter()  # local · external · blocked
_external_hosts: Counter = Counter()
_blocked_hosts: Counter = Counter()


class EgressBlocked(httpx.TransportError):
    """허용 목록에 없는 외부 호스트로 보내려 했다. 연결 실패와 같게 다룬다(모델 실패 → 규칙 결과)."""


def is_local(host: str | None) -> bool:
    host = (host or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".internal", ".local")) or "." not in host:
        return True  # 점 없는 이름은 같은 네트워크의 컨테이너 · 서비스 이름(docker compose · Railway 사설망)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def allowed_hosts(settings) -> frozenset[str]:
    """서비스 설정이 허용하는 외부 호스트. 엑사원 API 모드일 때만 그 호스트 하나(D53). 로컬 모드는 빈 목록."""
    if settings.llm_backend == "exaone_api":
        host = urlsplit(settings.exaone_api_base_url).hostname
        return frozenset({host.lower()}) if host and not is_local(host) else frozenset()
    return frozenset()


def hooks(settings) -> dict:
    """httpx.Client(event_hooks=…)에 넘긴다. 클라이언트를 만들 때의 설정으로 허용 목록을 정한다."""
    allow = allowed_hosts(settings)

    def on_request(request: httpx.Request) -> None:
        host = (request.url.host or "").lower()
        if is_local(host):
            with _lock:
                _counts["local"] += 1
            return
        if host in allow:
            with _lock:
                _counts["external"] += 1
                _external_hosts[host] += 1
            log.info("외부 송신 host=%s path=%s", host, request.url.path)
            return
        with _lock:
            _counts["blocked"] += 1
            _blocked_hosts[host] += 1
        log.warning("외부 송신 막음(허용 목록 밖) host=%s path=%s", host, request.url.path)
        raise EgressBlocked(f"허용 목록에 없는 외부 호스트: {host}", request=request)

    return {"request": [on_request]}


def snapshot(settings) -> dict:
    """GET /health용. 시연 ⑧: 로컬 모드로 바꾼 뒤 서비스 경로를 돌려도 external이 0이다."""
    with _lock:
        return {"mode": "external_allowed" if allowed_hosts(settings) else "local_only",
                "allow": sorted(allowed_hosts(settings)), "local": _counts["local"], "external": _counts["external"],
                "blocked": _counts["blocked"], "external_hosts": dict(_external_hosts), "blocked_hosts": dict(_blocked_hosts)}


def reset() -> None:
    """테스트 · 시연용: 건수를 0으로."""
    with _lock:
        _counts.clear()
        _external_hosts.clear()
        _blocked_hosts.clear()
