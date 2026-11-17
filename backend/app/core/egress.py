"""외부 송신 허용 목록 · 송신 기록 (구조도 10절 · 시연 ⑧). ai 서비스의 app/core/egress.py와 같은 규칙이다(서비스 경계상 따로 둔다).

backend가 밖으로 보내는 HTTP는 ai 서비스 호출(ai_client)뿐이다. ai 주소(AI_SERVICE_URL)는 우리 서비스라 공개 주소여도 허용하고
'외부'가 아니라 ai_service로 센다(모델 외부 호출은 ai /health의 egress가 센다).
그 밖의 외부 호스트는 막는다(Outlook Graph는 BE-7에서 MAIL_SOURCE=outlook_graph일 때 허용 목록에 더한다).
기록은 호스트 · 경로 · 건수만 남기고 본문 · 머리글은 남기지 않는다. 건수는 GET /health의 egress에 보인다.
"""
import ipaddress
import logging
import threading
from collections import Counter
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("app.egress")
_lock = threading.Lock()
_counts: Counter = Counter()
_hosts: Counter = Counter()


class EgressBlocked(httpx.TransportError):
    """허용 목록에 없는 외부 호스트. 연결 실패와 같게 다룬다(ai 호출이면 AIError → 503 · 규칙 결과)."""


def is_local(host: str | None) -> bool:
    host = (host or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".internal", ".local")) or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def allowed_hosts(ai_service_url: str) -> frozenset[str]:
    host = urlsplit(ai_service_url).hostname
    return frozenset({host.lower()}) if host and not is_local(host) else frozenset()


def hooks(ai_service_url: str) -> dict:
    allow = allowed_hosts(ai_service_url)

    def on_request(request: httpx.Request) -> None:
        host = (request.url.host or "").lower()
        kind = "local" if is_local(host) else "ai_service" if host in allow else "blocked"
        with _lock:
            _counts[kind] += 1
            if kind != "local":
                _hosts[f"{kind}:{host}"] += 1
        if kind == "blocked":
            log.warning("외부 송신 막음(허용 목록 밖) host=%s path=%s", host, request.url.path)
            raise EgressBlocked(f"허용 목록에 없는 외부 호스트: {host}", request=request)

    return {"request": [on_request]}


def snapshot(ai_service_url: str) -> dict:
    with _lock:
        return {"allow": sorted(allowed_hosts(ai_service_url)), "local": _counts["local"],
                "ai_service": _counts["ai_service"], "blocked": _counts["blocked"], "hosts": dict(_hosts)}


def reset() -> None:
    with _lock:
        _counts.clear()
        _hosts.clear()
