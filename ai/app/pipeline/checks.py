"""확인 칸 (AI-D15). 할 일은 아니지만 내가 읽고 확인할 메일을 할 일 목록과 따로 둔다.

칸은 수신 조건과 메일 유형으로만 정한다(해석하지 않는다, 11/7 사용자 결정).
- 나에게(받는사람) 온 회신 · 공유 · 공지 → 확인 칸. 회신은 완료든 진행 중이든 어렵다는 답이든 같다 — 안의 내용은 열어서 본다
- 단체 메일 · 참조 · 기타 → 참고(확인 항목 없음)
- 모델이 할 일을 비웠는데 나 혼자 받은 메일에 요청 어미 문장('~ 부탁드립니다')이 있으면 이유를 '요청 문장 있음'으로 띄운다.
  할 일을 만들지 않는다 — 놓친 요청인지는 사람이 본다(누락 안전망, D15)
- 모델 할 일이었지만 본문이 조건 없이 필요 없다고 밝혀 옮긴 것 → '필요 없다고 밝힘'(받는 방식과 상관없이 버리지 않는다)
- 참조로 받았는데 내 이름 · 팀 · 직책 글자가 없어 옮긴 모델 할 일 → '나를 부르지 않은 참조'(11/8)
- 모델 호출이 실패한 메일 → '분류 실패'(받는 방식과 상관없이, 다시 시도 대상)
할 일이 남은 메일에는 확인 항목을 만들지 않는다(같은 메일이 두 칸에 뜨지 않게).
"""
import re

from app.pipeline.conditions import Conditions
from app.schemas.classify import CheckOut, ClassifyRequest, TaskOut

SUBJECT_PREFIX = re.compile(r"^\s*(?:(?:RE|Re|re|FW|Fw|FWD|Fwd|회신|전달)\s*:\s*|\[[^\]]*\]\s*)+")


def gist(subject: str) -> str:
    """제목 요지: 회신 · 전달 표시와 머리말([공지] 등) · 끝 괄호를 뺀 제목."""
    g = re.sub(r"\s*\([^)]*\)\s*$", "", SUBJECT_PREFIX.sub("", subject)).strip()
    return (g or subject.strip())[:80]


def build(req: ClassifyRequest, c: Conditions, types: list[str], tasks: list[TaskOut],
          moved: list[tuple[TaskOut, str, str | None]], mail_type: str | None, failed: bool = False) -> list[CheckOut]:
    if tasks:
        return []
    if failed:
        return [CheckOut(text=gist(req.subject), reason="분류 실패")]
    if moved:
        return [CheckOut(text=t.text, reason=why, evidence=ev, source="exaone") for t, why, ev in moved]
    if c.recipient != "to" or types[0] not in ("회신", "공유", "공지"):
        return []
    if c.sole_to and c.request_sentence and not c.auto_sent:
        return [CheckOut(text=gist(req.subject), reason="요청 문장 있음", evidence=c.request_sentence)]
    return [CheckOut(text=gist(req.subject), reason=types[0])]
