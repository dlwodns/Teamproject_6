// 화면이 서버 데이터를 읽는 TanStack Query 훅. QueryClient · 공급자는 app/queryClient.ts가 만든다(여기서는 쓰기만).
// 키는 queryKeys 한곳에서만 만든다. 다시 불러오기(invalidateQueries)가 같은 키를 가리켜야 해서다.
//
// 훅마다 isNotAvailable을 더했다: 실제 모드에서 서버에 그 요청이 아직 없으면(NotAvailableError) 화면은 그 부분을 숨긴다.
// isError만 보고 '불러오지 못함 [다시 시도]'를 띄우면 없는 기능을 고장으로 보이게 되므로, 둘을 나눠 본다.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client.ts';
import type {
  AgentSettings,
  ApiClient,
  AppNotification,
  ComposeMode,
  ContactPatch,
  MailFolder,
  NotificationId,
  NotificationPatch,
  ReplyDraft,
  Settings,
  SettingsPatch,
} from './contract.ts';
import { isScheduled } from './contract.ts';
import { ConfigError, ContractError, HttpError, NotAvailableError } from './errors.ts';
import type { MailId } from './types.ts';

export const queryKeys = {
  dashboard: ['dashboard'] as const,
  notifications: ['notifications'] as const,
  settings: ['settings'] as const,
  awaiting: ['awaiting'] as const,
  mail: (id: MailId) => ['mail', id] as const,
  mailSummary: (id: MailId) => ['mail-summary', id] as const,
  /** 에이전트 패널(제안 · 기록 · 기억 · 설정). 업무 · 기억이 바뀌면 이 앞부분으로 한꺼번에 다시 부른다 */
  agent: ['agent'] as const,
  history: (days: number) => ['agent', 'history', days] as const,
  agentMemory: ['agent', 'memory'] as const,
  agentSettings: ['agent', 'settings'] as const,
};

/** 다시 물어도 결과가 같은 오류(없는 요청 · 형식 오류 · 설정 오류 · 4xx)는 다시 묻지 않는다. 그 밖은 앱 기본(1번)과 같게 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof NotAvailableError || error instanceof ContractError || error instanceof ConfigError) return false;
  if (error instanceof HttpError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

// 쿼리 결과 객체에 읽기 전용 값으로 붙인다(펼쳐 복사하면 TanStack Query가 '읽은 칸만 다시 그리기'를 못 한다)
export function withAvailability<R extends { error: unknown }>(result: R): R & { readonly isNotAvailable: boolean } {
  return Object.defineProperty(result, 'isNotAvailable', {
    get: () => result.error instanceof NotAvailableError,
    enumerable: true,
    configurable: true,
  }) as R & { readonly isNotAvailable: boolean };
}

/** 대시보드 원자료. 대시보드 · 메일 목록이 같은 캐시를 나눠 쓴다 */
/** 분류 대기가 있을 때 대시보드 다시 받기 간격(분류 작업자는 한 통에 수십 초) · 없을 때(Outlook 동기화 1분 + 30초 안에 보이게) */
export const PENDING_REFRESH_MS = 5_000;
export const IDLE_REFRESH_MS = 30_000;
/** 분류 대기 수가 이만큼 그대로면 자주 받기를 멈춘다 — 분류 실패 · AI 꺼짐으로 계속 null인 메일 때문에 5초마다 끝없이 받지 않게(#276 리뷰) */
export const PENDING_STALL_MS = 10 * 60_000;

/** 분류 대기 수(pending)에 따른 다시 받기 간격. 수가 바뀐 지 PENDING_STALL_MS 안이면 자주, 아니면 가끔 */
export function refreshInterval(pending: number, at: number, seen: { count: number; since: number }): number {
  if (pending !== seen.count) {
    seen.count = pending;
    seen.since = at;
  }
  return pending > 0 && at - seen.since < PENDING_STALL_MS ? PENDING_REFRESH_MS : IDLE_REFRESH_MS;
}
const pendingSeen = { count: 0, since: 0 };

export function useDashboardQuery() {
  return withAvailability(
    useQuery({
      queryKey: queryKeys.dashboard,
      queryFn: ({ signal }) => api.getDashboard(signal),
      retry: shouldRetry,
      // AI-42: 새로 고침 없이 분류 결과 · 새 메일이 들어오게. 분류 대기가 있으면 자주, 없으면 가끔(탭이 가려지면 멈춤)
      refetchInterval: (q) =>
        refreshInterval(q.state.data?.mails.filter((m) => m.direction === 'received' && m.category === null).length ?? 0, Date.now(), pendingSeen),
    }),
  );
}

export function useNotificationsQuery() {
  return withAvailability(
    useQuery({ queryKey: queryKeys.notifications, queryFn: ({ signal }) => api.getNotifications(signal), retry: shouldRetry }),
  );
}

export function useSettingsQuery() {
  return withAvailability(useQuery({ queryKey: queryKeys.settings, queryFn: ({ signal }) => api.getSettings(signal), retry: shouldRetry }));
}

/** 응답 대기(BE-13 전에는 실제 모드에서 isNotAvailable → 칸을 숨긴다) */
export function useAwaitingQuery() {
  return withAvailability(useQuery({ queryKey: queryKeys.awaiting, queryFn: ({ signal }) => api.getAwaiting(signal), retry: shouldRetry }));
}

/** 메일 한 통. id가 null이면(아무 메일도 안 열림) 부르지 않는다 */
export function useMailQuery(id: MailId | null) {
  return withAvailability(
    useQuery({
      queryKey: queryKeys.mail(id ?? (0 as MailId)),
      queryFn: ({ signal }) => api.getMail(id!, signal),
      enabled: id !== null,
      retry: shouldRetry,
    }),
  );
}

/**
 * 메일 요약. 사용자가 [요약]을 누를 때만 부른다(enabled). 요약은 AI를 부르는 비싼 요청이라 한 번 받으면 다시 받지 않는다.
 * 자동으로 다시 묻지 않는다: 실패하면 '요약하지 못함 [다시 시도]'를 바로 보이고, 다시 시도는 refetch()로 한다
 */
export function useMailSummaryQuery(id: MailId | null, enabled: boolean) {
  return withAvailability(
    useQuery({
      queryKey: queryKeys.mailSummary(id ?? (0 as MailId)),
      queryFn: ({ signal }) => api.summarizeMail(id!, signal),
      enabled: enabled && id !== null,
      staleTime: Infinity,
      retry: false,
    }),
  );
}

// ── 바꾸기(업무 상태는 features/tasks/useTaskActions.ts) ──

export function usePatchNotification() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: NotificationId; patch: NotificationPatch }) => api.patchNotification(id, patch),
    onSuccess: (updated) => {
      client.setQueryData<AppNotification[]>(queryKeys.notifications, (list) => list?.map((n) => (n.id === updated.id ? updated : n)));
    },
  });
}

export function usePatchSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: SettingsPatch) => api.patchSettings(patch),
    onSuccess: (settings) => {
      client.setQueryData<Settings>(queryKeys.settings, settings);
      // 응답 대기 기준 날 수가 바뀌면 응답 대기 목록도 달라진다
      void client.invalidateQueries({ queryKey: queryKeys.awaiting });
    },
  });
}

/** 상급자 · 즐겨찾기 표시. 플래그 칩과 집계가 대시보드 원자료에서 나오므로 그것을 다시 불러온다 */
export function usePatchContact() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ email, patch }: { email: string; patch: ContactPatch }) => api.patchContact(email, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.dashboard }),
  });
}

/**
 * 답장 보내기(FE 제안). 실제 모드에서 서버에 아직 없으면 NotAvailableError — 화면은 보내지 못했다고 알리고 '보냄'으로 꾸미지 않는다.
 * 보낸 답장은 대시보드 원자료(받은 메일 · 업무)를 바꾸지 않으므로 다시 불러오지 않는다. 업무 완료는 완료 확인 시트가 따로 보낸다
 */
/** AI-32 큰 첨부 올리기 */
export function useUploadAttachment() {
  return useMutation({ mutationFn: (file: File) => api.uploadAttachment(file) });
}

/** AI-32 메일 번역(누를 때만) */
/** AI-45 [요약]: 누를 때만. 서버가 저장하므로 메일 한 통 캐시의 summary에도 넣어 다시 부르지 않는다 */
export function useSummarizeMail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: MailId) => api.summarizeMail(id),
    onSuccess: (summary, id) => {
      if (summary) qc.setQueryData(queryKeys.mail(id), (d: { summary: unknown } | undefined) => (d ? { ...d, summary } : d));
    },
  });
}

export function useTranslateMail() {
  return useMutation({ mutationFn: (id: MailId) => api.translateMail(id) });
}

/** 11-15 답장 다듬기(보내지 않는다) */
export function usePolishReply() {
  return useMutation({ mutationFn: ({ id, text }: { id: MailId; text: string }) => api.polishReply(id, text) });
}

/** 답장 · 전체 답장 · 전달(id 있음) 또는 새 메일(id null). 예약이면 예약 목록을 다시 부른다 */
export function useSendReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, draft, mode = 'reply', accountId = null }: { id: MailId | null; draft: ReplyDraft; mode?: ComposeMode; accountId?: number | null }) =>
      mode === 'new' || id === null ? api.sendNewMail(draft, accountId) : api.sendReply(id, draft, mode),
    onSuccess: (r) => (isScheduled(r) ? qc.invalidateQueries({ queryKey: scheduledKey }) : undefined),
  });
}

// ── 에이전트 패널(PL-16) ──

export function useHistoryQuery(days = 7) {
  return withAvailability(useQuery({ queryKey: queryKeys.history(days), queryFn: ({ signal }) => api.getActionHistory(days, signal), staleTime: 0, retry: shouldRetry }));
}

/** 설정 '메일 내용 분석'(11-15): 켜면 받은 메일에서 보낸 사람의 소속 · 담당 업무를 뽑아 DB에 저장한다. 무엇을 아는지는 보여 주지 않는다 */
export function useAgentSettingsQuery() {
  return withAvailability(useQuery({ queryKey: queryKeys.agentSettings, queryFn: ({ signal }) => api.getAgentSettings(signal), retry: shouldRetry }));
}

export function usePatchAgentSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: AgentSettings) => api.patchAgentSettings(patch),
    onSuccess: (r) => client.setQueryData(queryKeys.agentSettings, r),
  });
}

// ── FE-12 캘린더(BE-15) ──

export const calendarKey = (start: string, end: string) => ['calendar', start, end] as const;
/** 화면을 열어 둔 동안 다시 묻는 간격. 미룬 업무는 다시 알릴 시각이 지나면 기한 날짜로 옮겨 보이므로(BE-D24 보완) 그 변화가 1분 안에 보이게 */
export const CALENDAR_REFRESH_MS = 60_000;

/** 캘린더 쿼리 설정(훅과 시험이 같은 값을 쓴다). getCalendar는 시험에서만 바꾼다 */
export function calendarQueryOptions(start: string, end: string, getCalendar: ApiClient['getCalendar'] = (s, e, signal) => api.getCalendar(s, e, signal)) {
  return {
    queryKey: calendarKey(start, end),
    queryFn: ({ signal }: { signal: AbortSignal }) => getCalendar(start, end, signal),
    placeholderData: keepPreviousData,
    staleTime: 0, // 업무를 완료 · 미루면 달력도 바뀌므로 화면에 올 때마다 다시 묻는다
    refetchInterval: CALENDAR_REFRESH_MS, // 화면에 있는 동안만(탭이 가려지면 멈춤). 같은 키라 보던 달 · 고른 날은 그대로
    retry: shouldRetry,
  };
}

/** 달력에 보이는 기간의 기한 · 다시 알림 · 회의 · 일정. 달을 넘기는 동안 앞 달 값을 그대로 보인다(깜빡임 없이) */
export function useCalendarQuery(start: string, end: string) {
  return withAvailability(useQuery(calendarQueryOptions(start, end)));
}

// ── 설정 화면(11-18): 내 정보(읽기만, 로그인한 계정에서 옴) ──

export function useAgentMemoryQuery() {
  return withAvailability(useQuery({ queryKey: queryKeys.agentMemory, queryFn: ({ signal }) => api.getAgentMemory(signal), retry: shouldRetry }));
}

// ── BE-7 메일 계정 · Outlook 연결 ──

export const accountsKey = ['accounts'] as const;

export function useAccountsQuery() {
  return withAvailability(useQuery({ queryKey: accountsKey, queryFn: ({ signal }) => api.getAccounts(signal), retry: shouldRetry }));
}

/** 받은 메일이 바뀌는 동작(동기화 · 연결 끊기) 뒤에는 계정 목록과 대시보드를 다시 부른다 */
function useAccountMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => Promise.all([qc.invalidateQueries({ queryKey: accountsKey }), qc.invalidateQueries({ queryKey: queryKeys.dashboard })]),
  });
}

export function useConnectOutlook() {
  return useMutation({ mutationFn: () => api.connectOutlook() });
}

export function useSyncAccount() {
  return useAccountMutation((id: number) => api.syncAccount(id));
}

export function useDisconnectAccount() {
  return useAccountMutation((id: number) => api.disconnectAccount(id));
}

// ── BE-7 보관함 · 지운 편지함 ──

export const hiddenMailsKey = ['mails', 'hidden'] as const;

export function useHiddenMailsQuery() {
  return withAvailability(useQuery({ queryKey: hiddenMailsKey, queryFn: ({ signal }) => api.getHiddenMails(signal), retry: shouldRetry }));
}

/** 메일함 옮기기. 숨긴 메일의 업무는 대시보드 · 캘린더 · 에이전트 패널에서 빠지거나 돌아오므로 모두 다시 부른다 */
export function useMoveMail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, folder }: { id: MailId; folder: MailFolder }) => api.moveMail(id, folder),
    onSettled: () =>
      Promise.all([hiddenMailsKey, queryKeys.dashboard, queryKeys.agent, ['calendar']].map((queryKey) => qc.invalidateQueries({ queryKey }))),
  });
}

// ── BE-7 단계 2: 예약 보내기 · 첨부 · Outlook 검색 ──

export const scheduledKey = ['scheduled-sends'] as const;

export function useScheduledSendsQuery() {
  return withAvailability(useQuery({ queryKey: scheduledKey, queryFn: ({ signal }) => api.getScheduledSends(signal), retry: shouldRetry, refetchInterval: 60_000 }));
}

export function useCancelScheduled() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: number) => api.cancelScheduledSend(id), onSettled: () => qc.invalidateQueries({ queryKey: scheduledKey }) });
}

export function useAttachmentsQuery(id: MailId) {
  return withAvailability(useQuery({ queryKey: ['mails', id, 'attachments'], queryFn: ({ signal }) => api.getAttachments(id, signal), retry: shouldRetry, staleTime: 5 * 60_000 }));
}

/** 2글자 이상일 때만 Outlook 사서함을 찾는다 */
export function useOutlookSearch(q: string) {
  const term = q.trim();
  return withAvailability(
    useQuery({ queryKey: ['mails', 'search', term], queryFn: ({ signal }) => api.searchOutlook(term, signal), enabled: term.length >= 2, retry: false, staleTime: 60_000 }),
  );
}
