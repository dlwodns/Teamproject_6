# scripts/gpu · 빌린 NVIDIA GPU에서 최종 측정

> 지금 쓰지 않는다(2026-11-27): 서비스 모델이 엑사원 API(K-EXAONE 2.5)로 바뀌어 로컬 엑사원(ollama 7.8B) · GPU 측정 경로를 쓰지 않는다(D53 11-19 덧붙임, PR #321 · #322). 아래는 11-14 당시 기록으로 남긴다.

PC(CPU) 엑사원은 메일 1통 약 22초(전원 · 발열에 따라 37초), 캐시가 안 맞는 명령 70초다(plan 4.4 · 4.5절). 속도는 노트북 성능 문제라 최종 측정은 GPU를 시간 단위로 빌려 한 번에 끝낸다(미결 #6 판단 근거).

## 1. 방식: GPU 상자 안에서 ollama와 채점을 모두 돌린다

| | (가) 상자 안에서 모두 실행 **← 채택** | (나) 서버에서 SSH 포트 포워딩으로 상자의 ollama 호출 |
|---|---|---|
| 비교 가능성 | 같음 — 모델 태그 · digest `099a498b9cbf` · ollama `0.34.0` 고정값을 `exaone-pc.env`에서 그대로 읽는다 | 같음 |
| 응답 시간 | ollama까지 같은 상자(127.0.0.1)라 순수 모델 시간 | 서버↔상자 왕복이 매 호출에 붙는다. GPU 명령 1건은 1초 안팎 `[추정]`이라 왕복 수십~수백 ms도 10% 넘게 섞인다 |
| 빌린 시간 낭비 | 터널 없음 | 터널이 끊기면 채점이 규칙 결과로 떨어진다(11/3 PC 터널도 끊겼다) |
| 준비 | 묶음 전송 + 파이썬 환경(약 1~2분) | 상자에 ollama만 |
| 데이터 | 코드 · 더미 메일만 화이트리스트로 보낸다(`pack.sh`) | 상자로 가는 것은 프롬프트뿐 |

- 아직 커밋하지 않은 세트(dev3 · test3 · 명령 v2~v4)와 규칙 · 프롬프트 수정까지 재려면 `git clone`이 아니라 작업 폴더를 묶어야 한다 → `pack.sh`. 묶음의 `GPU_BUNDLE.txt`에 HEAD · 커밋 안 된 파일 · 파일별 sha256을 남긴다.
- (나)가 필요하면: `ssh -N -L 11435:127.0.0.1:11434 <상자>` 후 서버에서 `GPU_OLLAMA_PORT=11435 bash -c '. scripts/gpu/env.sh; ai/.venv/bin/python eval/runners/run_dummy.py --set dev3 --llm'`. 응답 시간에는 왕복이 섞인다고 보고서에 적는다.

## 2. 사용 순서 (복사해 붙이기)

```bash
# ── 서버(dev-server-02) ── 묶음 만들기. 서버에서는 ollama · 모델을 띄우지 않는다(setup.sh · run_all.sh는 여기서 멈춘다)
scripts/gpu/pack.sh                                   # → ~/gpu_bundle/ax_gpu_<시각>.tgz
scp -P <포트> ~/gpu_bundle/ax_gpu_<시각>.tgz <사용자>@<상자>:~/

# ── GPU 상자 ──
mkdir -p ~/ax && tar xzf ~/ax_gpu_*.tgz -C ~/ax && cd ~/ax
bash scripts/gpu/setup.sh                             # ollama 0.34.0 · 모델 4.8GB · ai/.venv · digest · GPU 적재 확인 (10~15분)
tmux new -s ax                                        # SSH가 끊겨도 계속 돈다
bash scripts/gpu/run_all.sh --quick                   # 5분 점검. summary.md에 실패 · 0건 없는지 본다
bash scripts/gpu/run_all.sh --with-parallel2          # 전체(test3 제외) + NUM_PARALLEL=2 비교 (약 25분)
# 최종 버전이 확정됐을 때만, 단 1회:
CONFIRM_TEST3=test3-once bash scripts/gpu/run_all.sh --only-test3

# ── 서버로 가져오기 ──
scp -P <포트> <사용자>@<상자>:~/ax/eval/reports/gpu_*.tgz eval/reports/ && tar xzf eval/reports/gpu_<시각>.tgz -C eval/reports/
```

- `--only-test3`는 워밍업 뒤 test3만 잰다. 전체 측정과 한 번에 하려면 `--unseal-test3`(같은 확인 문구 필요). 이미 잰 기록(`eval/reports/gpu_*/predictions_test3_llm.json`)이 있으면 건너뛴다.
- 같은 CPU 조건 벤치(나란히 비교용, PC 켜 둔 상태에서 약 15분): `scripts/exaone-pc.sh run ai/.venv/bin/python eval/runners/bench_latency.py --set dev3 --n 10 --m 10 --k 5 --out eval/reports/bench_cpu.md`

## 3. 무엇을 재나 (`run_all.sh`)

| 순서 | 단계 | 내용 | 호출 수 | GPU 예상 `[추정 3초/통 · 명령 1초]` |
|---|---|---|---|---|
| 0 | 사전 확인 | 연결 · 고정값 · GPU 적재 100% · 하드웨어 기록(`env.md`) · `nvidia-smi` 5초 간격 기록(`gpu_monitor.csv`, 클럭 · 온도) | — | — |
| 1 | 워밍업 | 분류 3통(버림) | 3 | 10초 |
| 2 | 벤치 NUM_PARALLEL=1 | 분류 캐시 적중 20 · 명령 20 · **분류↔명령 번갈아 10왕복(캐시 미적중, CPU 70초 상황)** · 모델 내린 뒤 첫 호출 | 약 61 | 2~3분 |
| 3 | 분류 · 엑사원 | dev · dev2 · dev3 · test, 라우터 0.8 | 17+20+22+23 = 82 | 약 4분 |
| 4 | 명령 · 엑사원 | v1 · v2 · v4(없으면 건너뜀). 규칙 경로는 0.1ms | 모델 경로 약 1+48+40 | 약 2분 |
| 5 | 전부 엑사원 | 라우터 1.0, dev · dev2 · dev3만(라우터 정책은 개발 세트로 고른다) | 100+47+60 = 207 | 약 10분 |
| 6 | (선택) NUM_PARALLEL=2 | ollama 재시작 후 번갈아 10왕복 | 20 | 약 2분 |
| 7 | (선택) test3 | 봉인 세트 1회. 확인 문구 · 이미 잰 기록이 있으면 건너뜀 | 약 22 | 약 1분 |
| 8 | 정리 | CPU 출력 캐시와 같은지 비교(`compare.md`) · `summary.md` · `.tgz` | — | — |

- 합계 약 480호출 · 25분 + 준비 10~15분 ≈ 40분. **1시간 빌리면 되고, 다시 돌릴 여유까지 2시간.** GPU가 5초/통으로 느려도 1시간 안이다.
- 사양: VRAM 8GB 이상(7.8B Q4_K_M 약 4.8GB + 문맥 캐시), NUM_PARALLEL=2 · 긴 문맥까지 보면 12GB 이상 권장. 디스크 15GB 이상, root 또는 sudo, ollama.com · huggingface.co · github · pypi 접속. GPU 종류 · 시간당 가격은 `[확인 필요]`(자주 바뀐다). ollama 0.34.0이 요구하는 드라이버 버전 `[확인 필요]`.

## 4. 고정값(digest · ollama 버전)이 다를 때

`setup.sh`가 멈춘다. 값을 고쳐 넘기지 않는다 — 진행 여부는 사용자가 정한다. 진행하면 `GPU_ALLOW_UNPINNED=1 bash scripts/gpu/run_all.sh ...`로 돌리고, `env.md`에 '고정값 확인 끔 — CPU 수치와 직접 비교 불가'가 남는다. digest가 다르면 HF 모델 파일이 바뀐 것이라 정확도 비교도 다시 해야 한다.

## 5. 체크리스트

- [ ] 빌리기 전: 측정할 규칙 · 프롬프트 버전이 정해졌다(빌린 뒤에 고치지 않는다). `pack.sh`를 그 상태에서 만든다
- [x] PC 문맥 길이: 11/3 PC `/api/ps` context_length 4096 → `env.sh` 기본값 `GPU_CONTEXT_LENGTH=4096`(PC 값이 바뀌면 다시 확인)
- [ ] 상자: NVIDIA GPU · VRAM 8GB+ · 디스크 15GB+ · root/sudo
- [ ] `setup.sh` 끝 줄이 '준비 완료 · ollama 0.34.0 · gpu_ratio 1.0'
- [ ] `--quick`의 `summary.md`: 호출 실패 0 · JSON 오류 0 · 엑사원행이 CPU와 같은 수(dev3 22)
- [ ] 전체 실행 중 `gpu_monitor.csv`의 클럭 · 온도가 안정적(스로틀이면 수치에 적는다)
- [ ] 결과 `.tgz`를 서버로 가져왔다 · 상자와 디스크(볼륨)를 지웠다
- [ ] plan 표에는 CPU 수치와 나란히, 하드웨어 · 버전과 함께 적는다

## 6. 주의

- **정확도도 다시 잰다.** temperature 0이어도 GPU 연산 순서가 달라 출력 글자가 CPU와 다를 수 있다. `compare.md`가 같은 프롬프트끼리 출력이 같은지 센다(프롬프트 · 규칙이 CPU 캐시 이후 바뀌었으면 겹침 0 — 그때는 보고서 수치로만 비교).
- **테스트셋**: test는 버전마다 1회 재는 세트, test3는 최종 1회 봉인 세트다. 오답 목록을 보고 규칙 · 프롬프트를 고치지 않는다. 라우터 1.0(전부 엑사원)은 개발 세트로만 돈다.
- **조건 고정**: 양자화 · 문맥 길이 · flash attention 같은 ollama 설정은 바꾸지 않는다. 기본 NUM_PARALLEL=1(PC와 같다고 본 값 `[확인 필요]`), 2는 6단계에서 따로 잰다.
- **워밍업**: 첫 몇 통은 클럭 · 커널 준비가 섞여 버린다. 다른 작업을 같이 돌리지 않는다.
- **보안**: 상자에는 코드 · 더미 메일만 간다(실명 원본 `data/raw` · 메일함 캡처 · `.env` · docs 제외). ollama는 127.0.0.1에만 묶는다. 끝나면 상자를 지운다.
- 서버(dev-server-02)에서 `setup.sh` · `run_all.sh`는 시작하자마자 멈춘다(메모리 5GiB, AI-T4). 흐름만 보려면 `GPU_DRY_RUN=1`.

## 파일

| 파일 | 어디서 | 내용 |
|---|---|---|
| `pack.sh` | 서버 | 화이트리스트 묶음 + `GPU_BUNDLE.txt`(HEAD · 커밋 안 된 파일 · sha256) + CPU 출력 캐시 |
| `env.sh` | 상자 | 공용 설정. `exaone-pc.env`의 모델 · 고정값을 읽고 TCP 127.0.0.1로 바꾼다. ollama 띄우기/내리기 |
| `setup.sh` | 상자 | uv · 파이썬 3.12 · ai/.venv · ollama 0.34.0 · 모델 · digest · GPU 적재 확인 |
| `run_all.sh` | 상자 | 측정 묶음(3절). `--quick` · `--with-parallel2` · `--unseal-test3` · `--only-test3` · `--skip-bench` · `--skip-all-exaone` |
| `gpu_tool.py` | 상자 | health · resident · hwinfo · stamp · compare · summary |
| `../../eval/runners/bench_latency.py` | 어디서나 | 응답 시간 벤치(캐시 적중 · 미적중 · 로딩). PC에서도 같은 명령으로 잰다. `--fake`로 모델 없이 확인 |
