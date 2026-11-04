from datetime import datetime

from app.agent.assist import draft, summarize
from app.llm.client import LLMError
from app.schemas.assist import DraftRequest, MailInput, SummarizeRequest, SummaryItem

NOW = datetime(2026, 11, 2, 9, 0)
ITEMS = [
    SummaryItem(task_id="1", text="실적 자료 제출", sender="박 팀장", due_at=datetime(2026, 11, 2, 17, 0), priority="P2"),
    SummaryItem(task_id="2", text="절차서 검토", due_at=datetime(2026, 11, 1, 18, 0), priority="P3"),
    SummaryItem(task_id="3", text="견적 확인", status="snoozed"),
]


def test_today_code_summary_orders_overdue_first(fake_llm):
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS, awaiting_reply_count=2, use_model=False), fake_llm)
    lines = r.text.splitlines()
    assert r.source == "code" and lines[0] == "미처리 2건 · 오늘까지 2건 · 기한 지남 1건 · 응답 대기 2건"
    assert "절차서 검토" in lines[1] and "기한 지남" in lines[1]  # 나중에(snoozed)는 빠진다
    assert "견적" not in r.text


def test_today_model_gets_only_facts(fake_llm):
    fake_llm.replies = ["오늘은 실적 자료 제출이 가장 급합니다."]
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS), fake_llm)
    assert r.source == "exaone" and "실적 자료 제출" in fake_llm.calls[0]["user"]


def test_today_falls_back_to_code(fake_llm):
    fake_llm.replies = [LLMError("down")]
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS), fake_llm)
    assert r.source == "code" and r.fallback == "down" and r.text.startswith("미처리 2건")


def test_mail_summary_fallback(fake_llm):
    body = "Please send the Q3 report by Friday. It is needed for the board.\nThanks."
    r = summarize(SummarizeRequest(mode="mail", now=NOW, mail=MailInput(subject="Q3", body=body)), fake_llm)
    assert r.source == "code" and r.text.startswith("Please send")


def test_draft_from_model_and_template(fake_llm):
    fake_llm.replies = [{"subject": "RE: 견적", "body": "확인했습니다."}, LLMError("down")]
    req = DraftRequest(kind="reply", mail=MailInput(subject="견적 요청", body="견적 부탁드립니다", sender="박 책임"))
    assert draft(req, fake_llm).source == "exaone"
    t = draft(req, fake_llm)
    assert t.source == "template" and t.subject == "RE: 견적 요청" and "[확인 필요" in t.body


def test_endpoints(client, fake_llm):
    fake_llm.replies = [LLMError("down")]
    r = client.post("/draft", json={"kind": "new", "recipient": "오 책임", "topic": "장애 보고 일정"})
    assert r.status_code == 200 and r.json()["subject"] == "[문의] 장애 보고 일정"
    r = client.post("/summarize", json={"mode": "today", "now": "2026-11-02T09:00", "items": [], "use_model": True})
    assert r.json()["text"].startswith("미처리 0건")
