// 실제 모드: backend를 부른다. 개발 서버에서는 Vite 프록시(vite.config.ts)가 /api/... 를 backend로 넘긴다.
// 실패하면 오류를 그대로 올린다. 모의 데이터로 대신하지 않는다.
// ai 서비스는 부르지 않는다(backend만 부른다, D34).
//
// 요청마다 계약 표(components.md 5.1)의 상태를 적었다.
//   있음:    backend에 있다. 404도 그대로 HttpError(없는 업무 등 진짜 오류라서)
//   FE 제안: backend에 아직 없을 수 있다. 404 · 405 · 501은 NotAvailableError → 화면이 그 부분을 숨긴다.
//            backend가 만들면 그 요청의 proposed를 false로 바꾼다(그 뒤의 404는 '없는 메일' 같은 진짜 오류)
import {
  agentCommandBody,
  bulkPreviewBody,
  executeBody,
  contactPatchBody,
  replyBody,
  settingsPatchToRaw,
  statusChangeBody,
  toActionResult,
  toAgentResult,
  toAwaitingList,
  toBulkPreview,
  toContact,
  toDashboardSource,
  toMailDetail,
  toMailSummary,
  toNotification,
  toNotifications,
  toPolishedReply,
  toMailTranslation,
  toUploadedFile,
  toSettings,
  toUndoResult,
  memoryMePatchBody,
  memoryPersonPatchBody,
  toAgentMemory,
  toAgentSettings,
  toHideResult,
  toHistoryList,
  toMemoryChange,
  toSuggestionList,
  mailPatchBody,
  toMailItem,
} from './adapter.ts';
import type { ApiClient } from './contract.ts';
import { calendarEventBody, toCalendarEventResult, toCalendarRange } from './adapter.ts'; // FE-12 캘린더(BE-15)
import { toAccountSyncResult, toConnectUrl, toMailAccount, toMailAccounts, toMailList } from './adapter.ts'; // BE-7 메일 계정 · 보관함
import { toAttachments, toScheduledSend, toScheduledSends, toSearchHits, toSendResult } from './adapter.ts'; // BE-7 단계 2
import { AgentUnavailableError, ContractError, HttpError, NetworkError, NotAvailableError } from './errors.ts';

const NOT_AVAILABLE_STATUSES = new Set([404, 405, 501]);

/** 요청 제한 시간(FE-D14). 응답 헤더 · 본문을 다 받을 때까지 센다. */
export const REQUEST_TIMEOUT_MS = 15_000;
/** 모델을 부르는 요청(에이전트 명령 · 메일 요약)과 메일 보내기는 더 기다린다.
 *  backend가 ai를 130초까지 기다리므로(ai_client TIMEOUT_S) 그보다 길게 잡아, 늦으면 화면이 먼저 끊지 않고 backend의 503을 받는다 */
export const SLOW_REQUEST_TIMEOUT_MS = 140_000;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  /** FE 제안 요청이면 true(404 · 405 · 501 → NotAvailableError) */
  proposed: boolean;
  /** 제한 시간(ms). 기본 REQUEST_TIMEOUT_MS */
  timeoutMs?: number;
  /** 파일을 본문 그대로 보낸다(AI-32 큰 첨부 POST /api/uploads). 이름은 X-File-Name(URL 인코딩) */
  file?: File;
}

export function createHttpApi(baseUrl: string, userId = '1'): ApiClient {
  async function request(
    path: string,
    { method = 'GET', body, signal, proposed, timeoutMs = REQUEST_TIMEOUT_MS, file }: RequestOptions,
  ): Promise<unknown> {
    const url = `${baseUrl}${path}`;
    // 모든 요청에 사용자 번호를 붙인다. 운영 모드 backend는 이 헤더가 없으면 업무 변경 · 되돌리기 · 명령을 401로 막는다(#53 리뷰).
    // 로그인(BE-6)이 생기면 이 한 줄만 토큰으로 바꾼다
    const headers: Record<string, string> = { Accept: 'application/json', 'X-User-Id': userId };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (file) {
      headers['Content-Type'] = file.type || 'application/octet-stream';
      headers['X-File-Name'] = encodeURIComponent(file.name);
    }

    // 화면 쪽 취소 신호와 제한 시간 신호를 함께 건다. 어느 쪽이 걸렸는지는 따로 기억한다:
    // 화면 취소는 그대로 올리고(화면이 무시), 제한 시간 초과는 연결 실패(NetworkError)로 올린다.
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort(new DOMException('요청 제한 시간 초과', 'TimeoutError'));
    }, timeoutMs);
    const onCancel = () => controller.abort(signal?.reason);
    if (signal?.aborted) onCancel();
    else signal?.addEventListener('abort', onCancel, { once: true });
    const timeoutError = (cause: unknown) => new NetworkError(`서버가 ${timeoutMs / 1000}초 안에 응답하지 않았다`, { cause });

    try {
      let res: Response;
      try {
        res = await fetch(url, { method, headers, signal: controller.signal, body: file ?? (body === undefined ? undefined : JSON.stringify(body)) });
      } catch (e) {
        // 요청 경계에서만 구분한다: 취소는 그대로(화면이 무시), 제한 시간 초과 · fetch의 TypeError는 네트워크 실패.
        // 이 밖(응답 읽기 · 변환)에서 나는 TypeError는 프로그래밍 오류라 NetworkError로 바꾸지 않는다
        if (signal?.aborted) throw e;
        if (timedOut) throw timeoutError(e);
        if (e instanceof TypeError) throw new NetworkError('서버에 연결하지 못했다', { cause: e });
        throw e;
      }
      if (!res.ok) {
        if (proposed && NOT_AVAILABLE_STATUSES.has(res.status)) throw new NotAvailableError(path, res.status);
        throw new HttpError(res.status, `${url} 응답 ${res.status}`);
      }
      try {
        return await res.json();
      } catch (e) {
        // 본문을 읽다가 끊긴 것은 형식 오류가 아니다: 화면 취소는 그대로, 제한 시간 초과는 NetworkError
        if (signal?.aborted) throw e;
        if (timedOut) throw timeoutError(e);
        throw new ContractError('응답이 JSON이 아니다');
      }
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onCancel);
    }
  }

  const id = (v: number | string) => encodeURIComponent(String(v));

  return {
    // 있음(BE-3 #47). 응답 형식은 provisional.ts(FE 임시 계약)를 그대로 따른다
    async getDashboard(signal) {
      return toDashboardSource(await request('/dashboard', { signal, proposed: false }), { kind: 'http', baseUrl });
    },

    // 있음(BE-4) — 요청 · 응답은 backend/app/schemas/actions.py 그대로
    async patchTaskStatus(taskId, change) {
      return toActionResult(await request(`/tasks/${id(taskId)}`, { method: 'PATCH', body: statusChangeBody(change), proposed: false }));
    },
    async bulkPreview(req) {
      return toBulkPreview(await request('/tasks/bulk/preview', { method: 'POST', body: bulkPreviewBody(req), proposed: false }));
    },
    async executeAction(previewId, taskIds) {
      return toActionResult(await request('/actions/execute', { method: 'POST', body: executeBody(previewId, taskIds), proposed: false }));
    },
    async undoAction(actionId) {
      return toUndoResult(await request(`/actions/${id(actionId)}/undo`, { method: 'POST', proposed: false }));
    },

    // 있음(BE-11 #50). 503은 'AI를 쓸 수 없음'(상태 안 바뀜)이라 따로 구분한다. 모의로 대신하지 않는다
    async runAgentCommand(req, signal) {
      try {
        return toAgentResult(await request('/agent/command', { method: 'POST', body: agentCommandBody(req), signal, proposed: false, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
      } catch (e) {
        if (e instanceof HttpError && e.status === 503) throw new AgentUnavailableError();
        throw e;
      }
    },

    // FE 제안
    async getNotifications(signal) {
      return toNotifications(await request('/notifications', { signal, proposed: true }));
    },
    async patchNotification(notificationId, patch) {
      return toNotification(await request(`/notifications/${id(notificationId)}`, { method: 'PATCH', body: patch, proposed: true }));
    },
    async getSettings(signal) {
      return toSettings(await request('/settings', { signal, proposed: true }));
    },
    async patchSettings(patch) {
      return toSettings(await request('/settings', { method: 'PATCH', body: settingsPatchToRaw(patch), proposed: true }));
    },
    async patchContact(email, patch) {
      return toContact(await request(`/contacts/${id(email)}`, { method: 'PATCH', body: contactPatchBody(patch), proposed: true }), '응답');
    },
    async getAwaiting(signal) {
      return toAwaitingList(await request('/awaiting', { signal, proposed: true }));
    },
    async getMail(mailId, signal) {
      return toMailDetail(await request(`/mails/${id(mailId)}`, { signal, proposed: true }));
    },
    async summarizeMail(mailId, signal) {
      return toMailSummary(await request(`/mails/${id(mailId)}/summary`, { method: 'POST', signal, proposed: true, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
    },
    async sendReply(mailId, draft, mode = 'reply') {
      const path = { reply: 'reply', replyAll: 'reply-all', forward: 'forward' }[mode];
      return toSendResult(await request(`/mails/${id(mailId)}/${path}`, { method: 'POST', body: replyBody(draft, mode), proposed: true, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
    },
    async sendNewMail(draft, accountId) {
      const body = { ...replyBody(draft, 'new'), account_id: accountId };
      return toSendResult(await request('/mails', { method: 'POST', body, proposed: true, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
    },
    async uploadAttachment(file) {
      // 150MB를 느린 연결로 올릴 수 있어 넉넉히(10분)
      const r = await request('/uploads', { method: 'POST', file, proposed: true, timeoutMs: 600_000 });
      return toUploadedFile(r);
    },
    async dropUpload(uploadId) {
      await request(`/uploads/${encodeURIComponent(uploadId)}`, { method: 'DELETE', proposed: true });
    },
    async translateMail(mailId) {
      // 긴 메일은 번역문 생성이 130초를 넘는다(AI-32 실측) → 서버 백그라운드 대기(310초)보다 조금 길게
      return toMailTranslation(await request(`/mails/${id(mailId)}/translate`, { method: 'POST', proposed: false, timeoutMs: 320_000 }));
    },

    async polishReply(mailId, text) {
      const r = await request(`/mails/${id(mailId)}/polish`, { method: 'POST', body: { text, style: 'polite' }, proposed: false, timeoutMs: SLOW_REQUEST_TIMEOUT_MS });
      return toPolishedReply(r);
    },

    // 있음(PL-16 #44) — backend/app/api/agent.py · docs/30_backend/agent_api_contract.md
    async getSuggestions(limit, signal) {
      return toSuggestionList(await request(`/suggestions?limit=${id(limit)}`, { signal, proposed: false }));
    },
    async hideSuggestion(key) {
      return toHideResult(await request(`/suggestions/${id(key)}/hide`, { method: 'POST', proposed: false }));
    },
    // BE-15(#74) 캘린더. #74를 먼저 머지한 뒤 이 PR을 머지한다(그 뒤의 404는 '없는 일정' 같은 진짜 오류)
    async getCalendar(start, end, signal) {
      return toCalendarRange(await request(`/calendar?start=${id(start)}&end=${id(end)}`, { signal, proposed: false }));
    },
    async addCalendarEvent(req) {
      return toCalendarEventResult(await request('/calendar/events', { method: 'POST', body: calendarEventBody(req), proposed: false }));
    },
    async removeCalendarEvent(eventId) {
      return toCalendarEventResult(await request(`/calendar/events/${id(eventId)}`, { method: 'DELETE', proposed: false }));
    },

    async getActionHistory(days, signal) {
      return toHistoryList(await request(`/actions/history?days=${id(days)}`, { signal, proposed: false }));
    },
    async getAgentMemory(signal) {
      return toAgentMemory(await request('/agent/memory', { signal, proposed: false }));
    },
    async patchAgentMemoryMe(patch) {
      return toMemoryChange(await request('/agent/memory/me', { method: 'PATCH', body: memoryMePatchBody(patch), proposed: false }));
    },
    async patchAgentMemoryPerson(contactId, patch) {
      return toMemoryChange(
        await request(`/agent/memory/people/${id(contactId)}`, { method: 'PATCH', body: memoryPersonPatchBody(patch), proposed: false }),
      );
    },
    async getAgentSettings(signal) {
      return toAgentSettings(await request('/agent/settings', { signal, proposed: false }));
    },
    async patchAgentSettings(patch) {
      return toAgentSettings(await request('/agent/settings', { method: 'PATCH', body: { learn_from_mail: patch.learnFromMail }, proposed: false }));
    },

    // ── FE-5d 메일 읽음 · 고정(FE 제안) ──
    async patchMail(mailId, patch) {
      return toMailItem(await request(`/mails/${id(mailId)}`, { method: 'PATCH', body: mailPatchBody(patch), proposed: true }));
    },

    // ── BE-7 메일 계정 · Outlook 연결 ──
    async getAccounts(signal) {
      return toMailAccounts(await request('/accounts', { signal, proposed: true }));
    },
    async connectOutlook() {
      // 서버가 더미 모드면 501 → NotAvailableError(화면이 연결 버튼 대신 안내)
      return toConnectUrl(await request('/accounts/outlook/connect', { method: 'POST', proposed: true }));
    },
    async syncAccount(accountId) {
      return toAccountSyncResult(await request(`/accounts/${id(accountId)}/sync`, { method: 'POST', proposed: false, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
    },
    async disconnectAccount(accountId) {
      return toMailAccount(await request(`/accounts/${id(accountId)}/disconnect`, { method: 'POST', proposed: false }));
    },
    async getHiddenMails(signal) {
      return toMailList(await request('/mails/hidden', { signal, proposed: false }));
    },
    async moveMail(mailId, folder) {
      return toMailItem(await request(`/mails/${id(mailId)}/move`, { method: 'POST', body: { folder }, proposed: false }));
    },

    // ── BE-7 단계 2: 예약 보내기 · 첨부 · Outlook 검색 ──
    async getScheduledSends(signal) {
      return toScheduledSends(await request('/scheduled-sends', { signal, proposed: true }));
    },
    async cancelScheduledSend(scheduledId) {
      return toScheduledSend(await request(`/scheduled-sends/${id(scheduledId)}`, { method: 'DELETE', proposed: false }));
    },
    async getAttachments(mailId, signal) {
      return toAttachments(await request(`/mails/${id(mailId)}/attachments`, { signal, proposed: true, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
    },
    async downloadAttachment(mailId, attId) {
      // 파일이라 JSON request()를 쓰지 않는다. 사용자 번호 머리글은 같게 붙인다
      let res: Response;
      try {
        res = await fetch(`${baseUrl}/mails/${id(mailId)}/attachments/${id(attId)}`, { headers: { 'X-User-Id': userId } });
      } catch (e) {
        throw new NetworkError('서버에 연결하지 못했다', { cause: e });
      }
      if (!res.ok) throw new HttpError(res.status, `첨부 응답 ${res.status}`);
      return res.blob();
    },
    async searchOutlook(q, signal) {
      return toSearchHits(await request(`/mails/search?${new URLSearchParams({ q }).toString()}`, { signal, proposed: true, timeoutMs: SLOW_REQUEST_TIMEOUT_MS }));
    },

    ...reminderHttp(request, id), // FE-16 리마인더(파일 끝)
  };
}

// ── 리마인더 (FE-16 · BE-12 계약) ──
// 모두 FE 제안(docs/10_planning/reminders.md 7.2절). BE-12가 만들기 전에는 404 · 405 · 501 → NotAvailableError → 화면이 숨긴다.
// 만들어지면 proposed를 false로 바꾼다(그 뒤의 404는 '없는 항목' 같은 진짜 오류).
import {
  dismissBody,
  toBriefing,
  toReadAllCount,
  toReminderChange,
  toReminderList,
  toReminderTypeNotify,
} from './adapter.ts';

type HttpRequest = (path: string, options: RequestOptions) => Promise<unknown>;

function reminderHttp(request: HttpRequest, id: (v: number | string) => string): Pick<
  ApiClient,
  'getReminders' | 'dismissReminder' | 'applyReminder' | 'setReminderTypeNotify' | 'getBriefing' | 'readAllNotifications'
> {
  return {
    async getReminders(group, signal) {
      return toReminderList(await request(`/reminders?group=${id(group)}`, { signal, proposed: true }));
    },
    async dismissReminder(key, reason) {
      return toReminderChange(await request(`/reminders/${id(key)}/dismiss`, { method: 'POST', body: dismissBody(reason), proposed: true }));
    },
    async applyReminder(key) {
      return toReminderChange(await request(`/reminders/${id(key)}/apply`, { method: 'POST', proposed: true }));
    },
    async setReminderTypeNotify(type, notify) {
      return toReminderTypeNotify(await request(`/reminders/types/${id(type)}`, { method: 'PATCH', body: { notify }, proposed: true }));
    },
    async getBriefing(kind, date, signal) {
      return toBriefing(await request(`/briefings/${id(kind)}?date=${id(date)}`, { signal, proposed: true }));
    },
    async readAllNotifications() {
      return toReadAllCount(await request('/notifications/read-all', { method: 'POST', proposed: true }));
    },
  };
}
