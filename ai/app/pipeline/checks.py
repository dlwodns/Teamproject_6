"""확인 칸 (AI-D15). 할 일은 아니지만 내가 읽고 확인할 메일을 할 일 목록과 따로 둔다.

칸은 수신 방식(사실)과 모델이 정한 메일 유형으로 배치한다(구조, 모델 판단을 바꾸지 않는다, AI-D19).
- 나에게(받는사람) 온 회신 · 공유 · 공지 → 확인 칸. 회신은 완료든 진행 중이든 어렵다는 답이든 같다 — 안의 내용은 열어서 본다
- 단체 메일 · 참조 · 기타 → 참고(확인 항목 없음)
- 모델이 할 일을 비웠는데 나 혼자 받은 메일에 요청 어미 문장('~ 부탁드립니다')이 있으면 이유를 '요청 문장 있음'으로 띄운다.
  할 일을 만들지 않고 모델 답도 바꾸지 않는다 — 놓친 요청인지는 사람이 본다(누락 안전망, D15, 11/13 유지 결정)
- '필요 없다고 밝힘' · '나를 부르지 않은 참조' · '분류 실패'는 v7까지 규칙이 모델 할 일을 옮기거나 결과를 메울 때 쓰던 이유다.
  AI-D19부터 ai는 내지 않는다(backend에는 예전 데이터 때문에 이유 목록이 남아 있다)
할 일이 있는 메일에는 확인 항목을 만들지 않는다(같은 메일이 두 칸에 뜨지 않게).
"""
import re

from app.pipeline.conditions import Conditions
from app.schemas.classify import CheckOut, ClassifyRequest, TaskOut

SUBJECT_PREFIX = re.compile(r"^\s*(?:(?:RE|Re|re|FW|Fw|FWD|Fwd|회신|전달)\s*:\s*|\[[^\]]*\]\s*)+")


def gist(subject: str) -> str:
    """제목 요지: 회신 · 전달 표시와 머리말([공지] 등) · 끝 괄호를 뺀 제목."""
    g = re.sub(r"\s*\([^)]*\)\s*$", "", SUBJECT_PREFIX.sub("", subject)).strip()
    return (g or subject.strip())[:80]


def build(req: ClassifyRequest, c: Conditions, types: list[str], tasks: list[TaskOut]) -> list[CheckOut]:
    if tasks:
        return []
    if c.recipient != "to" or types[0] not in ("회신", "공유", "공지"):
        return []
    if c.sole_to and c.request_sentence and not c.auto_sent:
        return [CheckOut(text=gist(req.subject), reason="요청 문장 있음", evidence=c.request_sentence)]
    return [CheckOut(text=gist(req.subject), reason=types[0])]
