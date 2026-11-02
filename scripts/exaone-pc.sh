#!/usr/bin/env bash
# PC에서 돌리는 엑사원(ollama)으로 ai 서비스 · 평가를 실행한다. 설정은 scripts/exaone-pc.env 한 곳에 둔다.
#   scripts/exaone-pc.sh check          터널 · 소켓 권한 · 고정값(모델 digest · ollama 버전) 확인
#   scripts/exaone-pc.sh pin            선택(권장): PC에서 읽은 digest · 버전을 exaone-pc.env에 고정값으로 적는다
#   scripts/exaone-pc.sh run <명령...>   확인을 통과하면 설정을 환경 변수로 넣고 명령을 실행한다
# 예) cd ai && ../scripts/exaone-pc.sh run .venv/bin/uvicorn app.main:app --port 8001
#     scripts/exaone-pc.sh run ai/.venv/bin/python eval/runners/run_dummy.py --set test --llm
# PC 쪽은 scripts/pc/exaone-tunnel.ps1 이 터널을 연다.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
ENV_FILE="$HERE/exaone-pc.env"
PY="$ROOT/ai/.venv/bin/python"
die() { echo "exaone-pc: $*" >&2; exit 1; }

mode=${1:-}
case "$mode" in check | pin) ;; run) shift; [ $# -gt 0 ] || die "실행할 명령이 없다" ;; *) sed -n 2,8p "$0"; exit 2 ;; esac

set -a
# shellcheck source=exaone-pc.env
. "$ENV_FILE"
set +a

# 보안: 소켓 폴더가 내 소유 0700이어야 다른 계정이 소켓에 붙거나 가짜 소켓을 심지 못한다
dir=$(dirname "$OLLAMA_UDS")
[ -d "$dir" ] || die "$dir 없음. PC에서 scripts/pc/exaone-tunnel.ps1 을 먼저 실행한다"
[ "$(stat -c '%u %a' "$dir")" = "$(id -u) 700" ] || die "$dir 권한이 $(stat -c '%U %a' "$dir")다. 내 소유 700이어야 한다"
[ -S "$OLLAMA_UDS" ] || die "소켓 없음: PC 터널이 꺼져 있다"
[ "$(stat -c %u "$OLLAMA_UDS")" = "$(id -u)" ] || die "소켓 소유자가 내가 아니다"

# pin은 고정값을 비운 채로 읽어야 PC의 실제 값이 보인다
if [ "$mode" = pin ]; then pins=(EXAONE_MODEL_DIGEST= OLLAMA_VERSION=); else pins=(); fi
health=$(cd "$ROOT/ai" && env "${pins[@]}" "$PY" -c '
import json
from app.core.config import get_settings
from app.llm.client import OllamaClient
print(json.dumps(OllamaClient(get_settings()).health()))')
field() { "$PY" -c 'import json,sys; v=json.loads(sys.argv[1]).get(sys.argv[2]); print("" if v is None else json.dumps(v) if isinstance(v,(list,bool)) else v)' "$health" "$1"; }

[ "$(field reachable)" = true ] || die "터널 끊김(소켓은 있지만 응답 없음): $health"
[ -n "$(field digest)" ] || die "PC ollama에 $EXAONE_MODEL 이 없다. PC에서 ollama pull 한다"

if [ "$mode" = pin ]; then
  digest=$(field digest) version=$(field version)
  for kv in "EXAONE_MODEL_DIGEST=$EXAONE_MODEL_DIGEST:$digest" "OLLAMA_VERSION=$OLLAMA_VERSION:$version"; do
    key=${kv%%=*} rest=${kv#*=} old=${rest%%:*} new=${rest#*:}
    [ -z "$old" ] || [ "$old" = "$new" ] || die "$key 이미 $old 로 고정됨(PC 값 $new). 바꾸려면 exaone-pc.env를 직접 고치고 평가를 다시 돌린다"
    sed -i "s|^$key=.*|$key=$new|" "$ENV_FILE"
  done
  echo "고정: EXAONE_MODEL_DIGEST=$digest · OLLAMA_VERSION=$version ($ENV_FILE)"
  exit 0
fi

# 고정값은 선택이다. 비어 있으면 확인 없이 실행하고, 채워져 있으면 다를 때 멈춘다
if [ -z "$EXAONE_MODEL_DIGEST" ] || [ -z "$OLLAMA_VERSION" ]; then
  echo "exaone-pc: 경고 · 고정값이 비어 있어 모델 · 버전을 확인하지 않는다(PC 값 digest $(field digest | cut -c1-12) · ollama $(field version)). 평가 수치를 남길 때는 scripts/exaone-pc.sh pin 을 권장" >&2
fi
[ "$(field model_ready)" = true ] || die "고정값과 다름 $(field pin_mismatch): PC 값 digest $(field digest) · ollama $(field version)"

echo "exaone-pc: OK · $EXAONE_MODEL · digest $(field digest | cut -c1-12) · ollama $(field version) · $(field latency_ms)ms" >&2
[ "$mode" = run ] && exec "$@"
exit 0
