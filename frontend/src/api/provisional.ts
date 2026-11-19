// [FE 임시] 대시보드 데이터 응답 형식.
// 구조도 8절과의 차이 · 정해야 할 것: docs/20_frontend/be3_contract_comparison.md (BE-3는 이 비교로 계약을 정한 뒤 구현한다)
// backend에 FE용 응답 스키마가 아직 없다(backend/app/schemas 비어 있음, BE-3 예정).
// 구조도 8절 `GET /dashboard`([제안])는 요약 + 칸별 {key, count, overdue, new, task_ids} 형식이라 이 형식과 다르다.
// 이 파일은 모의 데이터와 FE 집계를 위해 FE가 임시로 가정한 형식이며 합의된 계약이 아니다.
// 필드 이름 · 값은 backend 모델(backend/app/models/{mail,user}.py)을 따랐다. 시각은 +09:00이 붙은 ISO 문자열(D47).

export interface ProvisionalContact {
  email: string;
  name: string | null;
  position: string | null;
  is_superior: boolean;
  is_favorite: boolean;
  // 선택 칸(모의 v2 · 시안). 없으면 화면이 거래처 표시를 숨긴다
  org?: string | null;
  is_client?: boolean;
}

export interface ProvisionalMail {
  id: number;
  source_id: string;
  direction: 'received' | 'sent';
  sender: string;
  subject: string;
  received_at: string;
  // 미분류 메일: null 또는 필드 생략 둘 다 허용(FE 임시 계약). 값이 있으면 회신 · 요청 · 검토 · 공지 · 기타 중 하나
  category?: string | null;
  // 선택 칸(모의 v2 · 시안 v3.2, BE-3 #47에는 없음). 빠지면 화면이 그 부분을 숨긴다
  lane?: string | null; // 할 일 · 확인 · 참고
  reasons?: string[];
  to?: string[];
  account?: string | null;
  lang?: string | null;
  read_at?: string | null;
  pinned_at?: string | null; // FE-5d 제안(목록 맨 위 고정)
  folder?: string | null; // BE-7: Outlook 메일함(inbox · archive · deleteditems · other = Outlook에서 옮김), 더미는 null
}

export interface ProvisionalTask {
  id: number;
  mail_id: number;
  text: string;
  due_at: string | null;
  due_source: string;
  status: string;
  seen_at: string | null;
  // 선택 칸. due_raw는 BE-3 #47에 있음, type · evidence_text는 모의 v2에만
  due_raw?: string | null;
  type?: string | null;
  evidence_text?: string | null;
}

// 응답 대기 한 줄(FE 제안, BE-13). 보낸 메일 id는 받은 메일 id와 겹치지 않는다(모의는 1001부터)
export interface ProvisionalAwaiting {
  mail_id: number;
  subject: string;
  to: string;
  sent_at: string;
  days: number;
}

export interface ProvisionalDashboardResponse {
  as_of: string;
  contacts: ProvisionalContact[];
  mails: ProvisionalMail[];
  tasks: ProvisionalTask[];
  awaiting?: ProvisionalAwaiting[]; // 선택 칸. 빠짐 = BE-13 전(화면이 응답 대기 칸을 숨김), [] = 없음
}

// ── 아래는 BE-4(있음)와 FE 제안 요청의 응답 형식. 계약 표: docs/20_frontend/components.md 5.1 ──

// BE-4 backend/app/schemas/actions.py 그대로(있음)
export interface ProvisionalTaskState {
  id: number;
  status: string;
  done_at: string | null;
  snoozed_until: string | null;
  status_changed_at: string | null;
}

export interface ProvisionalActionResult {
  action_id: number | null;
  tasks: ProvisionalTaskState[];
}

export interface ProvisionalUndoResult extends ProvisionalActionResult {
  undone_action_id: number;
}

export interface ProvisionalPreviewResult {
  preview_id: string;
  expires_at: string;
  status: string;
  snoozed_until: string | null;
  targets: { id: number; text: string; status: string }[];
}

// BE-11 #50 backend/app/schemas/agent.py 그대로(있음). summary · awaiting · draft 칸과 그 kind는 FE 제안
export interface ProvisionalAgentTarget {
  id: number;
  mail_id: number;
  text: string;
  status: string;
  snoozed_until: string | null;
}

export interface ProvisionalAgentSummaryItem {
  task_id: number;
  mail_id: number;
  text: string;
  due_at: string | null;
  due_raw: string | null;
  section?: string | null;
}

export interface ProvisionalAgentResult {
  kind: string;
  action: string | null;
  action_name: string | null;
  source: string | null;
  title: string;
  targets: ProvisionalAgentTarget[];
  notes: string[];
  action_id: number | null;
  preview_id: string | null;
  expires_at: string | null;
  summary?: { items: ProvisionalAgentSummaryItem[]; hint: string | null; text?: string | null; refreshing?: boolean }; // FE 제안(T01). text · refreshing은 조율 중(FE-15)
  awaiting?: ProvisionalAwaiting[]; // FE 제안(T06)
  draft?: { mail_id: number; to: string; subject: string; text: string }; // FE 제안(T07)
  person?: ProvisionalAgentPerson; // 사람 조회(T17)
}

export interface ProvisionalAgentPerson {
  contact_id: number;
  name: string | null;
  email: string;
  position: string | null;
  is_superior: boolean;
  is_favorite: boolean;
  facts: { kind: string; label: string; value: string; evidence: string | null; mail_id: number | null }[];
  learn_off: boolean;
  mails: { mail_id: number; subject: string; received_at: string | null }[];
  mail_total: number;
}

// FE 제안(DB notifications · reminders 칸 그대로, BE-12)
export interface ProvisionalNotification {
  id: number;
  kind: string; // reminder · reply_confirm · new_tasks
  title: string;
  body?: string | null;
  task_ids: number[];
  rule?: string | null;
  scheduled_at?: string | null;
  read_at: string | null;
  answered_at: string | null;
  created_at: string;
}

export interface ProvisionalNotificationsResponse {
  items: ProvisionalNotification[];
}

// FE 제안(DB settings · templates 칸 그대로)
export interface ProvisionalTemplate {
  key: string;
  name: string;
  pattern: string;
  // 예전 서버 · 모의 JSON은 greeting · closing · signature도 보낸다. 읽지 않는다
}

export interface ProvisionalSettings {
  remind_time: string; // HH:MM (KST)
  evening_time?: string; // HH:MM (KST) 퇴근 회고 시각(11-14)
  awaiting_reply_days: number;
  quiet_start: string | null;
  quiet_end: string | null;
  reduce_motion: boolean;
  stt_mode: string;
  templates?: ProvisionalTemplate[];
  reply_confirm_skip_until?: string | null; // 선택 칸(DB settings 칸 그대로). +09:00 ISO, null = 꺼짐
  read_body?: boolean; // 선택 칸(11-18 설정 화면)
  work_start?: string;
  work_end?: string;
  work_days?: string;
  away_until?: string | null;
}

// FE 제안: 메일 한 통 = 목록 칸 + 본문 · 업무. 본문은 문단 배열(모의 v2), 문자열이 오면 줄바꿈으로 나눠 읽는다
export interface ProvisionalMailDetail extends ProvisionalMail {
  body: string[] | string;
  tasks: ProvisionalTask[];
}

// FE 제안(AI-13 v2 #34 요약 형식)
export interface ProvisionalMailSummary {
  lang: string;
  gist: string;
  asks: string[];
  due_text: string | null;
}

// FE 제안: 답장 보내기 요청 · 응답(POST /api/mails/{id}/reply)
export interface ProvisionalReplyRequest {
  account: string | null;
  subject: string;
  content: string;
  template_key: string | null;
}

export interface ProvisionalSentReply {
  id: number;
  sent_at: string;
}

// ── 에이전트 패널(있음, PL-16 #44) — backend/app/schemas/agent_panel.py 그대로 ──

export interface ProvisionalSuggestionButton {
  label: string;
  kind: string; // action | navigate | hide
  action: string;
  primary: boolean;
  params: Record<string, unknown>;
  target: { task_ids: number[]; mail_ids: number[] };
}

export interface ProvisionalSuggestion {
  key: string;
  rule: string;
  via: string;
  created_at: string;
  title: string;
  detail: string[];
  task_ids: number[];
  mail_ids: number[];
  buttons: ProvisionalSuggestionButton[];
  menu: ProvisionalSuggestionButton[];
}

export interface ProvisionalSuggestionList {
  suggestions: ProvisionalSuggestion[];
  more: number;
  total: number;
  generated_at: string;
}

export interface ProvisionalHideResult {
  key: string;
  hidden_until: string;
}

export interface ProvisionalHistoryItem {
  id: string;
  state: string;
  action: string;
  action_id: number | null;
  preview_id: string | null;
  text: string;
  via: string;
  via_label: string;
  auto: boolean;
  at: string;
  expires_at: string | null;
  can_undo: boolean;
  redo_action_id?: number | null;
}

export interface ProvisionalHistoryList {
  days: number;
  items: ProvisionalHistoryItem[];
}

export interface ProvisionalOrigin {
  at: string | null;
  text: string;
}

export interface ProvisionalMailingList {
  address: string;
  kind: string;
}

export interface ProvisionalMemoryMe {
  name: string;
  department: string | null;
  position: string | null;
  mailing_lists: ProvisionalMailingList[];
  uses: string;
  used_by: string[];
  origin: ProvisionalOrigin;
}

export interface ProvisionalMemoryFact {
  kind: string;
  label: string;
  value: string;
  evidence: string | null;
}

export interface ProvisionalMemoryPerson {
  contact_id: number;
  name: string | null;
  email: string;
  position: string | null;
  is_superior: boolean;
  is_favorite: boolean;
  facts?: ProvisionalMemoryFact[]; // 계약 문서 예시에는 없고 backend는 늘 보낸다 → 없으면 빈 목록
  uses: string;
  used_by: string[];
  origin: ProvisionalOrigin;
}

export interface ProvisionalAgentMemory {
  learn_from_mail: boolean;
  me: ProvisionalMemoryMe;
  people: ProvisionalMemoryPerson[];
}

export interface ProvisionalMemoryChange {
  action_id: number | null;
  memory: ProvisionalAgentMemory;
}

export interface ProvisionalAgentSettings {
  learn_from_mail: boolean;
}

// ── FE-5d 메일 읽음 · 고정(FE 제안) ──
// PATCH /api/mails/{id} 요청. 응답은 바뀐 메일 한 통(ProvisionalMail)
export interface ProvisionalMailPatch {
  read?: boolean;
  pinned?: boolean;
}

// ── FE-12 캘린더(BE-15) — backend/app/schemas/calendar.py ──
export interface ProvisionalCalendarItem {
  kind: string;
  title: string;
  start: string;
  end: string | null;
  time_stated: boolean;
  mail_id: number | null;
  task_id: number | null;
  event_id: number | null;
  subject: string | null;
  auto: boolean;
}

export interface ProvisionalCalendarRange {
  start: string;
  end: string;
  as_of: string;
  items: ProvisionalCalendarItem[];
}

export interface ProvisionalEventCreate {
  start: string;
  end?: string | null;
  title?: string | null;
  mail_id?: number | null;
  task_id?: number | null;
  via?: string | null;
}

export interface ProvisionalEventResult {
  action_id: number;
  item: ProvisionalCalendarItem;
}

// ── 리마인더 (FE-16 · BE-12 계약) ──
// docs/10_planning/reminders.md 7.2절 그대로(snake_case · +09:00 ISO). 선택 칸(?)은 FE가 더 요청한 것이고, 없으면 화면이 숨기거나 채운다.

export interface ProvisionalReminderAction {
  id: string;
  label: string;
  action: string; // T코드 | open_mail | apply | dismiss
  primary: boolean;
  params?: Record<string, unknown>; // BE-12: dismiss reason · T05 until · T07 mail_id 등. FE는 dismiss의 reason · T13의 start · end만 읽는다
}

export interface ProvisionalReminderItem {
  key: string;
  type: string;
  group: string;
  title: string;
  reason: string;
  evidence: string | null;
  task_id?: number | null;
  task_ids?: number[]; // FE 요청: 기한 몰림처럼 업무가 여럿인 항목
  task_type?: string | null; // 업무 유형(tasks.type). 캐치봇 리마인더 칸을 나눈다
  mail_id?: number | null;
  commitment_id?: number | null;
  due_at?: string | null;
  counterpart?: { name: string; position: string | null; email?: string; label?: string } | null;
  created_at: string;
  state: string;
  notify_count: number;
  last_notified_at?: string | null; // BE-12가 더하는 칸(선택): 마지막으로 알린 시각. 상세 '이 항목 기록'에 쓴다
  type_label?: string; // BE-12가 보냄. FE는 자기 이름표(TYPE_LABEL)를 쓴다
  notify?: boolean; // BE-12: 이 항목이 알림을 보내는 유형인가
  actions: ProvisionalReminderAction[];
}

export interface ProvisionalRemindersResponse {
  as_of: string;
  counts: Record<string, number>; // due · waiting · promise · revisit · prepare · cleanup · all
  items: ProvisionalReminderItem[];
  muted_types?: string[]; // FE 요청
}

/** POST /api/reminders/{key}/dismiss · apply 응답 */
export interface ProvisionalReminderChange {
  key: string;
  state?: string; // BE-12는 보내지 않는다(dismiss는 reason · hidden_until, apply는 task · due_at)
  action_id: number | null;
}

export interface ProvisionalReminderTypeNotify {
  type: string;
  notify: boolean;
}

export interface ProvisionalBriefingItem {
  title: string;
  reason?: string | null; // BE-12 이름(옛 FE 이름 detail도 읽는다)
  detail?: string | null;
  task_id?: number | null;
  mail_id?: number | null;
  commitment_id?: number | null;
  reminder_key?: string | null;
  due_at?: string | null;
  action_id?: number | null;
}

export interface ProvisionalBriefingSection {
  id: string;
  label?: string; // BE-12 이름(옛 FE 이름 title도 읽는다)
  title?: string;
  count: number;
  items: ProvisionalBriefingItem[];
}

/** GET /api/briefings/{morning | evening | weekly}?date= */
export interface ProvisionalBriefing {
  kind: string;
  date: string; // YYYY-MM-DD
  as_of?: string; // BE-12: 답한 시각(요청할 때 만든다). scheduled_at보다 이르면 아직 만들 시각이 아니다
  title?: string;
  summary?: string | null; // BE-12 이름(옛 FE 이름 text도 읽는다)
  text?: string | null;
  total?: number;
  scheduled_at?: string | null; // BE-12가 더하는 칸(선택): 그 브리핑을 만들기로 정한 시각
  generated_at?: string | null; // FE 요청(선택): 없으면 as_of로 본다
  sections: ProvisionalBriefingSection[];
}

/** POST /api/notifications/read-all 응답 */
export interface ProvisionalReadAll {
  updated: number;
}

export interface ProvisionalNotification {
  type?: string | null;
  group?: string | null;
  reminder_key?: string | null;
}
