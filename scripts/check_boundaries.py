#!/usr/bin/env python3
"""경계 · 비밀값 검사 (INF-8, infra/plan.md). 표준 라이브러리만 쓴다(Python 3.10 이상).

  python scripts/check_boundaries.py --staged      # 커밋 전(.githooks/pre-commit): 스테이징된 파일만
  python scripts/check_boundaries.py --all         # CI · 수동: 추적 중인 파일 전부 + 환경 변수 목록
  python scripts/check_boundaries.py --selfcheck   # 검사 규칙 점검 → selfcheck OK

막음(종료 코드 1)
  1. 올리면 안 되는 파일: .env(.env.example 제외) · 키 · 인증서 · data/raw/ 원본(D24) · 실제 메일함 캡처
  2. 비밀값: API 키 · 토큰 · 개인키 모양의 글자, 설정 파일에 값이 채워진 비밀 변수
  3. 서버 내부 정보: 실제 계정 홈 경로, 사설 · 공인 IP 주소
  4. 서비스 경계: frontend · backend · ai의 외부 LLM 호출(D26 · D41), backend · ai의 eval import(eval → ai 한 방향),
     backend의 ai 코드 import(HTTP로만, D34), ai의 DB 접근(D34)
  5. 서비스 코드가 읽는 환경 변수 중 .env.example에 없는 것(--all, INF-4). 기본값으로 충분한 변수는 '# NAME=기본값' 주석으로 적는다
경고(종료 코드 0)
  - 개인 메일 주소(gmail · naver 등). 예시 주소는 example.com을 쓴다

찾은 값은 앞 4글자만 보인다(CI 로그에 남지 않게). 일부러 넣은 가짜 값이면 그 줄 끝에 `boundary-ok`를 적는다.
"""
import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

ALLOW = "boundary-ok"
SERVICE_DIRS = ("frontend/", "backend/", "ai/")
CODE_SUFFIX = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"}
CONFIG_SUFFIX = {".env", ".sh", ".ps1", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties"}
MAILBOX_CAPTURES = {"docs/20_frontend/ui_reference/gmail_image.png", "docs/20_frontend/ui_reference/outlook_image.png"}
MAX_BYTES = 10_000_000

SECRETS = [
    ("Anthropic API 키", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenRouter API 키", re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}")),
    ("OpenAI 형식 API 키", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("GitHub 토큰", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("AWS 접근 키", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack 토큰", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("개인키", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
]
SECRET_VAR = re.compile(r"^\s*(?:export\s+|\$env:)?([A-Z0-9_]*(?:SECRET|SECRET_KEY|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|"
                        r"PRIVATE_KEY|TOKEN|ENCRYPTION_KEY))\s*[=:]\s*(.*)$")  # TOKEN: ACCESS_ · AUTH_ · HF_ · GITHUB_TOKEN 등
HOME_PATH = re.compile(r"(?:/home/[a-z_][a-z0-9_.\-]*|/Users/[A-Za-z0-9_.\-]+|[A-Za-z]:\\Users\\[^\\<>\s\"']+)(?=[/\\'\"`\s)]|$)")
IPV4 = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])")
IP_OK = ("127.", "0.0.0.0", "255.255.255.255", "192.0.2.", "198.51.100.", "203.0.113.")  # 루프백 · 문서용 대역
PERSONAL_MAIL = re.compile(r"[A-Za-z0-9._%+\-]+@(?:gmail|naver|daum|hanmail|kakao|nate|outlook|hotmail|live|yahoo|icloud|"
                           r"proton|protonmail)\.(?:com|net|co\.kr|me)\b", re.I)

LLM_PY_IMPORT = re.compile(r"^\s*(?:import|from)\s+(anthropic|openai|litellm|langchain_anthropic|langchain_openai)\b")
LLM_JS_IMPORT = re.compile(r"(?:from\s+|require\(\s*|import\(\s*)[\"'](@anthropic-ai/[^\"']*|openai|@openrouter/[^\"']*)[\"']")
LLM_DEP = re.compile(r"(?:^|[\"'\s,\[])(anthropic|openai|litellm|langchain-openai|langchain-anthropic)(?=\s*[<>=!~\[;\"',]|\s*$)")
LLM_HOST = re.compile(r"api\.anthropic\.com|openrouter\.ai|api\.openai\.com")
LLM_KEY_NAME = re.compile(r"\b(?:ANTHROPIC|OPENROUTER|OPENAI|CLAUDE)_API_KEY\b")
EVAL_IMPORT = re.compile(r"^\s*(?:from|import)\s+eval(?:\.|\s|$)")
AI_IMPORT = re.compile(r"^\s*(?:from|import)\s+ai(?:\.|\s|$)|[\"'](?:\.\./)*ai/app[/\"']")
DB_IMPORT = re.compile(r"^\s*(?:from|import)\s+(sqlite3|sqlalchemy|aiosqlite|sqlmodel|psycopg2?|asyncpg|pymysql)\b")

ENV_PY = re.compile(r"(?:environ|getenv|env)\s*(?:\.get)?\s*[(\[]\s*[\"']([A-Z][A-Z0-9_]{2,})[\"']")
ENV_JS = re.compile(r"(?:import\.meta\.env|process\.env)\.([A-Z][A-Z0-9_]{2,})")
ENV_EXAMPLE = re.compile(r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)\s*=", re.M)  # "# NAME=값"(주석, 코드 기본값)도 적어 둔 것으로 본다
ENV_BUILTIN = {"PATH", "HOME", "TZ", "CI", "NODE_ENV", "PYTHONPATH", "MODE", "DEV", "PROD", "SSR", "BASE_URL"}


@dataclass
class Finding:
    block: bool
    path: str
    line: int
    rule: str
    sample: str = ""

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        tail = f" ({self.sample[:4]}…)" if self.sample else ""
        return f"[{'막음' if self.block else '경고'}] {where} {self.rule}{tail}"


def forbidden(path: str) -> str | None:
    p = PurePosixPath(path)
    name = p.name.lower()
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return ".env 파일 — 비밀값은 .env에만 두고 올리지 않는다"
    if p.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}:
        return "키 · 인증서 파일"
    if name in {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}:
        return "SSH 개인키"
    if path.startswith("data/raw/") and path != "data/raw/README.md":
        return "MailEx 원본(실명 포함, D24)"
    if path in MAILBOX_CAPTURES:
        return "실제 메일함 캡처(실명 · 개인 메일 주소)"
    return None


def _is_config(path: str) -> bool:
    p = PurePosixPath(path)
    return p.suffix.lower() in CONFIG_SUFFIX or p.name.lower().startswith(".env")


def _placeholder(value: str) -> bool:
    v = re.sub(r"(?:^|\s)#.*$", "", value).strip().strip("\"'").strip()  # 줄 끝 주석을 뺀 값
    return (not v or v[0] in "$<%{" or v.lower() in {"changeme", "change-me", "none", "null", "dummy", "test"}
            or set(v) <= set("x*.-_"))


def scan(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    p = PurePosixPath(path)
    in_service = path.startswith(SERVICE_DIRS)
    is_code = p.suffix.lower() in CODE_SUFFIX
    is_dep = p.name in {"pyproject.toml", "package.json"} or (p.name.startswith("requirements") and p.suffix == ".txt")
    is_config = _is_config(path)
    for no, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        hit = next(((name, m) for name, rx in SECRETS if (m := rx.search(line))), None)
        if hit:
            out.append(Finding(True, path, no, f"비밀값: {hit[0]}", hit[1].group(0)))
        if is_config and (m := SECRET_VAR.match(line)) and not _placeholder(m.group(2)):
            out.append(Finding(True, path, no, f"비밀 변수에 값이 들어 있다: {m.group(1)}", m.group(2).strip()))
        if m := HOME_PATH.search(line):
            out.append(Finding(True, path, no, "서버 내부 정보: 실제 계정 홈 경로 — $HOME · ~ 또는 인자로 받는다", m.group(0)))
        for m in IPV4.finditer(line):
            if not m.group(0).startswith(IP_OK):
                out.append(Finding(True, path, no, "서버 내부 정보: IP 주소 — 주소는 .env나 실행 인자로 받는다", m.group(0)))
                break
        if m := PERSONAL_MAIL.search(line):
            out.append(Finding(False, path, no, "개인 메일 주소 — 예시 주소는 example.com을 쓴다", m.group(0)))
        if not in_service:
            continue
        if is_code or is_dep:
            if LLM_HOST.search(line) or LLM_KEY_NAME.search(line):
                out.append(Finding(True, path, no, "서비스 경계: 서비스 경로에서 외부 LLM 주소 · 키 사용(D26 · D41)"))
        if is_dep:
            body = line if p.name == "package.json" else line.split("#", 1)[0]
            if (p.name == "package.json" and re.search(r"\"(@anthropic-ai/[^\"]+|openai)\"\s*:", body)) or \
               (p.name != "package.json" and LLM_DEP.search(body)):
                out.append(Finding(True, path, no, "서비스 경계: 서비스 의존성에 외부 LLM SDK(D41)"))
        if not is_code:
            continue
        if (p.suffix == ".py" and LLM_PY_IMPORT.match(line)) or (p.suffix != ".py" and LLM_JS_IMPORT.search(line)):
            out.append(Finding(True, path, no, "서비스 경계: 서비스 경로에서 외부 LLM SDK import(D26 · D41)"))
        if p.suffix == ".py" and path.startswith(("backend/", "ai/")) and EVAL_IMPORT.match(line):
            out.append(Finding(True, path, no, "서비스 경계: backend · ai가 eval을 import(의존은 eval → ai 한 방향)"))
        if p.suffix == ".py" and path.startswith("backend/") and AI_IMPORT.search(line):
            out.append(Finding(True, path, no, "서비스 경계: backend가 ai 코드를 import(ai는 HTTP로만 부른다, D34)"))
        if p.suffix == ".py" and path.startswith("ai/") and DB_IMPORT.match(line):
            out.append(Finding(True, path, no, "서비스 경계: ai의 DB 접근(D34)"))
    return out


def env_names_used(path: str, text: str) -> list[tuple[str, int]]:
    if not path.startswith(SERVICE_DIRS) or PurePosixPath(path).suffix.lower() not in CODE_SUFFIX:
        return []
    rx = ENV_PY if path.endswith(".py") else ENV_JS
    # 줄 끝 boundary-ok는 이 규칙에도 통한다(테스트가 일부러 넣는 없어진 변수 등)
    return [(m.group(1), no) for no, line in enumerate(text.splitlines(), 1) if ALLOW not in line for m in rx.finditer(line)]


def check_env(files: dict[str, str]) -> list[Finding]:
    declared = set(ENV_EXAMPLE.findall(files.get(".env.example", "")))
    out, seen = [], set()
    for path, text in files.items():
        for name, no in env_names_used(path, text):
            if name not in declared and name not in ENV_BUILTIN and name not in seen:
                seen.add(name)
                out.append(Finding(True, path, no, f".env.example에 없는 환경 변수: {name} — 기본값이 있으면 '# {name}=기본값'으로라도 적는다(INF-4)"))
    return out


# ── git에서 파일 읽기 ──
def _git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], input=data, capture_output=True, check=True).stdout


def read_index(paths: list[str]) -> dict[str, bytes]:
    """인덱스(스테이징된 내용 · CI에서는 커밋 내용)에서 읽는다. 작업 폴더의 저장 안 한 수정은 보지 않는다."""
    if not paths:
        return {}
    raw = _git("cat-file", "--batch", data="".join(f":{p}\n" for p in paths).encode())
    out, i = {}, 0
    for p in paths:
        nl = raw.index(b"\n", i)
        head = raw[i:nl].split()
        if head[-1] == b"missing":
            i = nl + 1
            continue
        size = int(head[2])
        out[p] = raw[nl + 1:nl + 1 + size]
        i = nl + 1 + size + 1
    return out


def run(paths: list[str], with_env: bool) -> list[Finding]:
    findings = [Finding(True, p, 0, f"올리면 안 되는 파일: {why}") for p in paths if (why := forbidden(p))]
    texts = {}
    for p, data in read_index(paths).items():
        if len(data) > MAX_BYTES or b"\0" in data[:8000]:
            continue  # 바이너리 · 아주 큰 파일은 이름만 본다
        texts[p] = data.decode("utf-8", errors="replace")
        findings += scan(p, texts[p])
    if with_env:
        if ".env.example" not in texts and (ex := read_index([".env.example"])):
            texts[".env.example"] = ex[".env.example"].decode("utf-8", errors="replace")
        findings += check_env(texts)
    return findings


def selfcheck() -> None:
    fake_ant = "sk-" + "ant-" + "a" * 30
    fake_gh = "gh" + "p_" + "b" * 36
    home = "/" + "home/" + "someone/run/x.sock"
    ip = ".".join(["10", "1", "2", "3"])

    def blocks(path, text):
        return [f.rule for f in scan(path, text) if f.block]

    assert blocks("eval/a.py", f"KEY = '{fake_ant}'") and blocks("README.md", fake_gh)
    assert blocks(".env.example", "MS_GRAPH_CLIENT_SECRET=abc123") and not blocks(".env.example", "MS_GRAPH_CLIENT_SECRET=   # <여기에 주입>")
    assert not blocks(".github/workflows/ci.yml", "  API_KEY: ${{ secrets.API_KEY }}")
    assert blocks(".env", "SECRET_KEY=abc123") and blocks(".env", "JWT_SECRET_KEY=abc123") and blocks(".env", "HF_TOKEN=abc123")
    assert not blocks(".env.example", "MCP_ACCESS_TOKEN=              # <여기에 주입>") and not blocks(".env", "MAX_TOKENS=512")
    assert blocks("scripts/x.ps1", f"$Sock = '{home}'") and not blocks("scripts/x.sh", "OLLAMA_UDS=$HOME/run/x.sock")
    assert blocks("docs/a.md", f"서버 {ip}") and not blocks("docs/a.md", "127.0.0.1:8001 · 0.0.0.0 · 버전 0.34.0")
    assert blocks("ai/app/x.py", "import anthropic") and not blocks("eval/judges/x.py", "import anthropic")
    assert blocks("frontend/src/x.ts", "import Anthropic from '@anthropic-ai/sdk'")
    assert blocks("ai/pyproject.toml", '    "openai>=1.0",') and not blocks("ai/pyproject.toml", "# 외부 LLM SDK(anthropic · openai)를 넣지 않는다")
    assert blocks("ai/app/x.py", "from eval import evaluate") and blocks("backend/app/x.py", "from ai.app import x")
    assert blocks("ai/app/x.py", "import sqlite3") and not blocks("backend/app/x.py", "import sqlite3")
    assert not blocks("eval/a.py", f"KEY = '{fake_ant}'  # {ALLOW}")
    w = scan("eval/d.jsonl", '{"text": "abc@' + 'gmail.com 로 보내"}')
    assert len(w) == 1 and not w[0].block and str(w[0]).endswith("(abc@…)")  # 개인 메일은 경고, 값은 앞 4글자만
    assert str(Finding(True, "a", 1, "r", fake_ant)).endswith("(sk-a…)")
    assert forbidden(".env") and forbidden("backend/.env.local") and not forbidden(".env.example")
    assert forbidden("data/raw/mailex.json") and not forbidden("data/raw/README.md") and forbidden("certs/server.key")
    env = check_env({".env.example": "AI_SERVICE_URL=x\n# LLM_TIMEOUT_S=120   # 주석\n",
                     "ai/app/c.py": 'env.get("LLM_BACKEND", "ollama")\nenv.get("AI_SERVICE_URL")\nenv.get("LLM_TIMEOUT_S")'})
    assert [(f.block, f.rule.split(" —")[0]) for f in env] == [(True, ".env.example에 없는 환경 변수: LLM_BACKEND")]
    assert not check_env({".env.example": "", "ai/tests/t.py": f'monkeypatch.setenv("OLD_FLAG", "x")  # {ALLOW}\n'})
    print("selfcheck OK")


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true", help="스테이징된 파일만(커밋 전 훅)")
    g.add_argument("--all", action="store_true", help="추적 중인 파일 전부 + 환경 변수 목록(CI)")
    g.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        selfcheck()
        return 0
    if a.staged:
        paths = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").decode().split("\0")
    else:
        paths = _git("ls-files", "-z").decode().split("\0")
    findings = run([p for p in paths if p], with_env=a.all)
    for f in findings:
        print(f)
    blocked = sum(f.block for f in findings)
    warned = len(findings) - blocked
    if blocked:
        print(f"\n경계 · 비밀값 검사: 막음 {blocked}건 · 경고 {warned}건. 위 줄을 고치고 다시 커밋한다"
              f"(일부러 넣은 가짜 값이면 그 줄 끝에 `{ALLOW}`). 규칙: scripts/check_boundaries.py 머리말")
        return 1
    print(f"경계 · 비밀값 검사: 통과 (파일 {len([p for p in paths if p])}개 · 경고 {warned}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
