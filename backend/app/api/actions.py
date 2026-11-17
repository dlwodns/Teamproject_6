"""업무 상태 변경 · 일괄 변경(미리보기 → 실행) · 되돌리기 API (BE-4, 구조도 v3.1 8절 ③).

- 1건 변경(PATCH)은 바로 실행하고 되돌리기용 action_id를 준다.
- 여러 건 변경은 미리보기(preview)로 확인창을 띄운 뒤 실행(execute)한다(D37).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.clock import as_kst, to_kst_naive
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.models import ActionPreview, Task
from app.schemas.actions import (ActionResult, BulkPreviewRequest, ExecuteRequest, PreviewResult, PreviewTarget,
                                 StatusChange, TaskState, UndoResult)
from app.services import nudge, task_status
from app.services.task_status import StatusError

router = APIRouter(prefix="/api")
HTTP = {"not_found": 404, "conflict": 409, "invalid": 422}


def _state(t: Task) -> TaskState:
    return TaskState(id=t.id, status=t.status, done_at=as_kst(t.done_at), snoozed_until=as_kst(t.snoozed_until),
                     status_changed_at=as_kst(t.status_changed_at))


def _run(db: Session, fn, *args, **kwargs):
    try:
        out = fn(db, *args, **kwargs)
    except StatusError as e:
        db.rollback()
        raise HTTPException(HTTP[e.kind], str(e)) from None
    db.commit()
    return out


def _until(body: StatusChange):
    return to_kst_naive(body.snoozed_until) if body.snoozed_until else None


@router.patch("/tasks/{task_id}", response_model=ActionResult)
def patch_task(task_id: Id, body: StatusChange, user_id: int = Depends(current_user_id),
               db: Session = Depends(get_db)) -> ActionResult:
    log, tasks = _run(db, task_status.change_status, [task_id], body.status, _until(body), via=body.via, owner=user_id)
    return ActionResult(action_id=log.id if log else None, tasks=[_state(t) for t in tasks])


@router.post("/tasks/bulk/preview", response_model=PreviewResult)
def bulk_preview(body: BulkPreviewRequest, user_id: int = Depends(current_user_id),
                 db: Session = Depends(get_db)) -> PreviewResult:
    p, tasks = _run(db, task_status.preview, body.task_ids, body.status, _until(body), via=body.via, owner=user_id)
    return PreviewResult(preview_id=p.preview_id, expires_at=as_kst(p.expires_at), status=body.status,
                         snoozed_until=as_kst(_until(body)),
                         targets=[PreviewTarget(id=t.id, text=t.text, status=t.status) for t in tasks])


@router.post("/actions/execute", response_model=ActionResult)
def execute(body: ExecuteRequest, user_id: int = Depends(current_user_id),
            db: Session = Depends(get_db)) -> ActionResult:
    p = db.get(ActionPreview, body.preview_id)
    if p is not None and p.action == nudge.ACTION:  # 재촉 메일(T14): 확인한 미리보기를 보낸다(D37)
        if body.task_ids is not None:
            raise HTTPException(422, "재촉 메일 미리보기는 mail_ids로 고릅니다")
        out = _run(db, nudge.execute, body.preview_id, owner=user_id, mail_ids=body.mail_ids)
        return ActionResult(action_id=None, tasks=[], **out)
    if body.mail_ids is not None:
        raise HTTPException(422, "mail_ids는 재촉 메일 미리보기에만 씁니다")
    log, tasks = _run(db, task_status.execute, body.preview_id, task_ids=body.task_ids, owner=user_id)
    return ActionResult(action_id=log.id if log else None, tasks=[_state(t) for t in tasks])


@router.post("/actions/{action_id}/undo", response_model=UndoResult)
def undo(action_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> UndoResult:
    log, back, tasks = _run(db, task_status.undo, action_id, owner=user_id)
    return UndoResult(action_id=back.id, undone_action_id=log.id, tasks=[_state(t) for t in tasks])
