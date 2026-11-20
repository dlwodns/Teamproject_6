"""외부 송신 허용 목록 · 송신 기록 (구조도 10절 · 시연 ⑧). ai 서비스의 app/core/egress.py와 같은 규칙이다(서비스 경계상 따로 둔다).

backend가 밖으로 보내는 HTTP는 ai 서비스 호출(ai_client)뿐이다. ai 주소(AI_SERVICE_URL)는 우리 서비스라 공개 주소여도 허용하고
'외부'가 아니라 ai_service로 센다(모델 외부 호출은 ai /health의 egress가 센다).
Outlook Graph(BE-7)는 Graph 클라이언트(app/mail/graph.py)만 GRAPH_HOSTS를 허용하고 'graph'로 센다 — MAIL_SOURCE=outlook_graph일 때만 그 클라이언트가 쓰인다.
그 밖의 외부 호스트는 막는다.
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
GRAPH_HOSTS = frozenset({"graph.microsoft.com", "login.microsoftonline.com",  # Graph API · Microsoft 로그인(토큰)
                         # 큰 첨부 업로드 세션 주소(AI-32, Graph 문서 예시 outlook.office.com). 개인 계정 주소는 실제 계정으로 확인 못 함
                         "outlook.office.com", "outlook.office365.com"})


class EgressBlocked(httpx.TransportError):
    """허용 목록에 없는 외부 호스트. 연결 실패와 같게 다룬다(ai 호출이면 AIError → 503 · 규칙 결과)."""


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


def allowed_hosts(ai_service_url: str) -> frozenset[str]:
    host = urlsplit(ai_service_url).hostname
    return frozenset({host.lower()}) if host and not is_local(host) else frozenset()


def hooks(ai_service_url: str, *, graph: bool = False) -> dict:
    """graph=True: Graph 클라이언트용. ai 주소 대신 GRAPH_HOSTS만 허용한다."""
    allow = GRAPH_HOSTS if graph else allowed_hosts(ai_service_url)
    allowed_kind = "graph" if graph else "ai_service"

    def on_request(request: httpx.Request) -> None:
        host = (request.url.host or "").lower()
        kind = "local" if is_local(host) else allowed_kind if host in allow else "blocked"
        with _lock:
            _counts[kind] += 1
            if kind != "local":
                _hosts[f"{kind}:{host}"] += 1
        if kind == "blocked":
            log.warning("외부 송신 막음(허용 목록 밖) host=%s path=%s", host, request.url.path)
            raise EgressBlocked(f"허용 목록에 없는 외부 호스트: {host}", request=request)

    return {"request": [on_request]}


def snapshot(ai_service_url: str, *, graph: bool = False) -> dict:
    allow = allowed_hosts(ai_service_url) | (GRAPH_HOSTS if graph else frozenset())
    with _lock:
        return {"allow": sorted(allow), "local": _counts["local"], "ai_service": _counts["ai_service"],
                "graph": _counts["graph"], "blocked": _counts["blocked"], "hosts": dict(_hosts)}


def reset() -> None:
    with _lock:
        _counts.clear()
        _hosts.clear()
