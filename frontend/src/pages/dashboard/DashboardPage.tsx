import { ConfigError, ContractError, HttpError } from '../../api/errors.ts';
import type { DataOrigin } from '../../api/types.ts';
import { NOTICE_TASK_POLICY, type DashboardView } from '../../features/tasks/aggregate.ts';
import { formatKstFull } from '../../features/tasks/deadline.ts';
import { TaskBlock, TaskRow } from '../../features/tasks/TaskBlock.tsx';
import { useDashboard } from '../../features/tasks/useDashboard.ts';
import { SummaryCards } from './SummaryCards.tsx';

const PRIORITY_ICONS = { due: '⏱', superior: '★', favorite: '♥' } as const;

function errorMessage(error: unknown): string {
  if (error instanceof HttpError) {
    return error.status === 404
      ? `대시보드 API가 아직 준비되지 않았습니다(응답 404). (${error.message})`
      : `서버 오류: ${error.message}`;
  }
  if (error instanceof ContractError) return `응답 형식이 맞지 않습니다: ${error.message}`;
  if (error instanceof ConfigError) return `설정 오류: ${error.message}`;
  if (error instanceof Error) return `불러오지 못했습니다: ${error.message}`;
  return '불러오지 못했습니다.';
}

function Provenance({ origin, asOfMs }: { origin: DataOrigin; asOfMs: number }) {
  return (
    <p className="provenance">
      {origin.kind === 'mock' ? (
        <span className="badge-data">모의 데이터 · {origin.version}</span>
      ) : (
        <span className="badge-data">실제 API · {origin.baseUrl}</span>
      )}
      <span>기준 시각 {formatKstFull(asOfMs)} (KST)</span>
    </p>
  );
}

const MISSING_MAIL_NOTE = '메일 정보가 없는 업무는 분류 · 발신자별 집계에 반영되지 않았습니다(위 \'메일 정보 확인 필요\' 참고).';

/** 업무가 가리키는 메일이 응답에 없을 때만 보인다. 업무는 기한 · 상태와 함께 그대로 보여 주고 분류 · 발신자는 지어내지 않는다. */
function MissingMailNotice({ view }: { view: DashboardView }) {
  const tasks = view.missingMail.tasks;
  if (tasks.length === 0) return null;
  return (
    <section className="card missing-mail" aria-labelledby="missing-mail-title">
      <p className="missing-mail-alert" role="status">
        <span aria-hidden="true">⚠</span> 메일 정보를 불러오지 못한 업무 {tasks.length}건
      </p>
      <h2 id="missing-mail-title">메일 정보 확인 필요</h2>
      <p className="note">
        이 업무들은 기한 · 상태와 기한 집계에는 반영됐지만, 분류 · 발신자를 알 수 없어 상급자 · 즐겨찾기 · 업무 성격 칸에는 넣지 않았습니다.
        원본 메일이 필요한 동작은 메일 정보를 다시 불러온 뒤에 쓸 수 있습니다.
      </p>
      <ul className="tasks">
        {tasks.map((v) => (
          <TaskRow key={v.task.id} view={v} showCategory={false} showStatus />
        ))}
      </ul>
    </section>
  );
}

function Board({ view }: { view: DashboardView }) {
  const missing = view.missingMail.tasks.length > 0;
  const noticeNote =
    NOTICE_TASK_POLICY === 'other'
      ? `공지로 분류된 메일의 업무는 '기타'에 넣습니다(임시 정책 · 지금 해당 ${view.notice.pendingTasks}개).`
      : `공지로 분류된 메일의 업무는 이 열에서 뺍니다(임시 정책 · 지금 해당 ${view.notice.pendingTasks}개, 업무 수에는 포함).`;
  return (
    <div className="board">
      <section className="board-col" aria-labelledby="col-priority">
        <header>
          <h2 id="col-priority">우선 확인</h2>
          <p className="note">기한(지남 · 오늘 · 내일) · 상급자 · 즐겨찾기 발신 업무</p>
          {missing && <p className="note">{MISSING_MAIL_NOTE}</p>}
        </header>
        <div className="blocks">
          {view.priority.map((col) => (
            <TaskBlock key={col.key} column={col} icon={PRIORITY_ICONS[col.key]} showCategory />
          ))}
        </div>
      </section>
      <section className="board-col" aria-labelledby="col-nature">
        <header>
          <h2 id="col-nature">업무 성격</h2>
          <p className="note">업무가 나온 메일의 분류로 칸을 정합니다. {noticeNote}</p>
          {view.unclassifiedPendingTasks > 0 && (
            <p className="note">분류 전 메일의 업무 {view.unclassifiedPendingTasks}개는 '기타'에 넣었습니다.</p>
          )}
          {missing && <p className="note">{MISSING_MAIL_NOTE}</p>}
        </header>
        <div className="blocks">
          {view.nature.map((col) => (
            <TaskBlock key={col.key} column={col} showCategory={false} />
          ))}
        </div>
      </section>
    </div>
  );
}

export function DashboardPage() {
  const { state, reload } = useDashboard();

  return (
    <>
      <div className="page-head">
        <h1 id="page-title" tabIndex={-1}>
          대시보드
        </h1>
        {state.kind === 'ready' && <Provenance origin={state.origin} asOfMs={state.view.asOfMs} />}
      </div>

      {state.kind === 'loading' && (
        <div className="card status-view" role="status" data-kind="loading">
          <p>업무를 불러오는 중입니다…</p>
        </div>
      )}

      {state.kind === 'error' && (
        <div className="card status-view" role="alert" data-kind="error">
          <p>
            <strong>
              <span aria-hidden="true">⚠</span> 대시보드를 불러오지 못했습니다.
            </strong>
          </p>
          <p className="note">{errorMessage(state.error)}</p>
          <button type="button" className="btn" onClick={reload}>
            다시 시도
          </button>
        </div>
      )}

      {state.kind === 'ready' && state.view.taskCount === 0 && (
        <div className="card status-view" role="status" data-kind="empty">
          <p>
            <strong>표시할 업무가 없습니다.</strong>
          </p>
          <p className="note">메일 {state.view.mailCount}통 · 업무 0개</p>
        </div>
      )}

      {state.kind === 'ready' && state.view.taskCount > 0 && (
        <>
          <MissingMailNotice view={state.view} />
          {state.view.due.overdue > 0 && (
            <p className="alert">
              <span aria-hidden="true">⚠</span> 기한이 지난 업무 {state.view.due.overdue}개가 있습니다
            </p>
          )}
          <SummaryCards view={state.view} />
          <Board view={state.view} />
          <p className="note" style={{ marginTop: 16 }}>
            같은 업무가 여러 칸에 보일 수 있어 칸별 건수의 합은 전체 업무 수와 다릅니다. 완료 처리 · 되돌리기 · 원본 메일 보기는 준비 중입니다.
          </p>
        </>
      )}
    </>
  );
}
