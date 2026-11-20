"""큰 첨부 올리기 `POST /api/uploads` (AI-32 · 아웃룩 파일 첨부 ▾ '이 컴퓨터 찾아보기', 3MB 이상 ~ 150MB).

Graph는 3MB 이상 첨부를 업로드 세션으로만 받는다(learn.microsoft.com/graph/outlook-large-attachments). 그런데 업로드 세션은
보낼 초안이 생긴 뒤에야 만들 수 있다 → 화면은 파일을 먼저 여기로 올리고(본문 그대로, multipart 아님), 보내기 요청에 받은 id만 넣는다.
보내기(services/sending.py)가 초안에 업로드 세션을 만들어 나눠 올리고, 보낸 뒤 파일을 지운다.

- 파일 이름은 X-File-Name 머리(URL 인코딩), 형식은 Content-Type. 본문은 디스크로 바로 흘려 쓴다(메모리에 다 올리지 않는다).
- ponytail: 보내지 않고 버린 파일은 임시 폴더에 남는다(OS 임시 폴더 정리에 맡김). 오래 남는 게 문제면 만든 지 하루 지난 것을 지운다.
"""
import json
import tempfile
import uuid
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.user import current_user_id

router = APIRouter(prefix="/api")

MIN_BYTES = 3 * 1024 * 1024  # 이보다 작으면 기존 첨부(base64, POST .../attachments)로 보낸다
MAX_BYTES = 150 * 1024 * 1024  # Graph 업로드 세션 한도


def upload_dir(user_id: int) -> Path:
    d = Path(tempfile.gettempdir()) / "cne-uploads" / str(user_id)
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
    return path, json.loads(meta.read_text(encoding="utf-8"))


def drop_upload(user_id: int, upload_id: str) -> None:
    if (found := find_upload(user_id, upload_id)) is not None:
        found[0].unlink(missing_ok=True)
        found[0].with_suffix(".json").unlink(missing_ok=True)


class UploadView(BaseModel):
    id: str
    name: str
    size: int


@router.post("/uploads", response_model=UploadView, status_code=201)
async def upload(request: Request, user_id: int = Depends(current_user_id)) -> UploadView:
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
