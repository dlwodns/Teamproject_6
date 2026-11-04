"""GPU 측정 보조 도구 (scripts/gpu/*.sh가 부른다). ai/.venv 파이썬으로 실행한다.

  health    ollama 연결 · 모델 · 고정값(digest · 버전) 확인. 준비 안 되면 종료 코드 1
  resident  올라간 모델이 GPU 메모리에 얼마나 올라갔는지(size_vram / size). --min 미만이면 1
  hwinfo    GPU 이름 · VRAM · 드라이버 · CUDA · CPU · RAM · ollama 버전 · digest를 env.md · hw.txt로
  stamp     보고서 제목 아래에 하드웨어 한 줄을 넣는다
  compare   CPU · GPU 모델 출력 캐시(llm_cache_*.json)를 같은 프롬프트끼리 비교한다(temperature 0이어도 다를 수 있다)
  summary   결과 폴더의 보고서에서 핵심 줄만 모아 summary.md를 만든다
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))


def _settings():
    from app.core.config import get_settings
    return get_settings()


def _http():
    import httpx
    s = _settings()
    transport = httpx.HTTPTransport(uds=s.ollama_uds) if s.ollama_uds else None
    return httpx.Client(base_url=s.ollama_base_url, timeout=10, transport=transport)


def _health() -> dict:
    from app.llm.client import OllamaClient
    return OllamaClient(_settings()).health()


def _sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _ps_model() -> dict | None:
    model = _settings().model
    ms = _http().get("/api/ps").json().get("models", [])
    return next((m for m in ms if model in (m.get("name"), m.get("model"))), None)


def cmd_health(a) -> int:
    h = _health()
    print(json.dumps(h, ensure_ascii=False))
    return 0 if h.get("model_ready") else 1


def cmd_resident(a) -> int:
    m = _ps_model()
    if not m:
        print(json.dumps({"loaded": False}))
        return 1
    ratio = m.get("size_vram", 0) / max(m.get("size", 1), 1)
    out = {"loaded": True, "size_gb": round(m.get("size", 0) / 1e9, 2), "size_vram_gb": round(m.get("size_vram", 0) / 1e9, 2),
           "gpu_ratio": round(ratio, 3), "context_length": m.get("context_length")}
    print(json.dumps(out))
    return 0 if ratio >= a.min else 1


def gpu_rows() -> list[str]:
    q = _sh(["nvidia-smi", "--query-gpu=name,memory.total,driver_version,power.limit", "--format=csv,noheader"])
    cuda = re.search(r"CUDA Version:\s*([\d.]+)", _sh(["nvidia-smi"]))
    return [f"{ln.strip()} · CUDA {cuda[1] if cuda else '?'}" for ln in q.splitlines() if ln.strip()] or ["GPU 정보 없음"]


def cmd_hwinfo(a) -> int:
    s, h = _settings(), _health()
    try:
        ps = _ps_model() or {}
    except Exception:  # noqa: BLE001 — 정보 수집용, 실패해도 기록만 비운다
        ps = {}
    cpu = re.search(r"Model name:\s*(.+)", _sh(["lscpu"]))
    mem = re.search(r"Mem:\s+(\S+)", _sh(["free", "-h"]))
    gpus = gpu_rows()
    par = Path(a.run_dir, "num_parallel").read_text().strip() if a.run_dir and Path(a.run_dir, "num_parallel").exists() else "?"
    pinned = bool(s.model_digest and s.ollama_version)
    rows = [
        f"- GPU: {' / '.join(gpus)}",
        f"- CPU · RAM: {cpu[1].strip() if cpu else platform.processor() or '?'} · {mem[1] if mem else '?'}",
        f"- ollama {h.get('version') or '?'} · digest {(h.get('digest') or '?')[:12]} · 모델 {s.model}",
        f"- 고정값 확인: {'켬(exaone-pc.env)' if pinned else '**끔 — GPU_ALLOW_UNPINNED=1, CPU 수치와 직접 비교 불가**'}",
        f"- ollama 설정: OLLAMA_NUM_PARALLEL {par} · keep_alive {s.ollama_keep_alive} · 문맥 길이 {ps.get('context_length') or os.environ.get('GPU_CONTEXT_LENGTH') or 'ollama 기본'}"
        f" · GPU 적재 {ps.get('size_vram', 0) / max(ps.get('size', 1), 1):.0%}" if ps else
        f"- ollama 설정: OLLAMA_NUM_PARALLEL {par} · keep_alive {s.ollama_keep_alive} · (모델 미적재)",
        f"- 제한 시간 LLM_TIMEOUT_S {s.llm_timeout_s:.0f} · 라우터 기준 {s.router_threshold}",
    ]
    Path(a.out).write_text("# GPU 측정 환경\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    if a.line:
        Path(a.line).write_text(f"- 하드웨어: {' / '.join(gpus)} · ollama {h.get('version') or '?'} · digest {(h.get('digest') or '?')[:12]} · NUM_PARALLEL {par}\n",
                                encoding="utf-8")
    print("\n".join(rows))
    return 0


def cmd_stamp(a) -> int:
    p, line = Path(a.report), Path(a.line).read_text(encoding="utf-8").strip()
    if not p.exists():
        return 1
    lines = p.read_text(encoding="utf-8").splitlines()
    if line not in lines:
        lines[1:1] = ["", line] if len(lines) < 2 or lines[1].strip() else [line]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def cmd_compare(a) -> int:
    x = json.loads(Path(a.cpu).read_text(encoding="utf-8"))
    y = json.loads(Path(a.gpu).read_text(encoding="utf-8"))
    both = sorted(set(x) & set(y))
    same = [k for k in both if json.dumps(x[k], sort_keys=True, ensure_ascii=False) == json.dumps(y[k], sort_keys=True, ensure_ascii=False)]
    diff = [k for k in both if k not in same]
    md = [f"## 모델 출력 비교 · {Path(a.cpu).name} (CPU) vs {Path(a.gpu).name} (GPU)", "",
          f"- 같은 프롬프트(규칙 · 프롬프트 · 메일이 같은 호출): {len(both)}건 / CPU {len(x)} · GPU {len(y)}",
          f"- 출력이 글자까지 같음: {len(same)}건 · 다름: {len(diff)}건"]
    if not both:
        md.append("- 겹치는 프롬프트가 없다 — CPU 캐시를 만든 뒤 프롬프트나 규칙이 바뀌었다. 정확도는 보고서끼리 비교한다")
    for k in diff[:a.limit]:
        md += [f"- `{k}`", f"  - CPU: `{json.dumps(x[k], ensure_ascii=False)[:300]}`", f"  - GPU: `{json.dumps(y[k], ensure_ascii=False)[:300]}`"]
    text = "\n".join(md) + "\n"
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


PATS = {
    "완전 정답": r"메일 완전 정답:\s*([\d/]+\s*\([\d.]+%\))",
    "Task 재현율": r"Task 메일 재현율\s*\|\s*\**([\d.]+%)",
    "Task 정밀도": r"Task 메일 정밀도\s*\|\s*\**([\d.]+%)",
    "주 유형": r"주 유형 정확도\s*\|\s*\**([\d.]+%)",
    "엑사원행": r"엑사원으로 보낸\(보낼\) 메일\s*(\d+)건",
    "1통 평균": r"평균 응답 시간 \(첫 호출 제외\)\s*\|\s*([\d.]+초)",
    "최소/최대": r"최소 / 최대\s*\|\s*([\d.]+초 / [\d.]+초)",
    "첫 호출": r"첫 호출 \(로딩 포함\)\s*\|\s*([\d.]+초)",
    "JSON 오류": r"JSON 형식 오류\s*\|\s*(\d+)건",
    "호출 실패": r"호출 실패 \(연결 · 시간 초과\)\s*\|\s*(\d+)건",
}
CMD_PATS = {
    "모두 일치": r"모두 일치:\s*([\d/]+)",
    "위험한 오탐": r"위험한 오탐[^:]*:\s*(\d+)건",
    "모델 경로 평균": r"모델 경로\s*([\d.]+ms\s*\(\d+건\))",
}


def _grab(text: str, pats: dict) -> list[str]:
    return [(m[1] if (m := re.search(p, text)) else "-") for p in pats.values()]


def cmd_summary(a) -> int:
    d = Path(a.dir)
    env = (d / "env.md").read_text(encoding="utf-8") if (d / "env.md").exists() else ""
    md = ["# GPU 측정 요약", "", *[ln for ln in env.splitlines() if ln.startswith("- ")], ""]
    if (d / "GPU_BUNDLE.txt").exists():
        b = (d / "GPU_BUNDLE.txt").read_text(encoding="utf-8")
        md += [ln if ln.startswith("- ") else f"- {ln}" for ln in b.splitlines() if re.match(r"-?\s*(HEAD|브랜치|규칙|프롬프트|만든 시각)", ln)] + [""]
    reps = sorted(d.glob("eval_report_*.md"))
    if reps:
        md += ["## 메일 분류", "", "| 보고서 | " + " | ".join(PATS) + " |", "|---|" + "---|" * len(PATS)]
        md += [f"| {r.stem.removeprefix('eval_report_')} | " + " | ".join(_grab(r.read_text(encoding="utf-8"), PATS)) + " |" for r in reps]
        md.append("")
    cmds = sorted(d.glob("agent_commands*_llm.md"))
    if cmds:
        md += ["## 명령 해석", "", "| 보고서 | " + " | ".join(CMD_PATS) + " |", "|---|" + "---|" * len(CMD_PATS)]
        md += [f"| {r.stem} | " + " | ".join(_grab(r.read_text(encoding="utf-8"), CMD_PATS)) + " |" for r in cmds]
        md.append("")
    for b in sorted(d.glob("bench_*.md")):
        t = b.read_text(encoding="utf-8")
        sec = t.split("## 요약", 1)
        if len(sec) == 2:
            md += [f"## 응답 시간 벤치 · {b.stem}", "", sec[1].split("\n## ", 1)[0].strip(), ""]
    if (d / "compare.md").exists():
        md += [(d / "compare.md").read_text(encoding="utf-8").replace("## 모델 출력 비교", "### 모델 출력 비교"), ""]
    if (d / "stages.tsv").exists():
        md += ["## 단계별 소요", "", "| 단계 | 결과 | 초 |", "|---|---|---|"]
        for ln in (d / "stages.tsv").read_text(encoding="utf-8").splitlines():
            parts = ln.split("\t")
            if len(parts) >= 3:
                md.append(f"| {parts[0]} | {parts[1]} | {parts[2]} |")
    Path(a.out or d / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    p = sub.add_parser("resident")
    p.add_argument("--min", type=float, default=0.99)
    p = sub.add_parser("hwinfo")
    p.add_argument("--out", required=True)
    p.add_argument("--line", help="보고서에 찍을 한 줄을 이 파일에 쓴다")
    p.add_argument("--run-dir")
    p = sub.add_parser("stamp")
    p.add_argument("report")
    p.add_argument("line")
    p = sub.add_parser("compare")
    p.add_argument("cpu")
    p.add_argument("gpu")
    p.add_argument("--out")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("summary")
    p.add_argument("dir")
    p.add_argument("--out")
    a = ap.parse_args()
    return {"health": cmd_health, "resident": cmd_resident, "hwinfo": cmd_hwinfo, "stamp": cmd_stamp,
            "compare": cmd_compare, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
