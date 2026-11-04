#!/usr/bin/env bash
# 빌린 GPU 상자에서 실행: 측정 묶음을 순서대로 한 번에 돌린다. setup.sh 다음에, 끊겨도 계속 돌도록 tmux 안에서 실행한다.
#   bash scripts/gpu/run_all.sh --quick            5분 점검: 벤치 소량 · dev3 분류 · 명령 v2. 이상 없으면 전체를 돌린다
#   bash scripts/gpu/run_all.sh                    전체(봉인 세트 test3 제외)
#   bash scripts/gpu/run_all.sh --with-parallel2   + OLLAMA_NUM_PARALLEL=2로 번갈아 부르기 다시 재기(캐시 칸 2개 안)
#   CONFIRM_TEST3=test3-once bash scripts/gpu/run_all.sh --only-test3   최종 버전으로 봉인 세트 test3만 1회 (마지막에 한 번만)
#   (--unseal-test3: 전체 뒤에 test3까지 · --skip-bench · --skip-all-exaone: 해당 단계 빼기)
#   GPU_DRY_RUN=1 bash scripts/gpu/run_all.sh ...   실행 없이 명령만 출력(서버에서 흐름 확인용)
# 결과: eval/reports/gpu_<시각>/ — env.md(하드웨어) · stages.tsv · logs/ · 보고서 · 모델 출력 캐시 · summary.md, 그리고 같은 이름 .tgz
set -uo pipefail
. "$(dirname "$0")/env.sh"
DRY=${GPU_DRY_RUN:-}
QUICK= P2= T3= SKIP_BENCH= SKIP_ALL= ONLY_T3=
for x in "$@"; do
  case "$x" in
    --quick) QUICK=1 ;; --with-parallel2) P2=1 ;; --unseal-test3) T3=1 ;; --skip-bench) SKIP_BENCH=1 ;; --skip-all-exaone) SKIP_ALL=1 ;;
    --only-test3) T3=1 ONLY_T3=1 ;;
    *) sed -n 2,9p "$0"; exit 2 ;;
  esac
done
[ -n "$DRY" ] || guard_gpu_box
cd "$ROOT"
OUT="eval/reports/gpu_$(date +%Y%m%d_%H%M)${QUICK:+_quick}${ONLY_T3:+_test3}"
mkdir -p "$OUT/logs"
HW="$OUT/hw.txt"

# 단계마다 시작 · 끝 · 종료 코드를 남기고 실패해도 다음 단계로 간다(빌린 시간 안에 최대한 많이 잰다)
stage() {
  local name=$1; shift
  if [ -n "$DRY" ]; then echo "+ [$name] $*"; return 0; fi
  say "▶ $name"
  local t0=$SECONDS
  "$@" > >(tee "$OUT/logs/$name.log") 2>&1
  local rc=$?
  printf '%s\t%s\t%s\n' "$name" "$([ $rc -eq 0 ] && echo ok || echo "실패($rc)")" "$((SECONDS - t0))" >>"$OUT/stages.tsv"
  [ $rc -eq 0 ] || say "✗ $name 실패($rc) — logs/$name.log"
  return 0
}
stamp() { [ -n "$DRY" ] || [ ! -f "$1" ] || tool stamp "$1" "$HW"; }

# 분류 채점: 결과 · 보고서 · 모델 출력 캐시가 모두 $OUT에 남는다(run_dummy --out)
classify_set() {  # $1 세트 $2 이름 꼬리(예: _all) — 나머지 환경 변수는 호출하는 쪽이 정한다
  "$PY" eval/runners/run_dummy.py --set "$1" --llm --out "$OUT/predictions_${1}${2:-}_llm.json"
}
# 명령 채점: 실행기가 eval/reports/에 고정 이름으로 쓰므로 표시 파일 뒤에 새로 생긴 보고서를 옮긴다
commands_set() {
  local mark="$OUT/.mark_$1"; : >"$mark"; sleep 1
  "$PY" eval/runners/run_agent_commands.py --llm --dataset "eval/datasets/$1.jsonl" || return $?
  local rep; rep=$(find eval/reports -maxdepth 1 -name '*_llm.md' -newer "$mark" | head -1)
  [ -n "$rep" ] && cp "$rep" "$OUT/$1_llm.md" && stamp "$OUT/$1_llm.md"
}
bench() {  # $1 이름 나머지 bench_latency 인자
  local name=$1; shift
  "$PY" eval/runners/bench_latency.py --out "$OUT/$name.md" "$@" && stamp "$OUT/$name.md"
}

# 0) 사전 확인 · 하드웨어 기록 · GPU 상태 기록(1.7배 느려졌던 PC 발열 같은 문제를 GPU 클럭 · 온도로 확인)
if [ -z "$DRY" ]; then
  [ -f "$RUN_DIR/ollama.pid" ] && kill -0 "$(cat "$RUN_DIR/ollama.pid")" 2>/dev/null || ollama_start 1
  tool health >/dev/null || die "엑사원 준비 안 됨: $(tool health)"
  curl -fs "$OLLAMA_BASE_URL/api/generate" -d "{\"model\":\"$EXAONE_MODEL\",\"keep_alive\":\"$OLLAMA_KEEP_ALIVE_GPU\"}" >/dev/null
  tool resident >/dev/null || [ "${GPU_ALLOW_CPU:-}" = 1 ] || die "모델이 GPU에 다 올라가지 않았다: $(tool resident)"
  tool hwinfo --out "$OUT/env.md" --line "$HW" --run-dir "$RUN_DIR" >/dev/null
  cp GPU_BUNDLE.txt "$OUT/" 2>/dev/null || say "GPU_BUNDLE.txt 없음 — pack.sh 묶음이 아니면 어떤 코드로 쟀는지 따로 적는다"
  nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.sm \
    --format=csv -l 5 >"$OUT/gpu_monitor.csv" 2>/dev/null &
  MON=$!
  trap 'kill $MON 2>/dev/null' EXIT
fi

# 1) 워밍업: 클럭이 오르고 커널이 준비된 뒤에 잰다(버림)
if [ -n "$ONLY_T3" ]; then SKIP_BENCH=1 SKIP_ALL=1; fi
stage warmup bench warmup --set dev3 --n 3 --m 0 --k 0 --scenarios classify-warm --label "워밍업(버림)"

# 2) 응답 시간 벤치 (NUM_PARALLEL=1): 평소 · 명령 · 번갈아(캐시 미적중) · 모델 로딩
if [ -z "$SKIP_BENCH" ]; then
  if [ -n "$QUICK" ]; then stage bench_p1 bench bench_p1 --set dev3 --n 5 --m 5 --k 3 --label "NUM_PARALLEL=1 (quick)"
  else stage bench_p1 bench bench_p1 --set dev3 --n 20 --m 20 --k 10 --label "NUM_PARALLEL=1"; fi
fi

# 3) 메일 분류 · 엑사원(라우터 기준 그대로). test는 버전마다 1회 재는 세트 — 오답 목록은 보지 않는다
for s in $([ -n "$ONLY_T3" ] || { [ -n "$QUICK" ] && echo dev3 || echo dev dev2 dev3 test; }); do
  stage "classify_$s" classify_set "$s"
  stamp "$OUT/eval_report_predictions_${s}_llm.md"
done

# 4) 명령 해석 · 엑사원. v4(100문장)는 아직 없으면 건너뛴다
for d in $([ -n "$ONLY_T3" ] || { [ -n "$QUICK" ] && echo agent_commands_v2 || echo agent_commands_v1 agent_commands_v2 agent_commands_v4; }); do
  if [ -f "eval/datasets/$d.jsonl" ]; then stage "commands_${d#agent_commands_}" commands_set "$d"; else say "$d.jsonl 없음 — 건너뜀"; fi
done

# 5) 전부 엑사원(라우터 기준 1.0): 빠르면 라우터가 아직 필요한지 판단용. 라우터 정책은 개발 세트로만 고른다(test 제외)
if [ -z "$QUICK" ] && [ -z "$SKIP_ALL" ]; then
  for s in dev dev2 dev3; do
    stage "classify_${s}_all" env ROUTER_THRESHOLD=1.0 "$PY" eval/runners/run_dummy.py --set "$s" --llm --out "$OUT/predictions_${s}_all_llm.json"
    stamp "$OUT/eval_report_predictions_${s}_all_llm.md"
  done
fi

# 6) (선택) NUM_PARALLEL=2: 분류 · 명령 시스템 프롬프트가 캐시 칸을 하나씩 쓰면 번갈아 불러도 미적중이 없어지는지
if [ -n "$P2" ]; then
  if [ -z "$DRY" ]; then ollama_start 2; tool hwinfo --out "$OUT/env_p2.md" --run-dir "$RUN_DIR" >/dev/null; fi
  stage bench_p2 bench bench_p2 --set dev3 --n 0 --m 0 --k 10 --scenarios alternate --label "NUM_PARALLEL=2"
  if [ -z "$DRY" ]; then ollama_start 1; fi  # 이후 단계(test3)는 다시 기본 조건으로
fi

# 7) (선택) 봉인 세트 test3: 최종 버전으로 단 1회. 오답 목록을 보고 규칙 · 프롬프트를 고치면 test3는 개발 세트가 된다
if [ -n "$T3" ]; then
  if ls eval/reports/gpu_*/predictions_test3_llm.json >/dev/null 2>&1 && [ "${FORCE_TEST3:-}" != 1 ]; then
    say "test3는 이미 채점했다(eval/reports/gpu_*/predictions_test3_llm.json) — 건너뜀. 다시 재야 하면 FORCE_TEST3=1 (보고에 2회째라고 적는다)"
  else
    ans=${CONFIRM_TEST3:-}
    if [ "$ans" != test3-once ] && [ -t 0 ] && [ -z "$DRY" ]; then
      read -r -p "봉인 세트 test3를 채점한다. 최종 버전이고 처음이면 test3-once 입력: " ans
    fi
    if [ "$ans" = test3-once ] || [ -n "$DRY" ]; then
      stage classify_test3 classify_set test3
      stamp "$OUT/eval_report_predictions_test3_llm.md"
    else
      say "확인 문구가 없어 test3를 건너뜀"
    fi
  fi
fi

# 8) CPU 출력과 비교(같은 프롬프트일 때만 의미 있음) · 요약 · 묶기
if [ -z "$DRY" ]; then
  for c in eval/reports/cpu_baseline/llm_cache_predictions_*llm.json; do
    [ -f "$c" ] || continue
    s=$(basename "$c" .json); s=${s#llm_cache_predictions_}; s=${s%llm}; s=${s%_}; s=${s:-dev}
    g="$OUT/llm_cache_predictions_${s}_llm.json"
    [ -f "$g" ] && tool compare "$c" "$g" --out "$OUT/compare.md" >/dev/null
  done
  tool summary "$OUT" >/dev/null
  rm -f "$OUT"/.mark_*
  tar czf "$OUT.tgz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
  say "끝: $OUT/summary.md · 서버로 가져갈 파일 $OUT.tgz"
else
  echo "+ compare · summary · tar → $OUT.tgz"
  rmdir "$OUT/logs" "$OUT" 2>/dev/null || true
fi
