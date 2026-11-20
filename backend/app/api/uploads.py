"""큰 첨부 올리기 `POST /api/uploads` (AI-32 · 아웃룩 파일 첨부 ▾ '이 컴퓨터 찾아보기', 3MB 이상 ~ 150MB).

Graph는 3MB 이상 첨부를 업로드 세션으로만 받는다(learn.microsoft.com/graph/outlook-large-attachments). 그런데 업로드 세션은
보낼 초안이 생긴 뒤에야 만들 수 있다 → 화면은 파일을 먼저 여기로 올리고(본문 그대로, multipart 아님), 보내기 요청에 받은 id만 넣는다.
보내기(services/sending.py)가 초안에 업로드 세션을 만들어 나눠 올리고, 보낸 뒤 파일을 지운다.

- 파일 이름은 X-File-Name 머리(URL 인코딩), 형식은 Content-Type. 본문은 디스크로 바로 흘려 쓴다(메모리에 다 올리지 않는다).
- 보내지 않고 버린 파일은 새로 올릴 때 sweep()이 지운다(마지막으로 쓴 지 KEEP_S 지난 것, AI-35). 예약 보내기(pending · sending)가
  잡고 있는 파일은 남기고, 보내는 중인 파일은 find_upload가 시각을 새로 찍어 건드리지 않는다.
  ponytail: 올리기가 있을 때만 돈다. 아무도 안 올리면 남는다 — 문제면 작업자(jobs/worker.py) 주기에 붙인다.
"""
import json
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.user import current_user_id
from app.models import ScheduledSend

router = APIRouter(prefix="/api")

MIN_BYTES = 3 * 1024 * 1024  # 이보다 작으면 기존 첨부(base64, POST .../attachments)로 보낸다
MAX_BYTES = 150 * 1024 * 1024  # Graph 업로드 세션 한도
KEEP_S = 24 * 3600  # 보내지 않은 큰 첨부를 남겨 두는 시간


def upload_root() -> Path:
    return Path(tempfile.gettempdir()) / "cne-uploads"


def upload_dir(user_id: int) -> Path:
    d = upload_root() / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_upload(user_id: int, upload_id: str) -> tuple[Path, dict] | None:
    """올린 파일(경로, {name, content_type, size}). 다른 사용자 것 · 없는 id는 None."""
    try:
        uuid.UUID(hex=upload_id)
    except ValueError:
        return None
    path = upload_dir(user_id) / upload_id
    meta = path.with_suffix(".json")
    if not path.is_file() or not meta.is_file():
        return None
    path.touch()  # 쓰는 중 — sweep이 지우지 않게 시각을 새로 찍는다
    meta.touch()
    return path, json.loads(meta.read_text(encoding="utf-8"))


def drop_upload(user_id: int, upload_id: str) -> None:
    if (found := find_upload(user_id, upload_id)) is not None:
        found[0].unlink(missing_ok=True)
        found[0].with_suffix(".json").unlink(missing_ok=True)


def sweep(db: Session, keep_s: int = KEEP_S) -> int:
    """마지막으로 쓴 지 keep_s 지난 업로드 파일(본문 · .json, 올리다 끊긴 것 포함)을 지운다. 예약 보내기가 잡고 있는 것은 남긴다."""
    held = {i for req in db.scalars(select(ScheduledSend.request_json)
                                    .where(ScheduledSend.status.in_(("pending", "sending"))))
            for i in (req or {}).get("large_attachments", [])}
    cut = time.time() - keep_s
    n = 0
    for f in upload_root().glob("*/*"):
        try:
            if f.stem not in held and f.stat().st_mtime < cut:
                f.unlink()
                n += 1
        except OSError:  # 다른 요청이 먼저 지웠거나(없음) Windows에서 열려 있는 파일
            pass
    return n


class UploadView(BaseModel):
    id: str
    name: str
    size: int


@router.post("/uploads", response_model=UploadView, status_code=201)
async def upload(request: Request, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> UploadView:
    await run_in_threadpool(sweep, db)  # DB 조회 · 파일 훑기가 이벤트 루프를 멈추지 않게
    name = unquote(request.headers.get("x-file-name", "")).strip()[:255]
    if not name:
        raise HTTPException(422, "X-File-Name이 필요합니다")
    declared = request.headers.get("content-length") or "0"
    if not declared.isdigit():
        raise HTTPException(400, "Content-Length가 숫자가 아닙니다")
    if int(declared) > MAX_BYTES:
        raise HTTPException(413, "첨부는 한 파일에 150MB까지입니다")
    upload_id = uuid.uuid4().hex
    path = upload_dir(user_id) / upload_id
    size = 0
    with path.open("wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                f.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, "첨부는 한 파일에 150MB까지입니다")
            f.write(chunk)
    if size < MIN_BYTES:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "3MB 미만 파일은 일반 첨부로 보냅니다")
    ctype = (request.headers.get("content-type") or "application/octet-stream")[:100]
    path.with_suffix(".json").write_text(json.dumps({"name": name, "content_type": ctype, "size": size}), encoding="utf-8")
    return UploadView(id=upload_id, name=name, size=size)
