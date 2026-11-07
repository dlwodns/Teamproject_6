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

export interface Contact {
  email: string;
  name: string | null;
  position: string | null;
  isSuperior: boolean;
  isFavorite: boolean;
}

export interface Mail {
  id: MailId;
  sourceId: string; // 원본 메일 id (예: M-0026)
  direction: 'received' | 'sent';
  sender: string; // 발신자 이메일
  subject: string;
  receivedAtMs: number;
  category: Category | null; // 분류 전이면 null
}

export interface Task {
  id: TaskId;
  mailId: MailId;
  text: string;
  dueAtMs: number | null; // 기한 유무는 이 값으로만 판단한다(due_source는 쓰지 않는다)
  status: TaskStatus;
  seenAtMs: number | null;
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
}
