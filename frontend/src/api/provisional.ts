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
  summary?: { items: ProvisionalAgentSummaryItem[]; hint: string | null }; // FE 제안(T01)
  awaiting?: ProvisionalAwaiting[]; // FE 제안(T06)
  draft?: { mail_id: number; to: string; subject: string; text: string }; // FE 제안(T07)
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
  greeting: string;
  closing: string;
  signature: string;
  pattern: string;
}

export interface ProvisionalSettings {
  remind_time: string; // HH:MM (KST)
  awaiting_reply_days: number;
  quiet_start: string | null;
  quiet_end: string | null;
  reduce_motion: boolean;
  stt_mode: string;
  templates?: ProvisionalTemplate[];
  reply_confirm_skip_until?: string | null; // 선택 칸(DB settings 칸 그대로). +09:00 ISO, null = 꺼짐
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

// ── FE-5d 메일 읽음 · 고정(FE 제안) ──
// PATCH /api/mails/{id} 요청. 응답은 바뀐 메일 한 통(ProvisionalMail)
export interface ProvisionalMailPatch {
  read?: boolean;
  pinned?: boolean;
}
