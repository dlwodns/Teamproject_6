#!/usr/bin/env bash
# 빌린 GPU 상자에서 실행: ollama(고정 버전) · 엑사원 모델 · 파이썬 환경을 준비하고 고정값 · GPU 적재를 확인한다.
#   bash scripts/gpu/setup.sh
# 멈추는 경우: GPU 안 보임 · 서버(dev-server-02) · ollama 버전이나 모델 digest가 exaone-pc.env 고정값과 다름 · 모델이 GPU에 다 안 올라감.
# 고정값과 다르면 바꿔 넘기지 않는다 — 진행 여부는 사용자가 정한다(GPU_ALLOW_UNPINNED=1, 결과에 '비교 불가'가 남는다).
set -euo pipefail
. "$(dirname "$0")/env.sh"
guard_gpu_box
cd "$ROOT"

# 1) 기본 도구 (컨테이너형 상자는 curl · zstd가 없을 수 있다)
if command -v apt-get >/dev/null && ! { command -v curl && command -v zstd; } >/dev/null; then
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq curl ca-certificates zstd pciutils >/dev/null
fi

# 2) 파이썬 환경: uv가 파이썬 3.12까지 받아 온다(상자 기본 파이썬 버전과 무관). ai/README '실행'과 같은 명령
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
if [ ! -x "$PY" ]; then
  (cd ai && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r pyproject.toml --extra dev)
fi
# 가짜 모델 단위 테스트 — 묶음이 온전한지 확인. 실패해도 빌린 시간을 쓰는 중이라 멈추지 않고 알린다
(cd ai && .venv/bin/python -m pytest -q 2>&1 | tail -1) || say "단위 테스트 실패 — 묶음(GPU_BUNDLE.txt)의 커밋 안 된 파일을 확인한다"

# 3) ollama 고정 버전 설치. 공식 설치 스크립트는 OLLAMA_VERSION으로 버전을 고른다
have=$(ollama -v 2>/dev/null | grep -o '[0-9][0-9.]*' | tail -1 || true)
if [ "$have" != "$GPU_OLLAMA_INSTALL_VERSION" ]; then
  curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION="$GPU_OLLAMA_INSTALL_VERSION" sh
fi
# 설치 스크립트가 systemd 서비스를 띄웠으면 멈춘다 — 환경 변수(NUM_PARALLEL · 127.0.0.1)를 정해 직접 띄운다
if command -v systemctl >/dev/null && systemctl is-active --quiet ollama 2>/dev/null; then
  $SUDO systemctl stop ollama && $SUDO systemctl disable ollama >/dev/null 2>&1 || true
fi
ollama_start 1
ver=$(curl -fs "$OLLAMA_BASE_URL/api/version" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["version"])')
[ -z "$OLLAMA_VERSION" ] || [ "$ver" = "$OLLAMA_VERSION" ] || die "ollama $ver — 고정값 $OLLAMA_VERSION 과 다르다. 설치 버전을 확인한다"

# 4) 모델 받기(약 4.8GB) → digest 확인
ollama pull "$EXAONE_MODEL"
tool health >/dev/null || die "고정값과 다르거나 모델이 없다: $(tool health). 진행 여부는 사용자가 정한다(scripts/gpu/README.md 4절)"

# 5) GPU에 올리고 적재 비율 확인. 일부만 올라가면 CPU로 넘쳐 느려지고 CPU 수치와 섞인다
curl -fs "$OLLAMA_BASE_URL/api/generate" -d "{\"model\":\"$EXAONE_MODEL\",\"keep_alive\":\"$OLLAMA_KEEP_ALIVE_GPU\"}" >/dev/null
res=$(tool resident) || { [ "${GPU_ALLOW_CPU:-}" = 1 ] || die "모델이 GPU에 다 올라가지 않았다: $res (nvidia-smi · $RUN_DIR/ollama.log 확인)"; }
say "준비 완료 · ollama $ver · $res"
tool hwinfo --out "$RUN_DIR/env_setup.md" --run-dir "$RUN_DIR"
say "다음: tmux 안에서 bash scripts/gpu/run_all.sh --quick (5분 점검) → bash scripts/gpu/run_all.sh"
