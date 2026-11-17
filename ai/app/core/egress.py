"""외부 송신 허용 목록 · 송신 기록 (구조도 10절 · D41 → D53 · 기획 detail 시연 ⑧ "로컬 모드면 외부 LLM 호출 0건").

ai 서비스가 밖으로 보내는 HTTP(모델 호출)는 모두 여기 hooks()를 건 httpx 클라이언트로 나간다.
- 로컬(is_local: 루프백 · 사설망 · 링크 로컬 IP, localhost · *.internal · 점 없는 컨테이너 이름)은 그대로 보낸다.
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
    """로컬(같은 기계 · 사설망 · 같은 네트워크의 서비스 이름)인가. 주소 문자열만 보고 판정한다 — DNS로 풀리는 실제 주소
    (search domain · 리바인딩)까지는 보지 않는다. 주소는 운영자가 .env로 정하므로 그 범위의 실수를 막는 장치다(#207 리뷰).
    1) IP로 읽히면 IP로 판정(IPv6 포함): 루프백 · 사설 · 링크 로컬이면 로컬. CGNAT(100.64/10, Tailscale)는 외부로 본다.
    2) 이름: localhost · *.localhost · *.internal · *.local, 점 없는 컨테이너 이름(docker compose · Railway 사설망)은 로컬.
       단 숫자뿐이거나 0x로 시작하는 이름은 IP를 다르게 쓴 것일 수 있어 외부로 본다(134744072처럼 IP를 10진수로 쓴 표기)."""
    host = (host or "").strip("[]").rstrip(".").lower()
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host.isdigit() or host.startswith("0x"):
            return False
        return host == "localhost" or host.endswith((".localhost", ".internal", ".local")) or "." not in host
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
    """GET /health용. 시연 ⑧: 로컬 모드로 바꾼 뒤 서비스 경로를 돌려도 external이 0이다.
    local은 모델 서버로 보낸 요청 수다(모델 호출뿐 아니라 /health의 상태 확인 · 예열 요청도 센다)."""
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
