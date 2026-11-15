# 에이전트 시나리오 평가 (PL-16 5.5절)

명령 평가(봉인 v1~v4)는 문장 하나를 어떤 행동으로 해석했는지만 본다. 이 평가는 **여러 번 주고받은 뒤 데이터가 원하는 상태가 됐는지**로 잰다. 피클이 포크해 쓰는 tau2-bench의 채점 방식을 우리 규모로 줄인 것이다.

- 한 시나리오 = 처음 상태(`fixture`) + 순서대로 보내는 요청(`steps`) + 기대 최종 상태(`final`).
- 채점은 두 가지다. 최종 상태가 모두 맞는가, 금지 행동(발송 등)이 0건인가.
- HTTP만 쓰므로 테스트와 실제 서버(시연 · 배포)에 같은 시나리오를 돌린다. 계약은 `docs/30_backend/agent_api_contract.md`.

## 돌리는 법

```bash
# 테스트로 (서버 없이, backend CI와 같이 돈다)
cd backend && .venv/bin/python -m pytest -q tests/test_scenarios.py

# 실제 서버에 (load가 테이블을 지우므로 시나리오 전용 DB로 띄운다. ax.db · demo.db에서는 개발 경로가 꺼져 있다)
cd backend && APP_MODE=dev DATABASE_URL=sqlite:///./scenario.db .venv/bin/uvicorn app.main:app --port 8000
backend/.venv/bin/python eval/scenarios/run_scenarios.py --base-url http://localhost:8000
```

## 지금 있는 시나리오 (11/11, 11개 중 최종 상태 일치 11 · 금지 행동 0)

| id | 확인하는 것 |
|---|---|
| SC-01 | 기한 임박 카드 [완료] → 기록 → 실행 취소 → 카드 복귀 |
| SC-02 | 상급자 + 기한 지남이면 카드 한 장(기한 지남)만 |
| SC-03 | 임박 카드를 숨겨도 기한이 지나면 기한 지남 카드가 뜸 |
| SC-04 | [나중에] → 카드 사라짐 → 그 시각 지나면 다시 뜸 |
| SC-05 | 아침 요약은 제안 카드가 아니라 아침 브리핑(BE-12) |
| SC-06 | 답 없음은 보낸 요청 한 통에 하나, 답 온 요청 · 내 답장 · 기준일 전 메일 제외 |
| SC-07 | 상급자 표시 끄기 → 상급자 카드 사라짐 → 실행 취소로 복귀 |
| SC-08 | 중요한 사람 표시(T11 결과) 바꾸기 → 되돌리기 → 다시 하기, 화면의 '읽는 곳'(used_by) |
| SC-09 | 여러 건 완료 미리보기가 기록 맨 위, 확인 뒤 대상 바꿔치기 422 |
| SC-10 | 조회만 반복하면 아무것도 안 바뀜(S1), [업무 아님]과 되돌리기 |
| SC-11 | 메일 기억하기: 기본 켜짐 확인 → 끄면 안 배움 → 켜면 서명에서 상급자 · 받는 사람에서 배포 목록 → 되돌리면 다시 안 배움 |

## 아직 못 만드는 시나리오

계획(PL-16 5.5절)의 12개 중 아래는 backend에 해당 경로가 생기면 더한다.

- T15 일정 등록 되묻기(시각 없음 · 상대 시점) 2개, 업무 아님과 자동 일정 함께 빼기 1개 — T15 backend(11/21)
- 말로 시킨 지시, "회신 초안 쓰고 내일 10시 회의 잡아줘" 섞인 지시 — 에이전트 실행기(BE-11)
- 메일 속 지시는 명령이 아님(S2) · 발송은 항상 확인(S3) — BE-11 · 발송(T14)

## 시나리오 파일 형식

`cases/_base.json`이 공통 처음 상태다. 시나리오의 `"fixture": {"base": true, ...}`는 공통 상태에 목록을 이어 붙인다.

```json
{"id": "SC-xx", "title": "…",
 "fixture": {"base": true, "mails": [...], "tasks": [...]},
 "steps": [
   {"do": "GET /api/suggestions", "expect": {"match": {"suggestions.0.rule": "due_soon"}, "len": {"suggestions": 1}},
    "save": {"via": "suggestions.0.via"}},
   {"do": "PATCH /api/tasks/1", "body": {"status": "done", "via": "${via}"}, "save": {"aid": "action_id"}},
   {"clock": "2026-11-11T18:00:00+09:00"},
   {"do": "POST /api/actions/${aid}/undo", "expect": {"status": 200}}
 ],
 "final": {"tasks": {"1": "pending"}, "log_count": 2, "live_count": 0}}
```

- `expect`: `status`(기본 200) · `match`(경로 = 값) · `len`(경로 = 개수) · `contains` · `not_contains`. 경로는 `a.0.b`, 목록 전체는 `items[*].state`.
- `final`: `tasks` · `log_count` · `live_count`(되돌리지 않은 기록) · `vias` · `contacts` · `unused_previews` · `hide_count` · `preview_count` · `forbidden_actions`.
- 모르는 칸(오타)은 실패로 처리한다. 경로가 없으면 `not_contains`도 실패다(거짓 통과 방지).
- 금지 행동은 발송(T12 · T14 실행)을 늘 포함한다. 지금 backend에는 발송 경로가 없어 이 값은 0이 정상이고, 조회가 아무것도 쓰지 않는지는 `log_count` · `hide_count` · `preview_count`로 본다.
