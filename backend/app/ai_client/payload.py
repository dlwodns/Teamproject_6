"""ai `POST /classify` 요청 만들기 (구조도 8절 · ai/app/schemas/classify.py ClassifyRequest).

요청의 owner · sender 칸은 '에이전트가 아는 것'에서 온다 — `memory.classify_context()` 한 곳만 거친다(BE-D18).
그래서 화면 · T11 · 메일 기억하기로 바뀐 기억이 다음 분류부터 그대로 들어간다.
요청은 작업이 실제로 돌 때 만든다(대기열에 넣을 때가 아니라). 대기 중에 바뀐 기억도 반영된다.

개인정보 가리기(BE-6 privacy)는 아직 없다. 지금 쓰는 데이터는 가상 조직의 더미 메일뿐이다(D24 · D53).
가리기가 생기면 이 함수의 결과를 그대로 넘겨 가리게 한다(owner 이름 · 팀도 같은 대체어로).
"""
from sqlalchemy.orm import Session

from app.models import Mail
from app.services import memory


def build_classify_request(db: Session, mail: Mail, body: str) -> dict:
    ctx = memory.classify_context(db, mail)
    return {
        "mail_id": mail.id,
        "from": mail.sender,
        "to": list(mail.recipients or []),
        "cc": list(mail.cc or []),
        "subject": mail.subject or "",
        "body": body,
        "attachments": [],  # 첨부 이름은 저장하지 않는다(구조도 9절). 메일 원본 연결(BE-7) 때 함께 가져온다
        "received_at": mail.sent_at,
        "owner": ctx["owner"],
        "sender": ctx["sender"],
    }
