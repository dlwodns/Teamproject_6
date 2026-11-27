# 에이전트 패널 API 계약 — 제안 카드 · 기록 탭 · 에이전트가 아는 것 (2026-11-11)

> 상태: 구현 완료(FastAPI) · 팀 리뷰 대기 · 작성: 문규남 · 작업 번호: PL-16 · 갱신: 2026-11-27 (backend 라우터와 대조: 3절 표에 빠진 경로 더함 · 세션 인증 · T01 · T06 준비됨 · 개인정보 가리기 반영) / 11-14 (홍태겸: #60 본문의 어긋남 4가지 — 기본값 · 예시 칸 · BE-11 문장 · 확인 기다림 줄 문구) · 근거: D50(제안 카드) · `docs/10_planning/agent_pickle_plan.md`(PL-16 명세, docs/PL-16 브랜치)
> 이 문서의 목적: 프런트엔드가 붙을 형식을 고정한다. 백엔드는 FastAPI다(D38 · BE-D1). 형식을 바꾸면 이 문서와 `eval/scenarios/`를 함께 고친다.

## 1. 원칙

1. **형식은 이 문서가 기준이다.** 경로 · 요청 · 응답 · 오류 코드를 바꾸면 이 문서와 시나리오를 함께 고친다.
2. **판단 규칙은 문장으로 적었다**(4절). 기획 리뷰는 코드가 아니라 이 표로 한다.
3. **계약 시험은 HTTP만 쓴다.** `eval/scenarios/`의 시나리오 10개는 테스트에서도, 시연 · 배포 서버에서도 주소만 바꿔 돌린다.
4. **사용자 찾기는 한 함수에 모았다.** 개발 · 테스트는 `X-User-Id` 헤더다. 로그인을 붙일 때 이 부분만 바꾼다(BE-D16). 11-25: 공개 배포용 브라우저 세션(`AUTH_MODE=session`, D58)을 같은 함수(`app/core/user.py`)에 붙였다.

## 2. 공통 규칙

| 항목 | 규칙 |
|---|---|
| 사용자 | (BE-D16) 이 문서의 **모든 경로**(BE-4 업무 경로 포함)는 `X-User-Id` 헤더(1 ~ 2^63-1)로 사용자를 정한다. 헤더가 없으면 개발 모드에서만 1번 사용자, 운영 모드는 401. 헤더의 사용자가 DB에 없으면 401. `AUTH_MODE=session`(공개 배포, 11-25)이면 헤더는 보지 않고 httpOnly 쿠키 `cne_session`의 사용자다. 쿠키가 없거나 모르는 세션이면 401 |
| 남의 것 | 다른 사용자의 업무 · 기록 · 미리보기 · 연락처를 가리키면 404(있는지도 알려 주지 않는다) |
| id | 경로의 id는 1 ~ 2^63-1(Java long 범위). 넘으면 422 |
| 시각 | 응답 시각은 모두 `YYYY-MM-DDTHH:MM:SS+09:00`(KST, 초까지, D47). 요청 시각은 날짜와 시각이 함께 있는 ISO 문자열만 받는다. 시간대가 없으면 KST로 본다. 숫자(epoch) · 날짜만 있는 값은 422 |
| 오류 | 없는 대상 404 · 순서가 꼬여 못 함(되돌리기 막힘 · 이미 실행 · 기록 밖에서 바뀜) 409 · 형식 오류 422 · 사용자 없음 401 |
| 오류 본문 | `{"detail": …}`. 직접 낸 오류는 문장 하나, 형식 오류(422)는 칸별 목록이다. 프런트엔드는 **상태 코드로만** 판단하고 `detail`은 개발용으로만 본다 |
| 모르는 칸 | 쓰기 요청 본문에 정의되지 않은 칸이 오면 422(오타가 조용히 빠지지 않게) |
| 바뀐 것 없음 | 같은 값으로 바꾸면 기록을 남기지 않고 `action_id: null` |
| 조회는 쓰지 않는다 | `GET`은 어떤 행도 쓰지 않는다(PL-16 S1). 카드를 계산하다가 행동을 실행하는 경로가 없어야 한다 |
| 기록과 변경은 한 트랜잭션 | 상태 · 기억을 바꾸는 요청은 바꾸기와 `action_log` 한 줄을 같은 트랜잭션에서 한다. 기록이 실패하면 바꾸기도 없다(S5) |

## 3. 엔드포인트

| 메서드 · 경로 | 하는 일 | 쓰기 |
|---|---|---|
| `GET /api/suggestions?limit=3` | 지금 띄울 제안 카드. 앞에서 `limit`장(1~50)과 접힌 수 | 없음 |
| `POST /api/suggestions/{key}/hide` | [이 제안 숨기기]. 다음 R-아침 시각까지(1시간도 안 남았으면 그다음 날, 확정). 응답 `{"key": …, "hidden_until": "…+09:00"}` | `suggestion_hides` |
| `PATCH /api/tasks/{id}` | (기존 BE-4) 카드 버튼 [완료] · [나중에] · [업무 아님]도 이것을 부른다. 본문에 카드의 `via`를 넣는다 | `tasks` · `action_log` |
| `POST /api/tasks/bulk/preview` · `POST /api/actions/execute` | (기존 BE-4) 여러 건 변경. `execute`는 `preview_id`와 `task_ids?`(확인 카드에서 체크한 업무, UX-D8 · #31)만 받는다. `task_ids`는 미리보기 대상 안에서 1건 이상 줄이기만 할 수 있고, 밖의 업무 · 빈 목록 · 다른 칸은 422(S4 대상 바꿔치기 금지). 없으면 전부 | 같음 |
| `POST /api/actions/{id}/undo` | (기존 BE-4) 업무 변경과 기억 변경을 모두 되돌린다 | 같음 |
| `GET /api/actions/history?days=7` | 기록 탭(`days` 1~30). 확인 기다림이 맨 위, 그다음 최근 것부터 | 없음 |
| `GET /api/agent/memory` | 에이전트가 아는 것: 나 · 중요한 사람(각 항목을 읽는 곳 포함) | 없음 |
| `PATCH /api/agent/memory/me` | 부서 · 직책 · 내 배포 목록 | `users` · `user_mailing_lists` · `action_log` |
| `PATCH /api/agent/memory/people/{contact_id}` | 상급자 · 즐겨찾기 표시 | `contacts` · `action_log` |
| `GET /api/classify/status` | 분류 대기 · 진행 · 완료 · 실패 수(화면 '분류 대기 N건', 누락 0)와 `rule_only`(완료 중 규칙 결과만 저장된 수, 엑사원 재분류 대상) | 없음 |
| `POST /api/classify/retry` | 화면 [다시 시도] `{"rule_only"?: false}`. 실패를 대기열로(시도 횟수 0부터), `rule_only=true`면 규칙 결과만 저장된 메일도 다시 분류 → `{"requeued": N}` | `classify_jobs` |
| `GET /api/agent/settings` · `PATCH /api/agent/settings` | 메일 기억하기 켬 · 끔 `{"learn_from_mail": true}`(참거짓만, 기본 켜짐) | `agent_settings` |
| `POST /api/agent/command` | 캐치봇 명령(BE-11 #50 · BE-18 #243). 4절 밖이라 형식은 `docs/30_backend/detail.md` 4절 · `app/schemas/` | 행동에 따라 |
| `POST /api/session` · `GET /api/session/demo` | (11-25 추가) 브라우저 세션 받기 · 발표자 시연 사용자로 들어가기(`DEMO_SHARE_USER_ID`가 있을 때만, 없으면 404). `AUTH_MODE=header`면 세션을 만들지 않는다 | `users` · `web_sessions` |
| 그 밖의 화면 경로 | 이 문서 범위(에이전트 패널) 밖이다. 경로 목록은 `backend/README.md` API 표: `GET /api/dashboard` · `/api/awaiting` · 메일(`/api/mails/{id}` · `/summary` · `/translate` · `/polish` · 회신 · 전달 · `/api/attachments/recent` · `/api/uploads` · `/api/scheduled-sends`) · `/api/reminders` · `/api/notifications` · `/api/briefings/{kind}` · `/api/calendar` · `/api/settings` · `/api/accounts` · `POST /api/graph/notify` | — |

### 3.1 제안 카드 응답

```json
{
  "suggestions": [{
    "key": "due_soon:task:1",
    "rule": "due_soon",
    "via": "suggestion:due_soon",
    "created_at": "2026-11-10T18:00:00+09:00",
    "title": "김민준 팀장님 '견적 회신' 기한이 오늘 18:00이에요. 초안을 써 둘까요?",
    "detail": [],
    "task_ids": [1], "mail_ids": [1],
    "buttons": [
      {"label": "초안 보기", "kind": "action", "action": "T07", "primary": true, "params": {"tone": "polite"},
       "target": {"task_ids": [1], "mail_ids": [1]}},
      {"label": "나중에", "kind": "action", "action": "T05", "primary": false, "params": {"until": null}, "target": {"task_ids": [1], "mail_ids": [1]}},
      {"label": "완료", "kind": "action", "action": "T03", "primary": false, "params": {}, "target": {"task_ids": [1], "mail_ids": [1]}}
    ],
    "menu": [
      {"label": "업무 아님", "kind": "action", "action": "T10", "primary": false, "params": {}, "target": {"task_ids": [1], "mail_ids": [1]}},
      {"label": "이 제안 숨기기", "kind": "hide", "action": "hide", "primary": false, "params": {}, "target": {"task_ids": [], "mail_ids": []}}
    ]
  }],
  "more": 0, "total": 1, "generated_at": "2026-11-11T14:00:00+09:00"
}
```

- `kind`: `action`은 등록된 행동(T01~) · `navigate`는 화면 이동(`open_mail`: 메일 화면의 그 메일) · `hide`는 숨기기 API.
- 버튼을 행동으로 바꾸는 표(프런트엔드 몫):

| action | 부르는 곳 |
|---|---|
| T03 완료 · T10 업무 아님 | `PATCH /api/tasks/{task_ids[0]}` `{"status": "done" 또는 "excluded", "via": 카드.via}` |
| T05 나중에 | 시각 메뉴에서 고른 뒤 `PATCH /api/tasks/{id}` `{"status": "snoozed", "snoozed_until": …, "via": 카드.via}` |
| T07 초안 보기 · T01 · T06 | 에이전트 명령 경로 `POST /api/agent/command`(BE-11, #50)는 있지만, 이 셋은 레지스트리에서 아직 `ready=False`라 "준비 중"(`unsupported`)으로 끝난다(11-27: T01 · T06은 `ready=True`가 됐고 T07만 남았다, `agent/tools/registry.py`. 프런트엔드 버튼이 지금 어느 쪽을 부르는지는 `[미확인]`). 준비될 때까지 프런트엔드는 화면으로 보낸다(T07 → 그 메일 화면(버튼 이름을 [메일 열기]로 바꿈), T01 · T06 → 대시보드, #60) |
| hide | `POST /api/suggestions/{key}/hide` |

- `created_at`은 카드 조건이 처음 맞은 시각이다. 기한 임박이면 기한 24시간 전이지만, 메일이 그 뒤에 왔거나 [나중에]가 그 뒤에 풀렸으면 그 시각이다. 응답 대기는 가장 늦게 기다림에 들어온 메일의 시각이다. ✦ 버튼 배지(마지막으로 패널을 연 뒤 새 카드 수)에 쓴다.

### 3.2 기록 탭 응답

```json
{"days": 7, "items": [
  {"id": "preview:9b1…", "state": "waiting", "action": "bulk_status", "action_id": null, "preview_id": "9b1…",
   "text": "업무 2건 완료 — 확인을 기다려요", "via": "ui", "via_label": "화면 버튼", "auto": false,
   "at": "…+09:00", "expires_at": "…+09:00", "can_undo": false, "redo_action_id": null},
  {"id": "log:12", "state": "done", "action": "set_status", "action_id": 12, "preview_id": null,
   "text": "'견적 회신' 업무를 완료했어요", "via": "suggestion:due_soon", "via_label": "제안 카드(기한 임박)",
   "auto": false, "at": "…+09:00", "expires_at": null, "can_undo": true, "redo_action_id": null}
]}
```

- `state`: `waiting`(미리보기를 만들고 아직 실행하지 않음, 만료 전) · `done` · `undone`. 실패(`failed`)는 실패를 기록하는 경로가 생기면 더한다.
- 되돌리기 기록(`action = undo`)은 따로 줄을 만들지 않는다. 되돌린 원래 줄이 `undone`이 된다. 그 줄의 `redo_action_id`(그 줄을 되돌린 기록)로 `POST /api/actions/{redo_action_id}/undo`를 부르면 다시 하기이고, 줄은 `done`으로 돌아온다.
- `via`: 제안 카드 `suggestion:<종류>` · 기록 탭 `history` · 기억 변경 `memory` · 그 밖에는 `source` 값(`ui` · `agent_rule` …). `via_label`은 화면 문구다. 확인 기다림 줄과 실행 뒤 줄은 같은 via면 같은 문구다. 에이전트가 만든 미리보기는 확인 기다림 줄에서도 그 `source`(`agent_rule` · `agent_model` → "말로 시킴")로 보인다(화면 버튼 미리보기만 `ui`).
- 확인 기다림은 만료 시각과 같은 순간까지 보인다(실행도 그 순간까지 된다).
- `can_undo`: 그 줄이 지금 되돌릴 수 있는 가장 최근 변경일 때만 `true`(뒤에 같은 업무 · 같은 기억 항목을 바꾼 살아 있는 기록이 없을 때).
- `auto`: `source`가 `reply_auto`(D48)면 `true`. `calendar_auto`(D50 결정 6)는 T15 backend에서 `source` 제약에 더할 때 함께 `true`가 된다.

### 3.3 에이전트가 아는 것 `[확정: 문규남 11-11, BE-D18]`

**원칙: 읽는 곳이 정해진 구조화된 값만 기억이다.** 화면에 보이는 모든 항목에는 그 값을 실제로 읽는 곳(`used_by`)이 있다. 아무도 읽지 않는 자유 문장 규칙은 두지 않는다. 11-11 확인 결과, 첫 구현의 '늘 지키는 규칙'(자유 문장, `templates.kind = rule`)은 읽는 곳이 없어 화면 문구("판단할 때 지켜요")가 사실이 아니었다. 그래서 뺐다.

| 기억 | 저장 | 읽는 곳(`used_by`) | 쓰는 길 |
|---|---|---|---|
| 내 직책 · 팀 · 배포 목록(종류: 직책 `role` · 팀 `team` · 전사 `all`) | `users` · `user_mailing_lists` | 메일 분류(owner.position · team · member_of · role_lists · team_lists, AI-D15) | 화면 · 메일 기억하기 |
| 상급자 | `contacts.is_superior` | 제안 카드 ④ · 메일 분류 우선순위(sender.is_superior) | 화면 · T11 · 메일 기억하기 |
| 즐겨찾기 | `contacts.is_favorite` | 메일 분류 우선순위(sender.is_favorite) | 화면 · T11 |
| 맡은 일 · 소속(문맥 기억) | `contact_facts`(kind = works_on · org, 근거 문장 · 메일 id) | 제안 카드의 사람 표시 "김민준 팀장님(한빛은행 2단계 전환 담당)" · "장민호 차장님(한빛은행 IT기획부)" | 화면(`PATCH people {"facts": {...}}`) · 문맥 기억(모델) |

- **T11 중요_발신자_지정**("박 책임님 메일은 항상 중요로")은 AI 계약(AI detail 2절: target sender, params `level` = superior · favorite) 그대로 그 연락처의 표시를 켠다. 자유 문장으로 저장하지 않는다. 실행 함수는 `services/memory.apply_t11()`이고, 확인창(설정 변경, D37)은 에이전트 실행기(BE-11)가 띄운다.
- **메일 분류로 가는 입구는 하나다.** 분류 요청(ai `POST /classify`)의 `owner` · `sender` 칸은 `services/memory.classify_context(mail)`이 만든다. backend의 ai 호출부(`app/ai_client`, BE-9)는 이것만 쓴다. 그래서 화면 · T11 · 메일 기억하기로 바뀐 값이 다음 분류부터 바로 들어간다. 칸 이름은 `ai/app/schemas/classify.py`의 OwnerProfile · SenderFlags와 같다.
- backend ai 호출부(`app/ai_client`, BE-9 #28)는 `app/ai_client/payload.py`에서 `classify_context()`를 쓴다.

응답 예:

```json
{
  "learn_from_mail": true,
  "me": {"name": "문규남", "department": "AX팀", "position": "책임",
         "mailing_lists": [{"address": "ax-team@cne.com", "kind": "team"}],
         "uses": "직책 · 팀 배포 목록으로 온 지시는 나에게 온 것으로 보고 할 일로 잡아요.", "used_by": ["메일 분류"],
         "origin": {"at": null, "text": "처음 설정에서 넣었어요"}},
  "people": [{"contact_id": 5, "name": "박서연", "email": "park@cne.com", "position": "상무",
              "is_superior": true, "is_favorite": false,
              "facts": [{"kind": "org", "label": "소속", "value": "한빛은행 IT기획부",
                         "evidence": "한빛은행 IT기획부 박서연입니다."}],
              "uses": "상급자 메일은 우선순위를 높이고, 받은 지 2시간이 넘도록 처리하지 않으면 제안 카드로 알려 드려요.",
              "used_by": ["제안 카드", "메일 분류"],
              "origin": {"at": "2026-11-11T14:05:00+09:00", "text": "11/11 화면에서 바꿨어요"}}]
}
```

- `people`에는 상급자나 즐겨찾기 표시가 있는 연락처만 나온다. 표시 없는 연락처는 기억이 아니다.
- 바꾸는 요청은 모두 `{"action_id": …, "memory": <위 전체>}`를 돌려준다. 정의되지 않은 칸을 보내면 422.
- `PATCH /me`: 보낸 칸만 바꾼다. `department` · `position`의 빈 문자열은 `null`로 저장한다. `mailing_lists`는 `{"address", "kind"}` 또는 주소 문자열(종류는 주소로 짐작: 주소에 leader · head · manager · 팀장이 있으면 `role`, all · everyone · staff · 전사면 `all`, 그 밖은 `team`)을 받는다. 소문자로 바꾸고 같은 주소는 하나로 합친다. `null`은 목록 비우기. 20개까지, `이름@도메인` 하나씩(공백 · 쉼표 · 세미콜론 · 꺾쇠 · 따옴표 불가). `role` · `team` 목록으로 온 지시만 나에게 온 것으로 본다(AI-D15). `all`은 단체 메일로 본다.
- `PATCH /people/{id}`: `is_superior` · `is_favorite`는 JSON `true` · `false`만(`"no"`, `0`, `null`은 422).
- 되돌리기는 지금 값이 그 기록이 남긴 값과 다르면(시드 등 기록 밖에서 바뀜) 덮어쓰지 않고 409.
- 메일 본문에서 기억을 만드는 길은 3.4절 '메일 기억하기' 하나뿐이고, 설정을 켰을 때만 동작한다.

### 3.4 메일 기억하기 `[확정: 문규남 11-11, BE-D17]`

설정 '메일 기억하기'(**기본 켜짐**, 11-11)가 켜져 있으면, 새로 저장되는 **사내 메일**(보낸 사람 도메인이 내 계정 도메인과 같음)에서 업무 사실을 알아내 바로 넣는다. 항목마다 묻지 않는다. 끄면 아무것도 하지 않는다. 기본이 켜짐인 것은 D50 결정 8 ①(자동 실행은 기본 꺼짐)의 예외다 — 앱 안의 기억만 바꾸고 밖으로 아무것도 보내지 않으며, 모두 보이고 되돌릴 수 있기 때문이다.

| 알아내는 것 | 방법(규칙, 모델 호출 없음) | 넣는 곳 |
|---|---|---|
| 보낸 사람 직급 | 서명 블록에서 `E-Mail :` 줄이 보낸 사람 주소와 같은 블록의 바로 위 4줄 안 "이름 직급" 줄 | 연락처 직급(비어 있을 때만) |
| 상급자 | 그 직급이 내 직급보다 높으면(직급 순서표 `RANK`) | 연락처 상급자 표시(켜기만, 끄지 않음) |
| 내 배포 목록 | 받는 사람 · 참조에 내 주소가 없고 주소가 사내 주소 하나뿐이며, ① 사람 주소가 아니고(연락처에 없고, 그 주소에서 나에게 온 메일이 없음) ② 서로 다른 보낸 사람 2명 이상에게서 같은 모양으로 받았을 때 | 내 배포 목록 |

- 배포 목록 조건 ① ②는 #44 리뷰로 더했다. 숨은참조로 받은 1:1 메일도 '받는 사람 = 동료 한 명, 나는 없음' 모양이라, 그대로 두면 동료 개인 주소가 팀 목록으로 들어가 그분께 간 지시가 내 업무로 잡힐 수 있다(분류 요청의 `team_lists`).
- 설정 '본문 읽기'(`settings.read_body`)가 꺼져 있으면 본문을 보는 서명 학습과 문맥 기억(3.4.1)을 하지 않는다. 받는 사람만 보는 배포 목록 학습은 한다.

- 넣은 것은 기록 탭에 `via = mail_learn`, `via_label = "메일에서 알게 됨"`, `auto = true`로 남고, "에이전트가 아는 것"의 출처는 "M/D 메일에서 알게 됐어요"다. 지우거나 되돌릴 수 있다.
- 사용자가 화면 · 말로 직접 바꾼 항목, 그리고 메일에서 알게 된 것을 사용자가 되돌린 항목은 다시 배우지 않는다(거절로 본다).
- 인용된 앞 메일의 서명(다른 사람 주소)은 쓰지 않는다. 처음 보는 사람은 연락처를 만든다(이 생성 자체는 기록하지 않는다).
- 메일 본문은 저장하지 않는다. 메일을 저장하는 그때 한 번 본다. 메일 저장 경로(시드 · Outlook 동기화 BE-7 · 더미 적재)는 저장 직후 `services/learn.on_mail_saved(db, user_id, mail, body)`를 같은 트랜잭션에서 부른다. 그래서 켜기 전에 받은 메일은 다시 보지 않는다.
- 기록의 `source`는 `mail_learn`이다(#44 리뷰: '말로 시킨 행동' `agent_rule` · `agent_model` 수와 섞이지 않게). 규칙으로 알았는지 모델로 알았는지는 `params_json.learned_by`(`rule` · `model`)에 남는다.
- 근거 문장(문맥 기억)은 `contact_facts`에만 두고 기록 스냅숏(`params_json.after` · `before_json`)에는 넣지 않는다. 화면에서 지우면 어디에도 남지 않는다. 그래서 지운 사실을 되돌리면 값은 돌아오지만 근거 문장은 비어 있다.

### 3.4.1 문맥 기억(모델) `[확정: 문규남 11-11, BE-D21]` — 모델을 연결하면 동작

규칙으로는 못 읽는 것("저는 한빛은행 2단계 전환을 맡고 있습니다")을 모델이 읽어 보낸 사람의 **맡은 일 · 소속**으로 기억한다. 파이프는 모두 만들어 두었고, 엑사원을 연결한 뒤(D52) `MEMORY_EXTRACT=1`을 켜면 동작한다.

```
분류 작업자: /classify 성공 → (MEMORY_EXTRACT=1) learn.learn_context → ai POST /memory/extract
  → ai가 근거 문장이 본문에 그대로 있는 사실만 남김 → contact_facts(기록 · 되돌리기) → 제안 카드 · 에이전트가 아는 것
```

- 분류와 따로 부른다. 동결한 분류 프롬프트와 정답 세트 측정에 영향이 없다. 프롬프트는 `ai/app/prompts/memory_v1.py`.
- 규칙 학습과 같은 선: 설정 '메일 기억하기'가 켜져 있을 때 · 사내 메일만 · 사용자가 직접 바꾸거나 되돌린 연락처는 건드리지 않음 · 같은 값이면 기록 없음.
- 종류는 `works_on`(맡은 거래처 · 프로젝트 · 업무) · `org`(소속) 둘뿐(BE-D18). 값은 40자 이내. 가족 · 건강 · 생일 같은 사적인 사실은 프롬프트에서 금지하고, 정해진 종류 밖은 ai가 버린다.
- 실패(모델 꺼짐 · 오류)는 아무것도 바꾸지 않고, 분류 결과는 그대로 저장된다. 켜면 메일마다 모델을 한 번 더 부르므로 처리 시간이 늘어난다(엑사원 API 실측 후 판단).
- 기록 문장: "메일에서 김민준님의 맡은 일(한빛은행 2단계 전환)을 알게 됐어요". 기록의 `source` · `via`는 `mail_learn`, `learned_by`는 `model`.
- 분류가 엑사원 결과로 끝났을 때만 부른다(규칙 결과만 저장된 메일은 모델이 꺼진 것이므로 부르지 않는다).

### 3.5 메일 분류 연결 `[확정: 문규남 11-11, BE-D19]`

```
메일 저장 ─▶ services/ingest.after_mail_saved ─┬▶ 메일 기억하기(설정을 켰을 때)
                                              └▶ classify_jobs 대기열(받은 메일만, noreply 제외)
작업자(jobs/classify.run_next) ─▶ 본문 가져오기(mail/body.py, 저장하지 않음)
   ─▶ 요청 만들기(ai_client/payload.py: 메일 머리글 + 본문 + memory.classify_context)
   ─▶ ai POST /classify (ai_client, BE-9) ─▶ mails.category · kind · lane, tasks, mail_checks 저장 ─▶ done
```

- 요청은 작업이 실제로 돌 때 만든다. 대기 중에 기억이 바뀌어도 바뀐 값이 들어간다.
- **ai가 꺼져 있거나(`unavailable`) 제한 시간을 넘으면(`timeout`) 실패로 세지 않고 `queued`로 남긴다**(구조도 12절 #17 "ai 중지 → job queued, 분류 대기 N건"). 시도 횟수도 늘지 않는다.
- 실패로 세는 것: 응답 형식 다름 · 응답 mail_id가 다름 · 본문을 가져오지 못함 · 그 밖의 예외(본문 파일 오류 · 저장 실패 등). 대기열로 되돌려 다시 시도하고, 3번이면 `failed`다. 어떤 예외가 나도 `running`으로 남기지 않는다. `failed`는 `POST /api/classify/retry`로 다시 `queued`가 된다. 메일은 지우지 않고 `GET /api/classify/status`에 센다(누락 0).
- **모델 실패로 규칙만 낸 결과(`fallback`)도 저장한다.** ai는 fallback이어도 규칙이 찾은 할 일 · 확인 칸을 채워 보낸다(`ai/app/pipeline/classify.py`). `source = rule`로 저장하고 `done`으로 끝내되, 작업의 `fallback` 칸에 이유를 남겨 엑사원 재분류 대상으로 표시한다(`status.rule_only`). `retry {"rule_only": true}`로 다시 돌리면, 그 메일의 업무 · 확인 칸이 모두 규칙 결과이고 사용자가 손대지 않았을 때만(미처리 · 상태 변경 없음 · 확인 칸 안 봄) 엑사원 결과로 바꾼다.
- 설정 '본문 읽기'를 끄면 본문을 빈 값으로 보낸다(제목 · 발신자로만 분류, 구조도 10절).
- 저장하는 칸: 메일 분류 · 분류 출처 · 메일 성격(`kind`) · 칸 배정(`lane`), 업무 할 일 · 기한 문구 · 기한 · 기한 출처 · 지목 · 긴급(`urgent`) · 재요청(`is_follow_up`) · 우선순위 · 출처 · 근거 문장(지목 · 긴급 · 재요청은 메일 단위 값을 업무마다 복사, #30), 확인 칸(`mail_checks`, 할 일이 없는 메일에 1개, 이유가 정해진 다섯 가지일 때만). 업무 유형 · 끝 시각은 AI-19 · AI-20 계약 정리 때 같은 자리에서 저장한다. 그 메일에 이미 업무나 확인 칸이 있으면 덮어쓰지 않는다(위 재분류 예외만).
- 작업자: `CLASSIFY_WORKER=1`이면 서버와 함께 뜨는 백그라운드 스레드(1프로세스, BE-D10). 리마인더 스케줄러(BE-10)가 붙으면 그 작업으로 옮긴다. 시작할 때 `running`으로 남은 작업을 대기열로 되돌리고, 그 뒤로는 쉴 때마다 `started_at`이 오래된(ai 제한 시간 2배 + 1분) `running`을 되살린다. 분류를 마쳤을 때만 바로 다음 작업을 보고, 실패 · 대기 · 빈 대기열이면 `CLASSIFY_WORKER_INTERVAL`초(기본 5) 쉰다 — ai가 꺼져 있을 때 몇 ms 안에 거듭 부르지 않는다. 대기 작업은 한 번도 꺼내지 않은 것부터, 그다음은 마지막으로 꺼낸 지 오래된 것부터 꺼낸다(`started_at`을 대기열로 돌아간 작업에도 남긴다). 제한 시간 초과는 세지 않아 계속 대기열에 남으므로, 늘 느린 메일 하나가 맨 앞을 차지해 뒤 메일을 막지 않게 하기 위해서다.
- 개발 모드 전용: `POST /api/dev/classify/enqueue` `{"mail_ids"?}`(없으면 작업 없는 받은 메일 전부), `POST /api/dev/classify/run?limit=1~20`(지금 처리). 운영 모드는 404.
- 계약 확인: 만든 요청을 ai 폴더의 `ClassifyRequest`로 읽어 보고, ai가 받는 owner · sender 칸이 하나도 빠지지 않았는지 시험한다(`tests/test_classify_job.py`). backend는 ai를 import하지 않으므로(D34) 따로 띄운 파이썬으로 확인한다.
- 개인정보 가리기(BE-6)는 아직 없다. 지금 데이터는 가상 조직 더미뿐이다(D24 · D53). → 11-15 붙였다: ai에 보내기 전 가리기(#94, `app/privacy/`).

## 4. 카드 판정 규칙

> 11-13 이후 판정은 리마인더 엔진(`app/reminders/rules.py`) 한 곳으로 옮겼고, 제안 카드는 리마인더 목록의 앞쪽 N건이다(BE-D31 · `docs/10_planning/reminders.md`). 아래 표는 11-11 당시 기준이다.

| 카드 | 뜨는 조건 | 기준값 |
|---|---|---|
| ① 아침 요약 `morning` | 미처리 업무가 1건 이상이고, 지금이 R-아침 시각부터 정오 전 | R-아침 기본 08:30. R-아침이 정오 1시간 전보다 늦으면 그때부터 4시간(자정을 넘을 수 있고, 키의 날짜는 시작한 날) |
| ② 기한 지남 `overdue` | 미처리 업무이고 기한 < 지금 | — |
| ③ 기한 임박 `due_soon` | 미처리 업무이고 기한 - 지금 ≤ 24시간 | 24시간 `[제안]` |
| ④ 상급자 `priority_sender` | 미처리 업무이고 발신자가 내 연락처에서 상급자이며 받은 지 2시간 이상 | 2시간 `[제안]` |
| ⑥ 응답 대기 `no_reply` | 내가 보낸 요청 메일 중 기준일이 지나도록 **같은 계정의 같은 대화**에 나 아닌 사람에게 받은 메일이 없는 것 1건 이상. 여러 메일을 한 장으로 | 기준일 = 설정 `awaiting_reply_days`(기본 3, 0 이하는 1) |

- **미처리 업무**: 받은 메일의 업무 중 `pending`, 또는 `snoozed`인데 `snoozed_until` ≤ 지금.
- **업무 하나에 카드 하나**: ② → ③ → ④ 순서에서 처음 걸리는 것만.
- **순서**: ① → ② → ③ → ④ → ⑥. 같은 종류 안에서는 기한이 이른 순(없으면 받은 시각 순).
- **주 버튼**: 메일 분류가 회신 · 요청 · 검토면 [초안 보기](T07), 그 밖이면 [메일 열기].
- **답장 판정**: 대화 id는 메일함마다 따로 매겨지므로 계정까지 맞춘다. 발신자가 내 계정 주소인 받은 메일(내가 속한 목록으로 돌아온 내 사본)은 답장이 아니다.
- **D+n**: 날짜 차이다. 어제 23:30 기한을 오늘 00:10에 보면 D+1.
- **요청 메일 판정** `[제안]`(기획 detail 5절의 `[결정 필요]`): 분류가 공지 · 기타가 아니고, 제목이 `RE:` · `FW:` · `Fwd:` · `회신:` · `답장:` · `전달:`로 시작하지 않는 보낸 메일. 대화 id가 없는 메일은 판정할 수 없어 뺀다.
- **숨김**: 키는 `{카드 종류}:…`(`due_soon:task:1`, `morning:2026-11-11`, `no_reply:waiting`). 형식은 `^(morning|overdue|due_soon|priority_sender|meeting|no_reply):[0-9A-Za-z:_-]{1,80}$`(끝 줄바꿈 불가). 다음 R-아침까지 같은 키를 띄우지 않는다. 그 시각까지 1시간도 안 남았으면 그다음 날 R-아침까지다 `[확정: 문규남 11-11]`(08:29에 숨긴 카드가 1분 뒤 다시 뜨지 않게 하는 방어선). 다른 종류가 되면(임박 → 지남) 키가 바뀌어 바로 뜬다. 응답 대기는 숨길 때 기다리던 메일을 저장해 두고, 그 밖의 메일이 새로 기다림에 들어오면 다시 뜬다(숨긴 뒤 몇 건에 답이 와도 다시 뜨지 않는다).
- **아직 없는 카드**: ⑤ 일정 참석(캘린더 T15가 backend에 생기면, 11/21). 조건은 메일 성격이 회의 · 행사 초대(K09)인 메일이다(D50 #41). 업무마다 '일정참석' 같은 유형은 저장하지 않는다. ④의 ASAP 조건(급함 칸은 #30으로 생겼고 분류 결과로 채우지만, 카드 조건과 문구는 아직 붙이지 않았다).

## 5. 기록(action_log) 형식

| 종류 | `action` | `params_json` | `before_json` | `affected_ids` |
|---|---|---|---|---|
| 업무 상태 | `set_status` · `bulk_status` | `{status, snoozed_until, via?}` | `{"<task_id>": {status, done_at, snoozed_until, status_changed_at}}` | 바뀐 업무 id |
| 기억 | `memory_me` · `memory_people` | `{target, after, via?, text?}` | `{"state": <바꾸기 전 스냅숏>}` | `[]` |
| 되돌리기 | `undo` | `{action_id, target?, after?}` | 되돌리기 직전 스냅숏 | 원래와 같음 |

- `target`: `me:<user_id>` · `contact:<id>`. 되돌리기는 `target`이 있으면 기억으로, 없으면 업무로 처리한다.
- `via` 형식: 영문 소문자와 밑줄, 콜론 하나까지(`suggestion:due_soon`, `history`), 40자 이내. 다른 값은 422.
- `source` 값은 `mail_learn` 하나를 더했다(메일 기억하기, #44 리뷰). 나머지는 그대로(`ui` · `agent_rule` · `agent_model` · `mcp` · `reply_auto`). 카드 버튼은 사용자가 누른 것이라 `ui`다(D50). 제약은 새로 만드는 DB부터 들어간다(#30 칸과 같이 예전 개발 DB는 다시 만든다).

## 6. 새 테이블과 개발용 경로

새 테이블 둘(기존 테이블에는 칸을 더하지 않았다. 마이그레이션 도구가 없어 있는 DB에 칸이 생기지 않기 때문이다):

| 테이블 | 칸 | 제약 |
|---|---|---|
| `suggestion_hides` | id · user_id · key · until · mail_ids(JSON, 응답 대기만) · created_at | (user_id, key) 하나 |
| `user_mailing_lists` | id · user_id · address | (user_id, address) 하나 |
| `agent_settings` | user_id(키) · learn_from_mail(기본 true, 켜짐) · updated_at | 사용자당 1행, 없으면 기본값 |

시나리오 평가용 개발 경로(운영에서는 404. 개발에서도 DB가 메모리이거나, 파일 이름이 `scenario`로 시작하는 `.db`이고 주소에 쿼리 문자열이 없을 때만. `…/ax.db?scenario=1`, `…/scenario/ax.db`, 윈도우 경로 모두 막는다):

| 경로 | 하는 일 |
|---|---|
| `POST /api/dev/scenario/load` | 테이블을 모두 지우고 처음 상태(users · settings · agent_settings · mailing_lists · accounts · contacts · mails · tasks · templates, 선택으로 `now`)를 넣는다. 각 항목의 칸 이름은 9절 테이블 칸 이름 그대로이고, 모르는 칸은 422. 기본값 두 개: `accounts.provider = "dummy"`, `mails.source_id = "M-<id>"` |
| `POST /api/dev/scenario/clock` `{"now": … 또는 null}` | 서비스 시각을 옮긴다(이후 실제 시간만큼 흐른다). 시연 시작 시각(CLOCK_START, #49)과 같은 시간 이동 장치를 쓰므로, 옮긴 값이 그 시각을 덮어쓴다. null이면 실제 시각으로 돌아간다 |
| `POST /api/dev/scenario/ingest` `{"mail_id", "body"}` | 메일 저장 직후 훅(메일 기억하기)을 그 본문으로 부른다 |
| `GET /api/dev/scenario/state` | `{now, tasks: [{id, status, snoozed_until}], action_log: [{id, action, source, via, target, undone}], previews: [{preview_id, used}], contacts: [{id, is_superior, is_favorite}], mailing_lists: [주소], suggestion_hides: [키]}` |

돌리는 법은 `eval/scenarios/README.md`.

## 7. 아직 하지 않은 것

| 항목 | 이유 · 붙일 때 |
|---|---|
| S2 메일 속 지시는 명령이 아님 · S3 발송은 항상 확인 | 에이전트 실행기(BE-11 #31 · #50)는 생겼다. 발송(T14)이 아직 없어 시나리오는 아직 더하지 않았다. 11-27: T14 재촉 발송은 생겼고(#205) 시나리오는 아직 없다(`eval/scenarios/cases` SC-01~SC-11) |
| S6 ai 서비스로 비밀값이 가지 않음 | ai 호출부(`app/ai_client`, #28)는 생겼다. 시나리오는 아직 더하지 않았다 |
| 기록 탭의 '실패' 상태 | 실패를 기록하는 경로가 없다 |
| 일정 참석 카드 · 캘린더 기록 | T15 backend(11/21). 11-27: T15 일정 넣기(BE-15 #74)와 리마인더 회의 준비(`meeting_prep`, `reminders/rules.py`)는 생겼다 |
| 예약 명령(T16) | PL-16 결정 1, 권장 P2 |
| 로그인 | `X-User-Id`는 임시다. 로그인(BE-6 이후)을 붙이면 `app/core/user.py` 한 곳만 바꾼다. 11-25: 계정 로그인 대신 브라우저 세션(`AUTH_MODE=session`)을 그 함수에 붙였다. 계정 로그인은 아직 없다 |
