// 화면용 모델. 외부 응답(provisional.ts)은 adapter.ts에서 이 형태로 바꾼 뒤에만 화면에 넘긴다.
// 시각은 epoch 밀리초로 들고 다닌다(시간대 정보를 잃지 않게, 브라우저 시간대와 무관하게).

// 메일 id와 업무 id는 둘 다 backend DB 정수지만 서로 바꿔 쓰면 안 된다 → 타입으로 구분한다.
export type MailId = number & { readonly __brand: 'MailId' };
export type TaskId = number & { readonly __brand: 'TaskId' };

// backend/app/models/mail.py CATEGORIES (D39) · TASK_STATUSES
export const CATEGORIES = ['회신', '요청', '검토', '공지', '기타'] as const;
export type Category = (typeof CATEGORIES)[number];
export const TASK_STATUSES = ['pending', 'done', 'excluded', 'snoozed'] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];
// 메일 칸(시안 v3.2): 할 일 · 확인 · 참고. BE-3 응답에는 아직 없다(있어도 되고 없어도 되는 칸)
export const LANES = ['할 일', '확인', '참고'] as const;
export type Lane = (typeof LANES)[number];

// 있어도 되고 없어도 되는 칸(선택 칸)의 값 규칙 — 화면이 두 경우를 다르게 그려야 해서 섞지 않는다.
//   undefined: 서버가 그 칸을 보내지 않았다(BE-3에 아직 없음) → 화면은 그 부분을 통째로 숨긴다
//   null:      서버가 칸은 보냈지만 값이 없다(또는 FE가 모르는 값) → 화면은 '없음'으로 그린다
// 0건 · 빈 글자로 바꿔 보이지 않는다(components.md 1절 6번).

export interface Contact {
  email: string;
  name: string | null;
  position: string | null;
  isSuperior: boolean;
  isFavorite: boolean;
  org?: string | null; // 소속 회사(거래처 표시용). 선택 칸
  isClient?: boolean; // 거래처 여부(UX-D13 거래처 칩). 선택 칸, 안 오면 칩을 숨긴다
}

export interface Mail {
  id: MailId;
  sourceId: string; // 원본 메일 id (예: M-0026)
  direction: 'received' | 'sent';
  sender: string; // 발신자 이메일
  subject: string;
  receivedAtMs: number;
  category: Category | null; // 분류 전이면 null
  // 아래는 선택 칸(모의 v2에만 있다). undefined = 서버가 안 보냄, null = 값 없음
  lane?: Lane | null;
  reasons?: string[]; // 확인 칸으로 간 이유(칩)
  to?: string[]; // 받는 사람 표시 이름
  account?: string | null; // 받은 계정(사내 · Outlook 등)
  lang?: string | null; // 본문 언어(ko · en · fr …), 번역 · 요약 버튼 판단용
  readAtMs?: number | null; // 읽은 시각, null이면 안 읽음
  pinnedAtMs?: number | null; // 고정한 시각(FE-5d 제안), null이면 고정 안 함. undefined면 고정 기능을 숨긴다
  folder?: string | null; // BE-7 Outlook 메일함(inbox · archive · deleteditems · other), 더미는 null
}

export interface Task {
  id: TaskId;
  mailId: MailId;
  text: string;
  dueAtMs: number | null; // 기한 유무는 이 값으로만 판단한다(due_source는 쓰지 않는다)
  status: TaskStatus;
  seenAtMs: number | null;
  // 아래는 선택 칸. undefined = 서버가 안 보냄, null = 값 없음
  dueRaw?: string | null; // 메일 속 기한 표현 그대로(ASAP 라벨은 이 값이 있을 때만). BE-3 #47에 있음
  type?: Category | null; // 업무 유형. 메일 category와 다를 수 있다. 5분류 밖의 값은 null
  evidenceText?: string | null; // 업무를 뽑은 근거 문장(본문 형광펜, AI-15)
}

// 응답 대기(내가 보낸 메일 중 답이 아직 없는 것, BE-13). 보낸 메일이라 mails[]에는 없다
export interface Awaiting {
  mailId: MailId;
  subject: string;
  to: string; // 받는 사람 표시 이름 한 줄(예: '박지호 매니저')
  sentAtMs: number;
  days: number; // 보낸 뒤 지난 날 수
}

export type DataOrigin =
  | { kind: 'mock'; dataset: string; version: string }
  | { kind: 'http'; baseUrl: string };

export interface DashboardSource {
  origin: DataOrigin;
  asOfMs: number; // 집계 기준 시각
  contacts: Contact[];
  mails: Mail[];
  tasks: Task[];
  // undefined = 서버가 응답 대기를 보내지 않음(BE-13 전) → 화면은 응답 대기 칸을 숨긴다. [] = 응답 대기 없음
  awaiting?: Awaiting[];
}
