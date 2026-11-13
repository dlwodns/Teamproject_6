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
  /** 있음(BE-4) POST /api/actions/execute. 미리보기 하나는 한 번만 실행된다(두 번째는 409) */
  executeAction(previewId: string): Promise<ActionResult>;
  /** 있음(BE-4) POST /api/actions/{id}/undo */
  undoAction(actionId: number): Promise<UndoResult>;
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
