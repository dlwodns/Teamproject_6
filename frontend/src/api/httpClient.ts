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
  toSentReply,
  toSettings,
  toUndoResult,
} from './adapter.ts';
import type { ApiClient } from './contract.ts';
import { AgentUnavailableError, ContractError, HttpError, NetworkError, NotAvailableError } from './errors.ts';

const NOT_AVAILABLE_STATUSES = new Set([404, 405, 501]);

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: unknown;
  signal?: AbortSignal;
  /** FE 제안 요청이면 true(404 · 405 · 501 → NotAvailableError) */
  proposed: boolean;
}

export function createHttpApi(baseUrl: string): ApiClient {
  async function request(path: string, { method = 'GET', body, signal, proposed }: RequestOptions): Promise<unknown> {
    const url = `${baseUrl}${path}`;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res: Response;
    try {
      res = await fetch(url, { method, headers, signal, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      // 요청 경계에서만 구분한다: 취소는 그대로(화면이 무시), fetch의 TypeError는 네트워크 실패.
      // 이 밖(응답 읽기 · 변환)에서 나는 TypeError는 프로그래밍 오류라 NetworkError로 바꾸지 않는다
      if (signal?.aborted) throw e;
      if (e instanceof TypeError) throw new NetworkError('서버에 연결하지 못했다', { cause: e });
      throw e;
    }
    if (!res.ok) {
      if (proposed && NOT_AVAILABLE_STATUSES.has(res.status)) throw new NotAvailableError(path, res.status);
      throw new HttpError(res.status, `${url} 응답 ${res.status}`);
    }
    try {
      return await res.json();
    } catch {
      throw new ContractError('응답이 JSON이 아니다');
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
        return toAgentResult(await request('/agent/command', { method: 'POST', body: agentCommandBody(req), signal, proposed: false }));
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
      return toMailSummary(await request(`/mails/${id(mailId)}/summary`, { method: 'POST', signal, proposed: true }));
    },
    async sendReply(mailId, draft) {
      return toSentReply(await request(`/mails/${id(mailId)}/reply`, { method: 'POST', body: replyBody(draft), proposed: true }));
    },
  };
}
