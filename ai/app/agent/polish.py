"""답장 다듬기 (POST /polish). 사용자가 쓴 글을 고른 방식대로 고친다. 표시용이고 보내지 않는다(발송은 사용자, D37).

모델 결과는 그대로 믿지 않는다. 아래 중 하나라도 걸리면 받은 글을 그대로 돌려준다(지어낸 내용보다 안 고친 글이 낫다).
- 빈 글 · 너무 긴 글(받은 글의 3배 + 200자 초과)
- 받은 글에 없던 숫자(날짜 · 시각 · 금액 · 번호)가 생김
- 가려 둔 값([전화번호 1] · 김◯◯ · user1@…)이 사라지거나, 받은 글 · 원 메일 어디에도 없던 가린 값이 생김
  (원 메일의 이름은 써도 된다: 정중하게 고치면 "김◯◯ 팀장님께" 인사가 붙을 수 있다. 숫자는 원 메일에서도 옮기지 않는다)
"""
import re

from app.llm.client import LLMClient, LLMError
from app.prompts import polish_v1 as prompts
from app.schemas.assist import PolishRequest, PolishResponse

_DIGITS = re.compile(r"\d+")
# backend 개인정보 가리기(BE-6)가 만든 대체어. 하나도 잃거나 새로 만들면 안 된다
_MASKED = re.compile(r"\[(?:전화번호|주민번호|카드번호) \d+\]|[가-힣A-Za-z]◯◯\d*|user\d+@[A-Za-z0-9.-]+")
_LIST_MARK = re.compile(r"^\s*\d+[.)]\s", re.M)  # '쉽게 정리'가 붙이는 줄 앞 번호(1. 2.)는 지어낸 숫자가 아니다
_WRAP = re.compile(r'^\s*(?:["“”\'`]+)|(?:["“”\'`]+)\s*$')


def _user_prompt(req: PolishRequest) -> str:
    name, how = prompts.STYLES[req.style]
    parts = [f"다듬기 방식: {name} — {how}"]
    if req.mail:
        parts.append(f"원 메일 제목: {req.mail.subject}\n원 메일 본문(맥락만):\n{req.mail.body[:3000]}")
    parts.append(f"내가 쓴 글:\n{req.text}")
    return "\n\n".join(parts)


def check(before: str, after: str, context: str = "") -> str | None:
    """모델 결과를 쓸 수 없으면 그 이유, 쓸 수 있으면 None. context는 원 메일(가린 이름을 써도 되는 곳)."""
    if not after.strip():
        return "빈 결과"
    if len(after) > len(before) * 3 + 200:
        return "너무 긴 결과"
    if new := sorted(set(_DIGITS.findall(_LIST_MARK.sub("", after))) - set(_DIGITS.findall(before))):
        return f"받은 글에 없던 숫자 {len(new)}개"
    b, a = set(_MASKED.findall(before)), set(_MASKED.findall(after))
    if b - a:
        return f"가려 둔 값 {len(b - a)}개가 사라짐"
    if a - b - set(_MASKED.findall(context)):
        return f"없던 가린 값 {len(a - b)}개가 생김"
    return None


def polish(req: PolishRequest, llm: LLMClient) -> PolishResponse:
    same = PolishResponse(text=req.text, style=req.style, changed=False, source="none",
                          prompt_version=prompts.PROMPT_VERSION)
    try:
        out = llm.chat_json(prompts.SYSTEM, _user_prompt(req), prompts.SCHEMA)
    except LLMError as e:
        return same.model_copy(update={"fallback": f"모델 호출 실패: {e}"})
    text = _WRAP.sub("", str(out.get("text", ""))).strip()
    context = f"{req.mail.subject}\n{req.mail.sender or ''}\n{req.mail.body}" if req.mail else ""
    if reason := check(req.text, text, context):
        return same.model_copy(update={"fallback": reason})
    return PolishResponse(text=text, style=req.style, changed=text != req.text.strip(), source="exaone",
                          prompt_version=prompts.PROMPT_VERSION)
