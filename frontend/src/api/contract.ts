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
  /**
   * 어느 화면에서 눌렀는지(PL-16, action_log.params_json.via). 제안 카드는 카드의 via(`suggestion:due_soon`), 기록 탭은 `history`.
   * BE-4 요청에 있는 칸이라 실제 모드에서도 보낸다. 형식: 영문 소문자 · 밑줄, 콜론 하나까지, 40자 이내(그 밖은 422)
   */
  via?: string;
}

export interface BulkPreviewRequest {
  taskIds: TaskId[];
  status: TaskStatus;
  snoozedUntilMs?: number;
  via?: string;
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

export const NOTIFICATION_KINDS = ['reminder', 'reply_confirm', 'new_tasks', 'digest'] as const; // digest: 여러 건 묶음 알림(FE-16 · BE-12)
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
  /** 자유롭게 쓴 답장 틀. {수신자명} · {발신자명}은 보낼 때 채우고, {내용} 자리에 쓴 글이 들어간다(없으면 틀 아래) */
  pattern: string;
}

export interface Settings {
  remindTime: string; // HH:MM, 한국 시각. 하루 요약(아침 브리핑) 시각
  eveningTime?: string; // HH:MM. 퇴근 회고 시각(11-14). undefined = 서버가 안 보냄(설정 칸을 숨김)
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
  /** 선택 칸(설정 화면 11-18). undefined = 서버가 안 보냄(그 칸을 숨김) */
  readBody?: boolean; // 메일 본문 읽기. 끄면 새 메일은 제목 · 발신자로만 분류
  workStart?: string; // HH:MM 근무 시작. 근무 시간 밖 알림은 다음 근무 시작에 몰아 보낸다
  workEnd?: string;
  workDays?: string; // "1-5" · "1,3,5"(월=1 … 일=7)
  awayUntilMs?: number | null; // 부재 중(~까지). null = 없음
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
export const AGENT_KINDS = ['done', 'confirm', 'query', 'ask', 'empty', 'unsupported', 'person'] as const;
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
  /** 브리핑 묶음 id(done_today · overdue 등). 회고의 완료 업무를 기한 라벨 대신 '완료'로 보인다 */
  section?: string | null;
}

/** FE 제안(T01) */
export interface AgentSummary {
  items: AgentSummaryItem[];
  hint: string | null; // '그 밖에 미처리 N건 · 확인사항 M건'
  /**
   * 조율 중(T01 백엔드, FE-15): 모델이 쓴 브리핑 한두 문장. 서버가 아직 보내지 않으면 undefined, 못 썼으면 null.
   * 화면은 있을 때만 결과물 칸에 보인다
   */
  text?: string | null;
  /** 조율 중(T01 백엔드, FE-15): 서버가 요약을 새로 정리하는 중이다(지금 보이는 것은 지난 요약). 모르면 undefined */
  refreshing?: boolean;
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
  /** 사람 조회(T17, 11-17). kind가 person일 때만 */
  person?: AgentPerson;
  /** 11-18 메일 목록(T19 메일 찾기 · T20 요약한 메일 · T18 답을 찾은 메일). 없으면 빈 목록 */
  mails?: AgentMail[];
  /** 11-18 카드 본문 줄(T08 근거 문장 · T13 일정 · T20 요청한 것). 접지 않고 보인다 */
  lines?: string[];
}

/** 대화 결과에 실린 메일 한 통 — backend/app/schemas/agent.py AgentMail */
export interface AgentMail {
  mailId: MailId;
  subject: string;
  /** 받은 메일은 보낸 사람, 보낸 메일은 받는 사람 */
  who: string;
  direction: 'received' | 'sent';
  atMs: number | null;
}

/** 사람 조회(T17) — backend/app/schemas/agent.py AgentPerson. 맡은 일 · 소속은 '메일 내용 분석 허용'을 켰을 때만 온다 */
export interface AgentPerson {
  name: string | null;
  email: string;
  position: string | null;
  isSuperior: boolean;
  isFavorite: boolean;
  facts: { label: string; value: string; evidence: string | null; mailId: MailId | null }[];
  /** 메일 내용 분석이 꺼져 있어 맡은 일 · 소속을 싣지 않음 */
  learnOff: boolean;
  /** 그 사람이 보낸 메일(최근 순, 최대 10통) */
  mails: { mailId: MailId; subject: string; receivedAtMs: number | null }[];
  mailTotal: number;
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
  /** 받는 사람(전달 · 새 메일만 보낸다). 답장 · 전체 답장은 서버가 원 메일에서 정한다 */
  to?: string[];
  /** 참조 · 숨은 참조(BE-7). 전체 답장에서 참조를 비우면 서버가 원 메일의 참조를 그대로 쓴다 */
  cc?: string[];
  bcc?: string[];
}

/** 메일 쓰기 종류(FE-18). new는 원 메일 없이 새로 쓴다 */
export type ComposeMode = 'reply' | 'replyAll' | 'forward' | 'new';
export type ReplyMode = Exclude<ComposeMode, 'new'>;

/** 저장된 보낸 메일 */
export interface SentReply {
  /** null = 나갔지만 서버 기록이 실패(다음 동기화가 보낸 편지함에서 넣는다) */
  id: MailId | null;
  sentAtMs: number;
}

/** POST /api/mails/{id}/polish 응답(#95, style=polite). none = 다듬지 못해 보낸 글 그대로(이유는 fallback) */
export interface PolishedReply {
  text: string;
  /** 보낸 글과 다른가 */
  changed: boolean;
  source: 'exaone' | 'none';
  fallback: string | null;
}

// ── 에이전트 패널: 제안 카드 · 기록 탭 · 에이전트가 아는 것(있음, PL-16 #44) ──
// 형식: docs/30_backend/agent_api_contract.md 3.1~3.4 · backend/app/schemas/agent_panel.py 그대로.

export const SUGGESTION_RULES = ['morning', 'overdue', 'due_soon', 'priority_sender', 'meeting', 'no_reply'] as const;
export type SuggestionRule = (typeof SUGGESTION_RULES)[number];

export interface SuggestionButton {
  label: string;
  /** action: 등록된 행동(T01~) · navigate: 화면 이동(open_mail) · hide: 숨기기 API */
  kind: 'action' | 'navigate' | 'hide';
  action: string;
  primary: boolean;
  params: Record<string, unknown>;
  target: { taskIds: TaskId[]; mailIds: MailId[] };
}

export interface Suggestion {
  /** 숨기기 키(`due_soon:task:1`) */
  key: string;
  rule: SuggestionRule;
  /** 버튼으로 행동을 부를 때 그대로 넘긴다(`suggestion:due_soon`) */
  via: string;
  /** 카드 조건이 처음 맞은 시각 */
  createdAtMs: number;
  title: string;
  /** 둘째 줄부터(응답 대기 메일 제목 등) */
  detail: string[];
  taskIds: TaskId[];
  mailIds: MailId[];
  buttons: SuggestionButton[];
  /** ⋯ 메뉴(업무 아님 · 이 제안 숨기기) */
  menu: SuggestionButton[];
}

export interface SuggestionList {
  suggestions: Suggestion[];
  /** 접힌 카드 수('제안 N건 더 보기') */
  more: number;
  total: number;
  /** 서버가 계산한 시각(기록 탭 '10분 전'의 기준 시계로도 쓴다) */
  generatedAtMs: number;
}

export interface HideResult {
  key: string;
  hiddenUntilMs: number;
}

export type HistoryState = 'waiting' | 'done' | 'undone';

export interface HistoryItem {
  /** log:<action_id> | preview:<preview_id> */
  id: string;
  state: HistoryState;
  action: string;
  actionId: number | null;
  previewId: string | null;
  text: string;
  via: string;
  viaLabel: string;
  auto: boolean;
  atMs: number;
  expiresAtMs: number | null;
  canUndo: boolean;
  /** 되돌림 줄의 [다시 하기]: 이 id를 undo 한다 */
  redoActionId: number | null;
}

export interface HistoryList {
  days: number;
  /** 확인 기다림이 맨 위, 그다음 최근 것부터(서버 순서 그대로) */
  items: HistoryItem[];
}

export interface MemoryOrigin {
  /** null = 처음 설정 */
  atMs: number | null;
  text: string;
}

export const MAILING_LIST_KINDS = ['role', 'team', 'all'] as const;
export type MailingListKind = (typeof MAILING_LIST_KINDS)[number];

export interface MailingList {
  address: string;
  kind: MailingListKind;
}

export interface MemoryMe {
  name: string;
  department: string | null;
  position: string | null;
  mailingLists: MailingList[];
  uses: string;
  usedBy: string[];
  origin: MemoryOrigin;
}

export const MEMORY_FACT_KINDS = ['works_on', 'org'] as const;
export type MemoryFactKind = (typeof MEMORY_FACT_KINDS)[number];

export interface MemoryFact {
  kind: MemoryFactKind;
  label: string;
  value: string;
  evidence: string | null;
}

export interface MemoryPerson {
  contactId: number;
  name: string | null;
  email: string;
  position: string | null;
  isSuperior: boolean;
  isFavorite: boolean;
  facts: MemoryFact[];
  uses: string;
  usedBy: string[];
  origin: MemoryOrigin;
}

export interface AgentMemory {
  learnFromMail: boolean;
  me: MemoryMe;
  /** 상급자 · 즐겨찾기 표시(또는 문맥 기억)가 있는 연락처만 */
  people: MemoryPerson[];
}

export interface MemoryChange {
  /** 되돌리기에 쓴다. 바뀐 것이 없으면 null */
  actionId: number | null;
  memory: AgentMemory;
}

/** 보낸 칸만 바꾼다. 빈 글자는 null로 저장, mailingLists: null은 목록 비우기 */
export interface MemoryMePatch {
  department?: string | null;
  position?: string | null;
  mailingLists?: MailingList[] | null;
}

export interface MemoryPersonPatch {
  isSuperior?: boolean;
  isFavorite?: boolean;
  /** 문맥 기억 고치기 · 지우기(null) */
  facts?: Partial<Record<MemoryFactKind, string | null>>;
}

export interface AgentSettings {
  learnFromMail: boolean;
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
  sendReply(id: MailId, draft: ReplyDraft, mode?: ReplyMode): Promise<SentReply>;
  /** BE-7 POST /api/mails(새 메일). accountId = 보낼 계정(GET /api/accounts의 id), null이면 서버가 보낼 수 있는 첫 계정 */
  sendNewMail(draft: ReplyDraft, accountId: number | null): Promise<SentReply>;
  /** #95 POST /api/mails/{id}/polish {text, style: 'polite'}. 답장 칸에 쓰거나 말한 글을 격식 있는 업무 문장으로 다듬는다(보내지 않는다).
   *  서버가 원 메일과 쓴 글의 개인정보를 가린 뒤 ai로 보낸다(#94 BE-6) */
  polishReply(id: MailId, text: string): Promise<PolishedReply>;
  /** 있음(PL-16) GET /api/suggestions?limit=N. 읽기만 한다(S1) */
  getSuggestions(limit: number, signal?: AbortSignal): Promise<SuggestionList>;
  /** 있음(PL-16) POST /api/suggestions/{key}/hide. 다음 R-아침까지 */
  hideSuggestion(key: string): Promise<HideResult>;
  /** 있음(PL-16) GET /api/actions/history?days=N(1~30) */
  getActionHistory(days: number, signal?: AbortSignal): Promise<HistoryList>;
  /** 있음(PL-16) GET /api/agent/memory */
  getAgentMemory(signal?: AbortSignal): Promise<AgentMemory>;
  /** 있음(PL-16) PATCH /api/agent/memory/me. 되돌리기는 undoAction(actionId) */
  patchAgentMemoryMe(patch: MemoryMePatch): Promise<MemoryChange>;
  /** 있음(PL-16) PATCH /api/agent/memory/people/{contact_id} */
  patchAgentMemoryPerson(contactId: number, patch: MemoryPersonPatch): Promise<MemoryChange>;
  /** 있음(PL-16) GET /api/agent/settings */
  getAgentSettings(signal?: AbortSignal): Promise<AgentSettings>;
  /** 있음(PL-16) PATCH /api/agent/settings */
  patchAgentSettings(patch: AgentSettings): Promise<AgentSettings>;
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

// ── FE-12 캘린더 (BE-15 · D50 · D56) ──
// backend/app/api/calendar.py(feature/BE-15-calendar)와 같은 형식. 그 PR이 머지되기 전 실제 모드에서는 404 → NotAvailableError.
// 달력 한 칸에 보이는 것: 기한(due) · 다시 알림(snoozed, 나중에) · 회의(meeting, 일정참석 업무) · 넣은 일정(event).

export const CALENDAR_KINDS = ['due', 'snoozed', 'meeting', 'event'] as const;
export type CalendarKind = (typeof CALENDAR_KINDS)[number];

export interface CalendarItem {
  kind: CalendarKind;
  title: string;
  startMs: number;
  /** meeting · event만. due · snoozed는 한 시점 */
  endMs: number | null;
  /** false면 날짜만 보여 준다(메일에 시각이 없어 기본 시각으로 채운 기한 · 회의) */
  timeStated: boolean;
  mailId: MailId | null;
  taskId: TaskId | null;
  /** event만. [빼기]에 쓴다 */
  eventId: number | null;
  /** 메일 제목(메일로 넘어가기) */
  subject: string | null;
  /** 자동 등록한 일정(지금은 늘 false) */
  auto: boolean;
}

export interface CalendarRange {
  /** 'YYYY-MM-DD' 두 날 포함 */
  start: string;
  end: string;
  asOfMs: number;
  items: CalendarItem[];
}

export interface CalendarEventCreate {
  startMs: number;
  /** 없으면 시작 + 1시간(D50) */
  endMs?: number | null;
  /** 없으면 메일 제목, 그것도 없으면 '일정' */
  title?: string | null;
  mailId?: MailId | null;
  taskId?: TaskId | null;
  via?: string | null;
}

export interface CalendarEventResult {
  /** 되돌리기: undoAction(actionId) */
  actionId: number;
  item: CalendarItem;
}

export interface ApiClient {
  /** BE-15(#BE-15 PR) GET /api/calendar?start=&end= — 두 날 포함, 62일까지 */
  getCalendar(start: string, end: string, signal?: AbortSignal): Promise<CalendarRange>;
  /** BE-15 POST /api/calendar/events. 메일 한 통에 하나(이미 있으면 409) */
  addCalendarEvent(request: CalendarEventCreate): Promise<CalendarEventResult>;
  /** BE-15 DELETE /api/calendar/events/{id}. 되돌리기는 undoAction(actionId) */
  removeCalendarEvent(eventId: number): Promise<CalendarEventResult>;
}

// ── 리마인더 (FE-16 · BE-12 계약) ──
// 명세: docs/10_planning/reminders.md 2 · 3 · 6 · 7.2절(PL-18). 백엔드(BE-12)와 AI(AI-24)가 같은 명세로 함께 만들고 있어서,
// 프론트는 7.2절 형식으로 모의 응답을 먼저 만들었다. 실제 모드에서 404 · 405 · 501이면 NotAvailableError → 화면이 그 부분을 숨긴다.
// 아래 선언은 위 인터페이스에 합쳐진다(TypeScript 인터페이스 합치기). 캘린더 · 형광펜 작업과 겹치지 않게 이 파일 끝에 따로 둔다.

/** 묶음 6개(공통 D57). 왼쪽 메뉴 · 🔔 칩 순서 */
export const REMINDER_GROUPS = ['due', 'waiting', 'promise', 'revisit', 'prepare', 'cleanup'] as const;
export type ReminderGroup = (typeof REMINDER_GROUPS)[number];

/** 업무 유형 6종(ai classify_v8 TASK_TYPES · tasks.type). 캐치봇 리마인더 칸은 이 유형별로 나눈다(11-14 결정) */
export const TASK_TYPES = ['자료제출요청', '회신요청', '검토승인요청', '수정재전송요청', '일정참석', '조치요청'] as const;
export type TaskType = (typeof TASK_TYPES)[number];

/** 유형(명세 3절 표). delegated · recurring은 코드만 예약('나중' 단계) */
export const REMINDER_TYPES = [
  'overdue',
  'due_soon',
  'due_changed',
  'due_cluster',
  'no_reply',
  'their_promise',
  'my_promise',
  'delegated',
  'snooze_due',
  'priority_sender',
  'cc_mention',
  'stale',
  'stalled_thread',
  'meeting_prep',
  'recurring',
  'resolved',
  'reply_confirm',
] as const;
export type ReminderType = (typeof REMINDER_TYPES)[number];

/** active = 목록, quiet = 알림을 3번 보내 목록에만 남음('조용히 둠'), done · dismissed = 끝남(목록에서 빠짐) */
export const REMINDER_STATES = ['active', 'quiet', 'done', 'dismissed'] as const;
export type ReminderState = (typeof REMINDER_STATES)[number];

/** 숨김 · 신고 이유. not_mine은 서버가 T10(업무 제외)을 부른다. keep = '그대로 두기 · 아직 남았어요'(정리 제안을 거절) */
export const DISMISS_REASONS = ['hide', 'not_mine', 'wrong_signal', 'keep', 'stop_waiting'] as const;
export type DismissReason = (typeof DISMISS_REASONS)[number];

/**
 * 항목 버튼. action: T코드(T03 완료 · T05 미루기 · T07 초안 · T13 그날 업무 …) · open_mail · apply · dismiss.
 * dismiss 버튼의 이유는 id로 정한다(id가 DISMISS_REASONS 중 하나면 그 이유, 아니면 hide)
 */
export interface ReminderAction {
  id: string;
  label: string;
  action: string;
  primary: boolean;
  /** dismiss 버튼의 이유(BE-12 params.reason). 없으면 id로 정한다 */
  reason?: DismissReason;
  /**
   * T13(기한 보기) 날짜 범위(BE-12 params.start · end, KST 'YYYY-MM-DD', 두 날 포함 — GET /api/calendar와 같은 꼴).
   * 서버가 둘 다 문자열로 보낼 때만 둔다. 날짜가 맞는지는 화면 판단(reminderModel)이 본다
   */
  range?: { start: string; end: string };
}

export interface ReminderCounterpart {
  name: string;
  position: string | null;
}

export interface ReminderItem {
  /** 예: `overdue:task:12` · `no_reply:sent_mail:1001` · `due_cluster:day:2026-11-06` */
  key: string;
  type: ReminderType;
  group: ReminderGroup;
  title: string;
  /** 왜 지금: 이유 한 문장 */
  reason: string;
  /** 근거 문장(AI-15). 없으면 null */
  evidence: string | null;
  taskId: TaskId | null;
  /** FE 요청 칸: 하루에 여러 업무가 걸린 항목(기한 몰림)의 업무 전부. 서버가 안 보내면 taskId 하나로 채운다 */
  taskIds: TaskId[];
  /** 업무 유형(BE tasks.type). 업무가 아닌 항목(보낸 메일 · 약속 · 기한 몰림)이나 유형 모르는 옛 업무는 null */
  taskType: TaskType | null;
  mailId: MailId | null;
  commitmentId: number | null;
  dueAtMs: number | null;
  counterpart: ReminderCounterpart | null;
  createdAtMs: number;
  state: ReminderState;
  notifyCount: number;
  /** FE 요청 칸(선택): 마지막으로 알린 시각. 상세의 '이 항목 기록'에 쓴다 */
  lastNotifiedAtMs: number | null;
  actions: ReminderAction[];
}

export interface ReminderList {
  asOfMs: number;
  /** 묶음별 건수 + 전체(all). 끝난 항목은 세지 않는다 */
  counts: Record<ReminderGroup | 'all', number>;
  items: ReminderItem[];
  /** FE 요청 칸(선택): 알림을 끈 유형. undefined = 서버가 안 보냄(⋯ 메뉴는 '끄기'만 보인다) */
  mutedTypes?: ReminderType[];
}

/** 숨김 · 신고 · 적용 결과. actionId가 있으면 [실행 취소](POST /api/actions/{id}/undo) */
export interface ReminderChange {
  key: string;
  /** BE-12는 보내지 않는다(모의만). 화면은 쓰지 않고 목록을 다시 부른다 */
  state?: ReminderState;
  actionId: number | null;
}

export interface ReminderTypeNotify {
  type: ReminderType;
  notify: boolean;
}

/** 브리핑 · 회고(명세 4.3절). 무엇이 있는지만 알린다 — 할 일을 권하는 문장을 쓰지 않는다(AI-D18) */
export const BRIEFING_KINDS = ['morning', 'evening', 'weekly'] as const;
export type BriefingKind = (typeof BRIEFING_KINDS)[number];

export interface BriefingItem {
  title: string;
  detail: string | null;
  taskId: TaskId | null;
  mailId: MailId | null;
  reminderKey: string | null;
  dueAtMs: number | null;
}

export interface BriefingSection {
  /** 아침: overdue · due_today_allday · due_today_am · due_today_pm · no_reply · my_promise · auto_done, 퇴근: done_today · remaining · due_tomorrow, 주간: done_week · carry_over · waiting · due_next_week (ai io_spec 3절) */
  id: string;
  title: string;
  count: number;
  items: BriefingItem[];
}

export interface Briefing {
  kind: BriefingKind;
  /** YYYY-MM-DD(한국 날짜) */
  date: string;
  /** 만드는(만든) 시각. 아직 만들 때가 아니면 generatedAtMs가 null */
  scheduledAtMs: number | null;
  generatedAtMs: number | null;
  /** 서버가 답한 시각(BE-12 as_of). 이것이 scheduledAtMs보다 이르면 아직 만들 시각이 아니다(내용이 와도 보이지 않는다) */
  asOfMs: number | null;
  /** 지금 다시 센 건수 문장(정해진 문장). 없으면 null */
  text: string | null;
  /** 정한 시각에 미리 만든 머리 문장(AI-29, 최대 3문장). 만든 뒤 목록이 바뀌었을 수 있어 만든 시각과 함께 보인다. 없으면 null */
  headline: string | null;
  headlineAtMs: number | null;
  sections: BriefingSection[];
}

export interface AppNotification {
  /** FE 제안 칸(BE-12): 리마인더 알림이면 그 유형 · 묶음 · 항목 키. 리마인더가 아닌 알림(새 업무 등)은 null · 없음 */
  type?: ReminderType | null;
  group?: ReminderGroup | null;
  reminderKey?: string | null;
}

export interface AgentCommandRequest {
  /** 고른 리마인더의 업무(명세 5절 '아래 입력'). 서버는 '이거'를 이 업무로 읽는다 */
  taskIds?: TaskId[];
  /** 고른 리마인더 키(선택, 기록용) */
  reminderKey?: string;
}

export interface ApiClient {
  /** FE 제안(BE-12) GET /api/reminders?group= */
  getReminders(group: ReminderGroup | 'all', signal?: AbortSignal): Promise<ReminderList>;
  /** FE 제안(BE-12) POST /api/reminders/{key}/dismiss {reason} */
  dismissReminder(key: string, reason: DismissReason): Promise<ReminderChange>;
  /** FE 제안(BE-12) POST /api/reminders/{key}/apply — 기한 바꾸기(T16) · 완료(T03) · 약속 끝냄. 되돌리기는 undoAction */
  applyReminder(key: string): Promise<ReminderChange>;
  /** FE 제안(BE-12) PATCH /api/reminders/types/{type} {notify} — 알림만 끄고 켠다. 목록에는 계속 보인다 */
  setReminderTypeNotify(type: ReminderType, notify: boolean): Promise<ReminderTypeNotify>;
  /** FE 제안(BE-12) GET /api/briefings/{kind}?date=YYYY-MM-DD */
  getBriefing(kind: BriefingKind, date: string, signal?: AbortSignal): Promise<Briefing>;
  /** FE 제안(BE-12) POST /api/notifications/read-all → 읽음으로 바꾼 수 */
  readAllNotifications(): Promise<number>;
}

// ── BE-7 메일 계정 · Outlook 연결 ──
// backend/app/api/accounts.py. 서버가 더미 모드(MAIL_SOURCE=dummy)면 연결 시작이 501 → NotAvailableError → 화면은 연결 버튼 대신 안내를 보인다.

export interface MailAccount {
  id: number;
  /** dummy = 시연 계정, outlook_graph = Outlook */
  provider: string;
  email: string;
  /** Outlook: 토큰이 있음(끊었거나 만료되면 false → 다시 연결). 시연 계정은 늘 true */
  connected: boolean;
  lastSyncedMs: number | null;
}

export interface MailAccountList {
  /** 서버가 Outlook 연결을 켰나(MAIL_SOURCE=outlook_graph). 거짓이면 연결 버튼 대신 안내 */
  outlookEnabled: boolean;
  items: MailAccount[];
}

export interface AccountSyncResult {
  added: number;
  updated: number;
  removed: number;
  lastSyncedMs: number | null;
}

export interface ApiClient {
  /** 있음(BE-7) GET /api/accounts */
  getAccounts(signal?: AbortSignal): Promise<MailAccountList>;
  /** 있음(BE-7) POST /api/accounts/outlook/connect → Microsoft 로그인 주소. 화면은 그 주소로 이동한다 */
  connectOutlook(): Promise<string>;
  /** 있음(BE-7) POST /api/accounts/{id}/sync → 지금 받은 수 */
  syncAccount(id: number): Promise<AccountSyncResult>;
  /** 있음(BE-7) POST /api/accounts/{id}/disconnect → 토큰만 지운다(받은 메일 · 업무는 남음) */
  disconnectAccount(id: number): Promise<MailAccount>;
}

// ── BE-7 보관함 · 지운 편지함 ──
// 대시보드는 보관 · 지운 메일을 빼므로 따로 받는다. 지우기도 지운 편지함으로 옮기기다(영구 삭제 없음).

export type MailFolder = 'inbox' | 'archive' | 'deleteditems';

export interface ApiClient {
  /** 있음(BE-7) GET /api/mails/hidden → 보관 · 지운(연결 끊긴 계정에서 우리 앱만 숨긴 것 포함) 받은 메일, 최근 순 */
  getHiddenMails(signal?: AbortSignal): Promise<Mail[]>;
  /** 있음(BE-7) POST /api/mails/{id}/move {folder} → 옮긴 메일. inbox로 옮기면 숨김도 풀린다 */
  moveMail(id: MailId, folder: MailFolder): Promise<Mail>;
}
