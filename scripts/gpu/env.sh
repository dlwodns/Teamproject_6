# GPU 상자 공용 설정. setup.sh · run_all.sh가 source 한다(직접 실행하지 않는다).
# 모델 태그 · 고정값(digest · ollama 버전) · 제한 시간은 scripts/exaone-pc.env 한 곳을 따른다 — CPU(PC) 수치와 같은 조건으로 비교하려고.
# 다른 점은 하나: PC 터널(Unix 소켓) 대신 같은 상자의 ollama를 127.0.0.1 TCP로 부른다.

GPU_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$GPU_DIR/../.." && pwd)
PY="$ROOT/ai/.venv/bin/python"
RUN_DIR="$ROOT/.gpu_run"  # ollama 로그 · pid. 빌린 상자 안에만 생긴다

set -a
# shellcheck source=../exaone-pc.env
. "$ROOT/scripts/exaone-pc.env"
set +a

GPU_OLLAMA_INSTALL_VERSION=${OLLAMA_VERSION:-0.34.0}  # 설치할 ollama 버전 = 고정값
OLLAMA_UDS=
OLLAMA_BASE_URL="http://127.0.0.1:${GPU_OLLAMA_PORT:-11434}"
export OLLAMA_UDS OLLAMA_BASE_URL

# 고정값과 다른 모델 · 버전으로라도 돌릴지는 사용자가 정한다. 1이면 고정값 확인을 끄고 env.md에 경고를 남긴다
if [ "${GPU_ALLOW_UNPINNED:-}" = 1 ]; then
  EXAONE_MODEL_DIGEST= OLLAMA_VERSION=
  export EXAONE_MODEL_DIGEST OLLAMA_VERSION
fi

die() { echo "gpu: $*" >&2; exit 1; }
say() { echo "gpu: $*" >&2; }
SUDO=$([ "$(id -u)" -eq 0 ] || echo sudo)

# 서버(dev-server-02, 메모리 한도 5GiB)에서 ollama · 7.8B를 띄우면 VS Code Remote까지 끊긴다(AI-T4). GPU가 보이는 상자에서만 실행한다
guard_gpu_box() {
  [ "$(hostname)" != dev-server-02 ] || die "dev-server-02(서버)에서는 실행하지 않는다. 빌린 GPU 상자에서 실행한다"
  command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1 || die "NVIDIA GPU가 보이지 않는다(nvidia-smi 실패)"
}

tool() { "$PY" "$GPU_DIR/gpu_tool.py" "$@"; }
OLLAMA_KEEP_ALIVE_GPU=${OLLAMA_KEEP_ALIVE:-30m}  # ai 서비스 기본(config.py)과 같다
GPU_CONTEXT_LENGTH=${GPU_CONTEXT_LENGTH:-4096}  # PC 실측(11/3 /api/ps context_length 4096). 문맥 길이가 다르면 비교 조건이 달라진다

# 우리가 띄운 ollama serve만 다룬다(systemd 서비스가 있으면 setup.sh가 멈춰 둔다)
ollama_start() {  # $1 = OLLAMA_NUM_PARALLEL
  mkdir -p "$RUN_DIR"
  ollama_stop
  # 공개 IP가 붙은 상자라도 밖에서 못 부르게 127.0.0.1에만 묶는다. 문맥 길이는 비우면 ollama 기본(PC와 맞추려면 PC 값을 넣는다)
  env OLLAMA_HOST="127.0.0.1:${GPU_OLLAMA_PORT:-11434}" OLLAMA_NUM_PARALLEL="${1:-1}" OLLAMA_KEEP_ALIVE="$OLLAMA_KEEP_ALIVE_GPU" \
    ${GPU_CONTEXT_LENGTH:+OLLAMA_CONTEXT_LENGTH=$GPU_CONTEXT_LENGTH} ${OLLAMA_MODELS:+OLLAMA_MODELS=$OLLAMA_MODELS} \
    nohup ollama serve >>"$RUN_DIR/ollama.log" 2>&1 &
  echo $! >"$RUN_DIR/ollama.pid"
  echo "${1:-1}" >"$RUN_DIR/num_parallel"
  for _ in $(seq 60); do
    curl -fs "$OLLAMA_BASE_URL/api/version" >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "ollama serve가 60초 안에 뜨지 않았다($RUN_DIR/ollama.log)"
}

ollama_stop() {
  if [ -f "$RUN_DIR/ollama.pid" ] && kill -0 "$(cat "$RUN_DIR/ollama.pid")" 2>/dev/null; then
    kill "$(cat "$RUN_DIR/ollama.pid")"
    for _ in $(seq 20); do kill -0 "$(cat "$RUN_DIR/ollama.pid")" 2>/dev/null || break; sleep 0.5; done
  fi
  rm -f "$RUN_DIR/ollama.pid"
}
