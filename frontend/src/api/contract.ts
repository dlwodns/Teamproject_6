// 화면이 부르는 서버 요청 전부를 한곳에 모은 계약(docs/20_frontend/components.md 5.1 표와 같은 순서).
// 모의(mockClient.ts) · 실제(httpClient.ts) 둘 다 이 ApiClient를 그대로 구현한다. 화면은 이 함수만 부른다.
//
// 표의 '상태'를 함수마다 적었다.
//   있음:    backend에 이미 있다. 실제 모드에서 실패하면 HttpError · NetworkError
//   FE 제안: backend DB에 칸만 있고 요청은 아직 없다. 실제 모드에서 404 · 405 · 501이면 NotAvailableError →
//            화면은 그 부분을 숨긴다(0건으로 보이지 않는다). 형식은 FE가 DB 칸 이름 그대로 먼저 정한 것
//
// 입력 · 출력은 화면 모델(camelCase, 시각은 epoch 밀리초)이다. 서버 형식(snake_case, +09:00 ISO)과의 변환은 adapter.ts가 한다.
import type { Awaiting, Contact, DashboardSource, Lane, Mail, MailId, Task, TaskId, TaskStatus } from './types.ts';

// ── 업무 상태(BE-4) ──

/** 누가 바꿨는지(BE-4 기록용). BE-4 action_log.source 값(ui · agent_rule · agent_model · mcp)과 아직 맞추지 않았다 → 실제 모드에서는 보내지 않는다 */
export type ActionSource = 'button' | 'sheet' | 'agent';

export interface StatusChange {
  status: TaskStatus;
  snoozedUntilMs?: number; // status가 snoozed일 때만, 그때는 꼭 있어야 한다(BE-4가 422로 거절)
  source?: ActionSource;
}

export interface BulkPreviewRequest {
  taskIds: TaskId[];
  status: TaskStatus;
  snoozedUntilMs?: number;
}

/** 바뀐 뒤 업무 상태(BE-4 TaskState) */
export interface TaskState {
  id: TaskId;
  status: TaskStatus;
  doneAtMs: number | null;
  snoozedUntilMs: number | null;
  statusChangedAtMs: number | null;
}

export interface ActionResult {
  /** 되돌리기에 쓴다. 이미 그 상태라 바뀐 업무가 없으면 null(기록도 없다 → 되돌리기 토스트를 띄우지 않는다) */
  actionId: number | null;
  tasks: TaskState[];
}

export interface UndoResult {
  actionId: number; // 되돌리기 자체의 기록 id(이것을 다시 되돌리면 '다시 하기')
  undoneActionId: number;
  tasks: TaskState[];
}

export interface BulkPreview {
  previewId: string;
  expiresAtMs: number; // 지나면 실행이 409로 거절된다(BE-4 5분)
  status: TaskStatus; // 바뀔 상태
  snoozedUntilMs: number | null;
  targets: { id: TaskId; text: string; status: TaskStatus }[]; // status = 지금 상태
}

// ── 알림(FE 제안, BE-12) ──

export const NOTIFICATION_KINDS = ['reminder', 'reply_confirm', 'new_tasks'] as const;
export type NotificationKind = (typeof NOTIFICATION_KINDS)[number];
export type NotificationId = number & { readonly __brand: 'NotificationId' };

export interface AppNotification {
  id: NotificationId;
  kind: NotificationKind;
  title: string;
  body: string | null; // 둘째 줄
  taskIds: TaskId[];
  rule: string | null; // 리마인더 규칙 이름(R-기한 · R-아침 …)
  scheduledAtMs: number | null;
  readAtMs: number | null;
  answeredAtMs: number | null; // reply_confirm에 예/아니오로 답한 시각
  createdAtMs: number;
}

export interface NotificationPatch {
  read?: true;
  answer?: 'yes' | 'no'; // reply_confirm에만
}

// ── 설정 · 연락처(FE 제안) ──

export interface ReplyTemplate {
  key: string;
  name: string;
  greeting: string;
  closing: string;
  signature: string;
  pattern: string; // {수신자명} · {발신자명} · {내용} 자리 표시
}

export interface Settings {
  remindTime: string; // HH:MM, 한국 시각
  awaitingReplyDays: number;
  quietStart: string | null; // HH:MM, null이면 방해 금지 없음
  quietEnd: string | null;
  reduceMotion: boolean;
  sttMode: string;
  templates?: ReplyTemplate[]; // 선택 칸. undefined = 서버가 안 보냄(템플릿 메뉴 숨김)
  /**
   * 선택 칸(DB settings.reply_confirm_skip_until). 완료 확인 시트의 '오늘 다시 보지 않음'을 고른 뒤 이 시각까지는
   * 답장을 보내면 시트 없이 바로 완료한다(D48 reply_auto). null = 꺼짐, undefined = 서버가 안 보냄(체크 상자를 숨김)
   */
  replyConfirmSkipUntilMs?: number | null;
}

export type SettingsPatch = Partial<Settings>;

export interface ContactPatch {
  isSuperior?: boolean;
  isFavorite?: boolean;
}

// ── 메일 한 통 · 요약(FE 제안) ──

export interface MailDetail extends Mail {
  to: string[];
  body: string[]; // 문단 배열
  lang: string | null;
  lane: Lane | null;
  reasons: string[];
  tasks: Task[]; // 이 메일의 업무(due_raw · type · evidence_text 포함)
}

export interface MailSummary {
  lang: string;
  gist: string;
  asks: string[];
  dueText: string | null;
}

// ── 에이전트 명령(BE-11 #50) ──
// backend/app/schemas/agent.py AgentResult를 화면 모델로 옮긴 것. 대상 찾기 · 확인 판정(D37) · 실행은 모두 서버가 한다.
// 화면은 kind에 따라 카드만 고른다.

/** 서버에 있는 kind(agent.py 그대로) */
export const AGENT_KINDS = ['done', 'confirm', 'query', 'ask', 'empty', 'unsupported'] as const;
/**
 * FE 제안 kind: 오늘 요약(T01) · 답장 없는 메일(T06) · 회신 초안(T07).
 * 서버 레지스트리에서 아직 준비 중(ready=False)이라 실제 서버는 unsupported('…아직 준비 중이에요')로 답한다. 지금은 모의만 만든다
 */
export const AGENT_PROPOSED_KINDS = ['summary', 'awaiting', 'draft'] as const;
export type AgentKind = (typeof AGENT_KINDS)[number] | (typeof AGENT_PROPOSED_KINDS)[number];

/** 명령을 어떻게 이해했나(단계 표시 '명령 이해 · 규칙/엑사원'). 모르는 값은 null */
export type AgentSource = 'agent_rule' | 'agent_model';

export interface AgentCommandRequest {
  text: string; // 1~500자. 넘거나 비면 서버가 422
  /** 메일 화면에서 고른 메일('이거') */
  selectedMailIds?: MailId[];
  /** 직전 결과 대상의 메일 id('그 2건'). 업무 id가 아니다(#50) */
  lastResultIds?: MailId[];
}

export interface AgentTarget {
  id: TaskId;
  mailId: MailId;
  text: string;
  status: TaskStatus; // 지금 상태
  snoozedUntilMs: number | null;
}

/** FE 제안(T01): 오늘 요약 한 줄. 기한 표시는 화면이 dueAtMs · dueRaw로 만든다 */
export interface AgentSummaryItem {
  taskId: TaskId;
  mailId: MailId;
  text: string;
  dueAtMs: number | null;
  dueRaw: string | null;
}

/** FE 제안(T01) */
export interface AgentSummary {
  items: AgentSummaryItem[];
  hint: string | null; // '그 밖에 미처리 N건 · 확인사항 M건'
}

/** FE 제안(T07): 회신 초안. 보내지 않는다 */
export interface AgentDraft {
  mailId: MailId;
  to: string;
  subject: string;
  text: string;
}

export interface AgentResult {
  kind: AgentKind;
  action: string | null; // 행동 ID(T03 등)
  actionName: string | null;
  source: AgentSource | null;
  title: string; // 확인 카드는 질문, 결과 카드는 과거형(서버 문구 그대로)
  targets: AgentTarget[];
  notes: string[]; // '어떻게 해석했나요'
  actionId: number | null; // done: 실행 취소에 쓴다
  previewId: string | null; // confirm: executeAction에 넘긴다
  expiresAtMs: number | null; // confirm: 이 시각까지 실행할 수 있다
  /** FE 제안 칸(kind가 summary · awaiting · draft일 때만) */
  summary?: AgentSummary;
  awaiting?: Awaiting[];
  draft?: AgentDraft;
}

// ── 답장 보내기(FE 제안) ──

export interface ReplyDraft {
  /** 보낸 사람 계정(메일 account 값, 예: 사내 · Outlook). 모르면 null(서버가 원메일을 받은 계정으로) */
  account: string | null;
  /** 제목(RE: 원메일제목) */
  subject: string;
  /** 보낼 본문 전체 — 템플릿 인사 · 맺음 · 서명에 사용자가 쓴 말을 넣은, 미리보기에 보인 글자 그대로 */
  content: string;
  /** 고른 템플릿(기록용). 템플릿 없이 쓰면 null */
  templateKey: string | null;
}

/** 저장된 보낸 메일 */
export interface SentReply {
  id: MailId;
  sentAtMs: number;
}

/** 대시보드 원자료만 쓰는 옛 화면(features/tasks/useDashboard.ts)용 좁은 창구. 새 화면은 ApiClient를 쓴다 */
export interface DashboardApi {
  getDashboardSource(signal?: AbortSignal): Promise<DashboardSource>;
}

export interface ApiClient {
  /** 있음(BE-3 PR #47). 대시보드 · 메일 목록이 나눠 쓰는 원자료 */
  getDashboard(signal?: AbortSignal): Promise<DashboardSource>;
  /** 있음(BE-4) PATCH /api/tasks/{id}. 1건은 확인 없이 바로 */
  patchTaskStatus(id: TaskId, change: StatusChange): Promise<ActionResult>;
  /** 있음(BE-4) POST /api/tasks/bulk/preview. 여러 건은 미리보기 → 확인 → 실행(D37) */
  bulkPreview(request: BulkPreviewRequest): Promise<BulkPreview>;
  /**
   * 있음(BE-4) POST /api/actions/execute. 미리보기 하나는 한 번만 실행된다(두 번째는 409, 만료도 409).
   * taskIds: 확인 카드에서 체크를 남긴 업무(미리보기 대상 안에서). 없으면 전부
   */
  executeAction(previewId: string, taskIds?: readonly TaskId[]): Promise<ActionResult>;
  /** 있음(BE-4) POST /api/actions/{id}/undo */
  undoAction(actionId: number): Promise<UndoResult>;
  /**
   * 있음(BE-11 #50) POST /api/agent/command. 명령 해석 · 대상 찾기 · 확인 판정 · (1건이면) 실행까지 서버가 한다.
   * AI가 꺼졌거나 늦으면 503 → AgentUnavailableError(상태는 바뀌지 않는다). 빈 글자 · 500자 넘음은 422
   */
  runAgentCommand(request: AgentCommandRequest, signal?: AbortSignal): Promise<AgentResult>;
  /** FE 제안(BE-12) GET /api/notifications */
  getNotifications(signal?: AbortSignal): Promise<AppNotification[]>;
  /** FE 제안(BE-12) PATCH /api/notifications/{id}. 바뀐 알림 한 건을 돌려준다 */
  patchNotification(id: NotificationId, patch: NotificationPatch): Promise<AppNotification>;
  /** FE 제안 GET /api/settings */
  getSettings(signal?: AbortSignal): Promise<Settings>;
  /** FE 제안 PATCH /api/settings. 바뀐 뒤 설정 전체를 돌려준다 */
  patchSettings(patch: SettingsPatch): Promise<Settings>;
  /** FE 제안 PATCH /api/contacts/{email}. 바뀐 연락처를 돌려준다 */
  patchContact(email: string, patch: ContactPatch): Promise<Contact>;
  /** FE 제안(BE-13) GET /api/awaiting */
  getAwaiting(signal?: AbortSignal): Promise<Awaiting[]>;
  /** FE 제안 GET /api/mails/{id}. 본문 저장 정책이 정해지기 전까지 실제 모드에서는 대개 NotAvailableError */
  getMail(id: MailId, signal?: AbortSignal): Promise<MailDetail>;
  /** FE 제안(AI-13 v2 #34) POST /api/mails/{id}/summary. 요약할 것이 없으면 null */
  summarizeMail(id: MailId, signal?: AbortSignal): Promise<MailSummary | null>;
  /** FE 제안 POST /api/mails/{id}/reply. 사용자가 [보내기]를 눌렀을 때만 부른다(D48). 저장된 보낸 메일을 돌려준다 */
  sendReply(id: MailId, draft: ReplyDraft): Promise<SentReply>;
}

// ── FE-5d 메일 읽음 · 고정(FE 제안) ──
// 백엔드에는 메일 읽음 · 고정 칸과 요청이 아직 없다. 실제 모드에서 404 · 405 · 501이면 NotAvailableError → 화면은 그 동작을 숨긴다.
// 여러 통은 이 요청을 한 통씩 보낸다(묶음 요청을 따로 두지 않는다 — 단순하게).
// 아래는 위 ApiClient에 합쳐지는 선언이다(TypeScript 인터페이스 합치기). 다른 작업과 합칠 때 겹치지 않게 따로 둔다.

export interface MailPatch {
  /** 참 = 읽음(읽은 시각을 지금으로, 이미 읽었으면 그대로), 거짓 = 안 읽음(읽은 시각을 비움) */
  read?: boolean;
  /** 참 = 목록 맨 위 고정, 거짓 = 고정 해제 */
  pinned?: boolean;
}

export interface ApiClient {
  /** FE 제안 PATCH /api/mails/{id} {read?, pinned?} → 바뀐 메일 한 통(목록 칸, read_at · pinned_at 포함) */
  patchMail(id: MailId, patch: MailPatch): Promise<Mail>;
}
