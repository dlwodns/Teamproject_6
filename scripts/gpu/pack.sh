#!/usr/bin/env bash
# 서버에서 실행: 빌린 GPU 상자로 보낼 묶음(.tgz)을 만든다.
#   scripts/gpu/pack.sh [출력 파일]      기본: ~/gpu_bundle/ax_gpu_<시각>.tgz
# git clone이 아니라 작업 폴더를 묶는다 — 아직 커밋하지 않은 세트(dev3 · test3 · 명령 v2~v4)와 규칙 · 프롬프트 수정까지 그대로 잰다.
# 화이트리스트만 담는다: 코드 · 더미 메일 · 평가 실행기 · 명령 세트. 실명 원본(data/raw) · 메일함 캡처 · .env · docs · PC 터널 스크립트는 넣지 않는다.
# CPU(PC)에서 남긴 모델 출력 캐시(eval/reports/llm_cache_*.json)는 cpu_baseline/으로 넣어 GPU 출력과 같은지 비교한다.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
ts=$(date +%Y%m%d_%H%M)
OUT=${1:-${GPU_BUNDLE_DIR:-$HOME/gpu_bundle}/ax_gpu_$ts.tgz}
mkdir -p "$(dirname "$OUT")"
STAGE=$(dirname "$OUT")/.stage_$ts
mkdir -p "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

PATHS=(ai/app ai/tests ai/pyproject.toml ai/README.md data/dummy eval/runners eval/datasets eval/README.md eval/reports/README.md
       scripts/gpu scripts/exaone-pc.env)
for p in "${PATHS[@]}"; do [ -e "$p" ] || { echo "pack: $p 없음" >&2; exit 1; }; done
mapfile -t CACHES < <(ls eval/reports/llm_cache_*.json 2>/dev/null || true)

FILES=$(find "${PATHS[@]}" -type f -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -not -name '*.pyc' | sort)
{
  echo "# GPU 측정 묶음"
  echo "- 만든 시각: $(date '+%Y-%m-%d %H:%M %Z')"
  echo "- 브랜치: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?') · HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
  echo "- 규칙: $(grep -ho 'RULES_VERSION = "[^"]*"' ai/app/pipeline/rules/*.py ai/app/agent/*.py | sed 's/RULES_VERSION = //' | tr '\n' ' ')"
  echo "- 프롬프트: $(grep -ho 'PROMPT_VERSION = "[^"]*"' ai/app/prompts/*.py | sed 's/PROMPT_VERSION = //' | tr '\n' ' ') · 분류 사용: $(grep -o 'PROMPT = [a-z0-9_]*' ai/app/pipeline/classify.py | head -1)"
  echo "- 커밋 안 된 파일(묶음 범위):"
  git status --porcelain -- "${PATHS[@]}" 2>/dev/null | sed 's/^/  /' || true
  echo "- CPU 출력 캐시: ${#CACHES[@]}개 → eval/reports/cpu_baseline/"
  echo ""
  echo "## sha256"
  # shellcheck disable=SC2086
  sha256sum $FILES
} >"$STAGE/GPU_BUNDLE.txt"

# shellcheck disable=SC2086
tar czf "$OUT" --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' \
  --transform 's,^eval/reports/llm_cache_,eval/reports/cpu_baseline/llm_cache_,' \
  "${PATHS[@]}" "${CACHES[@]}" -C "$STAGE" GPU_BUNDLE.txt
echo "pack: $OUT ($(du -h "$OUT" | cut -f1)) · 파일 $(echo "$FILES" | wc -l)개 + 캐시 ${#CACHES[@]}개"
echo "다음: scp -P <포트> $OUT <사용자>@<GPU 상자>:~/  → scripts/gpu/README.md 2절"
