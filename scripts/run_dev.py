#!/usr/bin/env python3
"""로컬 동시 실행 (INF-7, infra/plan.md). ai · backend · frontend를 한 번에 띄우고 Ctrl+C로 한 번에 끈다.

  python scripts/run_dev.py                    # 셋 다. 엑사원이 없으면 ai는 규칙 결과만 낸다
  python scripts/run_dev.py --no-llm           # 엑사원을 부르지 않는다(LLM_ENABLED=false)
  python scripts/run_dev.py --only ai,backend  # 고른 것만
  scripts/exaone-pc.sh run python scripts/run_dev.py   # 개발 서버에서 PC 엑사원 터널을 쓸 때(AI-D9)

- 밖에 여는 포트는 frontend 하나다. 화면은 같은 출처의 /api/...만 부르고 Vite 프록시가 backend로 넘긴다(CORS 설정 없음).
  ai(8001) · backend(8000)는 127.0.0.1에만 연다. 개발 서버는 여러 계정이 같이 써서 8000 등이 이미 잡혀 있을 수 있다 →
  그 포트가 사용 중이면 빈 포트를 골라 AI_SERVICE_URL · BACKEND_PROXY_TARGET으로 서로 이어 준다.
- frontend 포트: --port > 환경 변수 PORT(개발 서버 계정마다 할당) > 5173. PORT가 있으면 0.0.0.0에 연다(외부 브라우저 접속).
- 루트 .env를 읽어 세 서비스에 넘긴다. 이미 셸에 있는 값이 이긴다(exaone-pc.sh run이 넣은 값 등).
  평가 전용 외부 LLM 키(ANTHROPIC_API_KEY · OPENROUTER_API_KEY 등)는 .env · 셸 어디에 있어도 빼고 넘긴다(D41).
- 파이썬은 각 폴더의 uv.lock 그대로 `uv run --locked`로 띄운다(INF-3). 접근 로그는 서비스의 요청 ID 로그(INF-12)만 남긴다.
- 표준 라이브러리만 쓴다. Windows에서도 돈다.
"""
import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WIN = os.name == "nt"
AI_PORT, BACKEND_PORT, FRONTEND_PORT = 8001, 8000, 5173
COLORS = {"ai": "35", "backend": "36", "frontend": "33"}
# 서비스 프로세스 환경에 넣지 않는 외부 LLM 키. eval/에서만 쓴다(D41). 이름 규칙은 scripts/check_boundaries.py LLM_KEY_NAME과 같다
EVAL_ONLY_KEY = re.compile(r"(?:ANTHROPIC|OPENROUTER|OPENAI|CLAUDE)_API_KEY")


def load_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE 줄만 읽는다. 값 뒤 ' # 설명'과 따옴표는 뗀다. 주석 줄(# KEY=)은 코드 기본값이라 넘기지 않는다."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def service_env(dotenv: dict[str, str], shell: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """.env 위에 셸 값을 얹고, 평가 전용 키를 뺀다. (서비스 환경, 뺀 이름 목록 — 값은 돌려주지 않는다)."""
    env = {**dotenv, **shell}
    dropped = sorted(k for k in env if EVAL_ONLY_KEY.fullmatch(k))
    for key in dropped:
        del env[key]
    return env, dropped


def which(name: str) -> str:
    found = shutil.which(name)
    if not found:
        sys.exit(f"'{name}'을 찾을 수 없다. 설치 안내: README 4절")
    return found


def free_port(preferred: int) -> int:
    """127.0.0.1의 preferred가 비어 있으면 그대로, 사용 중이면 운영체제가 고른 빈 포트."""
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("빈 포트를 찾지 못했다")


def services(args: argparse.Namespace, ports: dict[str, int]) -> list[tuple[str, list[str], Path, str | None]]:
    """(이름, 명령, 실행 폴더, 준비 확인 주소)."""
    uv = which("uv") if {"ai", "backend"} & set(args.only) else ""
    out = []
    for name in ("ai", "backend"):
        if name in args.only:
            port = ports[name]
            cmd = [uv, "run", "--locked", "uvicorn", "app.main:app",
                   "--host", "127.0.0.1", "--port", str(port), "--no-access-log"]
            if args.reload:
                cmd.append("--reload")
            out.append((name, cmd, ROOT / name, f"http://127.0.0.1:{port}/health"))
    if "frontend" in args.only:
        fe = ROOT / "frontend"
        if not (fe / "package.json").exists():
            print("frontend/package.json 없음(FE-1 골격 병합 전) — frontend는 건너뛴다")
        else:
            npm = which("npm")
            if not (fe / "node_modules").exists():
                print("frontend/node_modules 없음 → npm ci (처음 한 번)")
                subprocess.run([npm, "ci"], cwd=fe, check=True)
            cmd = [npm, "run", "dev", "--", "--host", args.host, "--port", str(args.port), "--strictPort"]
            out.append(("frontend", cmd, fe, None))
    return out


def pump(name: str, proc: subprocess.Popen, color: bool) -> None:
    tag = f"\033[{COLORS[name]}m[{name}]\033[0m" if color else f"[{name}]"
    for line in proc.stdout:  # type: ignore[union-attr]
        sys.stdout.write(f"{tag} {line}")
        sys.stdout.flush()


def wait_ready(name: str, url: str, timeout: float = 90) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    print(f"[run_dev] {name} 준비됨 ({url})")
                    return
        except OSError:
            pass
        time.sleep(1)
    print(f"[run_dev] {name}: {timeout:.0f}초 안에 {url} 응답 없음 — 위 [{name}] 로그를 본다")


def stop(procs: dict[str, subprocess.Popen]) -> None:
    for proc in procs.values():
        if proc.poll() is None:
            if IS_WIN:  # npm · uv가 띄운 자식까지 끈다
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            else:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
    end = time.monotonic() + 10
    for proc in procs.values():
        try:
            proc.wait(timeout=max(0.1, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            if not IS_WIN:
                os.killpg(proc.pid, signal.SIGKILL)


def _interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> int:
    # kill · 터미널 닫기도 Ctrl+C처럼 끈다. 서비스는 따로 세션을 열어 띄우므로 이게 없으면 run_dev만 죽고 포트를 쥔 채 남는다
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)
    env_port = os.environ.get("PORT", "").strip()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default="ai,backend,frontend", help="쉼표로 구분: ai,backend,frontend")
    ap.add_argument("--port", type=int, default=int(env_port) if env_port.isdigit() else FRONTEND_PORT,
                    help="frontend 포트(기본: 환경 변수 PORT, 없으면 5173)")
    ap.add_argument("--host", default="0.0.0.0" if env_port else "127.0.0.1",
                    help="frontend를 열 주소(기본: PORT가 있으면 0.0.0.0, 없으면 127.0.0.1)")
    ap.add_argument("--no-llm", action="store_true", help="엑사원을 부르지 않는다(LLM_ENABLED=false)")
    ap.add_argument("--reload", action="store_true", help="파이썬 코드가 바뀌면 다시 띄운다(uvicorn --reload)")
    args = ap.parse_args()
    args.only = [s.strip() for s in args.only.split(",") if s.strip()]
    if bad := set(args.only) - set(COLORS):
        ap.error(f"--only에 모르는 이름: {', '.join(sorted(bad))}")

    env, dropped = service_env(load_dotenv(ROOT / ".env"), dict(os.environ))
    if dropped:
        print(f"[run_dev] 평가 전용 키는 서비스에 넘기지 않는다(D41): {', '.join(dropped)}")
    ports = {}
    for name, preferred, var in (("ai", AI_PORT, "AI_SERVICE_URL"), ("backend", BACKEND_PORT, "BACKEND_PROXY_TARGET")):
        if name in args.only:  # 같이 띄우는 서비스끼리는 실제로 연 포트로 잇는다(backend → ai, frontend 프록시 → backend)
            ports[name] = free_port(preferred)
            if ports[name] != preferred:
                print(f"[run_dev] {preferred} 사용 중 → {name}는 {ports[name]}에 연다")
            env[var] = f"http://127.0.0.1:{ports[name]}"  # BACKEND_PROXY_TARGET은 frontend/vite.config.ts가 읽는다
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    if args.no_llm:
        env["LLM_ENABLED"] = "false"
    if not (ROOT / ".env").exists():
        print("[run_dev] 루트 .env 없음 — 코드 기본값으로 띄운다(cp .env.example .env 권장)")

    plan = services(args, ports)
    if not plan:
        print("[run_dev] 띄울 서비스가 없다")
        return 1
    color = sys.stdout.isatty() and not IS_WIN
    procs: dict[str, subprocess.Popen] = {}
    try:
        for name, cmd, cwd, _ in plan:
            procs[name] = subprocess.Popen(
                cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
                start_new_session=not IS_WIN,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0,
            )
            threading.Thread(target=pump, args=(name, procs[name], color), daemon=True).start()
        for name, _, _, url in plan:
            if url:
                threading.Thread(target=wait_ready, args=(name, url), daemon=True).start()
        if "frontend" in procs:
            shown = "localhost" if args.host in ("0.0.0.0", "127.0.0.1") else args.host
            print(f"[run_dev] 화면: http://{shown}:{args.port}  (/api → {env.get('BACKEND_PROXY_TARGET')}, Ctrl+C로 모두 끈다)")
        while True:
            for name, proc in procs.items():
                if (code := proc.poll()) is not None:
                    print(f"[run_dev] {name}가 멈췄다(종료 코드 {code}) — 나머지도 끈다")
                    return code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[run_dev] 끄는 중…")
        return 0
    finally:
        stop(procs)


if __name__ == "__main__":
    sys.exit(main())
