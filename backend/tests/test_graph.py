"""Outlook 연결(BE-7): 로그인 · 토큰 갱신 · 델타 동기화 · 보내기 · 읽음 · 옮기기. Graph는 httpx.MockTransport로 흉내 낸다."""
import json
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.clock import real_now
from app.jobs import scheduler
from app.mail import graph, graph_sync, tokens
from app.models import Account, ClassifyJob, Mail, MailSync, Task, User

KEY = Fernet.generate_key().decode()
GRAPH = "https://graph.microsoft.com/v1.0"


def msg(i, folder="inbox", **kw):
    return {"id": f"IMM-{i}", "conversationId": f"conv-{i}", "subject": f"제목 {i}", "isRead": False, "isDraft": False,
            "from": {"emailAddress": {"address": "kim@corp.com", "name": "김"}},
            "toRecipients": [{"emailAddress": {"address": "me@example.com"}}], "ccRecipients": [],
            "receivedDateTime": "2026-11-19T00:30:00Z", "sentDateTime": "2026-11-19T00:29:00Z",
            "webLink": f"https://outlook.live.com/{i}", "body": {"contentType": "text", "content": f"본문 {i}"}, **kw}


class FakeGraph:
    """Graph · 로그인 서버 흉내. pages[folder]: 처음 동기화 쪽들, delta[folder]: 다음 델타 응답."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.pages = {"inbox": [[msg(1)], [msg(2)]], "sentitems": [[]]}
        self.delta = {"inbox": [], "sentitems": []}
        self.fail: dict[tuple[str, str], int] = {}  # (method, path 끝) → 상태
        self.token_n = 0
        self.draft_n = 0
        self.parent: dict[str, str | None] = {}  # 메일 id → 지금 메일함 id(None = 영구 삭제)
        self.unauthorized_once = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        body = None
        if req.content:
            body = parse_qs(req.content.decode()) if "oauth2" in path else json.loads(req.content)
        self.calls.append((method, path, body))
        if "oauth2/v2.0/token" in path:
            self.token_n += 1
            return httpx.Response(200, json={"access_token": f"AT{self.token_n}", "refresh_token": f"RT{self.token_n}",
                                             "expires_in": 3600})
        for (m, suffix), status in self.fail.items():
            if m == method and path.endswith(suffix):
                return httpx.Response(status, json={"error": {"code": "Boom"}})
        if self.unauthorized_once:
            self.unauthorized_once = False
            return httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}})
        assert req.headers["Authorization"].startswith("Bearer AT")
        if path == "/v1.0/me":
            return httpx.Response(200, json={"mail": None, "userPrincipalName": "Me@Example.com"})
        assert 'IdType="ImmutableId"' in req.headers["Prefer"]  # 옮겨도 id가 같게(app/mail/graph.py)
        if path.endswith("/messages/delta"):
            folder = path.split("/")[-3]
            if "deltatoken" in req.url.params:  # 다음 동기화
                return httpx.Response(200, json={"value": self.delta[folder], "@odata.deltaLink": f"{GRAPH}/me/mailFolders/{folder}/messages/delta?deltatoken=2"})
            n = int(req.url.params.get("page", 0))
            pages = self.pages[folder]
            data = {"value": pages[n]}
            if n + 1 < len(pages):
                data["@odata.nextLink"] = f"{GRAPH}/me/mailFolders/{folder}/messages/delta?page={n + 1}"
            else:
                data["@odata.deltaLink"] = f"{GRAPH}/me/mailFolders/{folder}/messages/delta?deltatoken=1"
            return httpx.Response(200, json=data)
        if path.endswith(("/createReply", "/createReplyAll", "/createForward")) or (method == "POST" and path == "/v1.0/me/messages"):
            to = (body or {}).get("toRecipients") or [{"emailAddress": {"address": "kim@corp.com"}}]
            self.draft_n += 1
            return httpx.Response(201, json={"id": f"DRAFT-{self.draft_n}", "conversationId": "conv-1", "subject": "RE: 제목 1", "toRecipients": to,
                                             "ccRecipients": []})
        if method == "POST" and path.endswith("/attachments"):
            return httpx.Response(201, json={"id": "ATT-NEW"})
        if method == "POST" and path == "/v1.0/subscriptions":
            return httpx.Response(201, json={"id": "SUB-1", "expirationDateTime": body["expirationDateTime"]})
        if method == "GET" and path == "/v1.0/me/messages" and "$search" in req.url.params:
            return httpx.Response(200, json={"value": [
                {"id": "REST-1", "conversationId": "conv-1", "subject": "제목 1", "from": {"emailAddress": {"address": "kim@corp.com"}},
                 "receivedDateTime": "2026-11-19T00:30:00Z", "webLink": "https://o/1"},
                {"id": "OLD-9", "subject": "작년 견적", "from": {"emailAddress": {"address": "lee@corp.com"}},
                 "receivedDateTime": "2025-05-01T00:00:00Z", "webLink": "https://o/9"}]})
        if method == "GET" and path.endswith("/$value"):
            return httpx.Response(200, content=b"%PDF-1.4 fake")
        if method == "GET" and "/attachments" in path:
            if path.endswith("/attachments"):
                return httpx.Response(200, json={"value": [
                    {"id": "A1", "name": "견적서.pdf", "contentType": "application/pdf", "size": 12, "isInline": False},
                    {"id": "A2", "name": "logo.png", "contentType": "image/png", "size": 5, "isInline": True}]})
            return httpx.Response(200, json={"name": "견적서.pdf", "contentType": "application/pdf"})
        if method == "POST" and path == "/v1.0/me/events":
            self.draft_n += 1
            return httpx.Response(201, json={"id": f"EVW-{self.draft_n}"})
        if method == "POST" and path.endswith("/send"):
            return httpx.Response(202)
        if method in ("PATCH", "DELETE"):
            return httpx.Response(200 if method == "PATCH" else 204, json={} if method == "PATCH" else None)
        if path.endswith("/move"):
            return httpx.Response(201, json={"id": path.split("/")[-2]})
        if path.endswith("/calendarView"):
            assert req.url.params["startDateTime"].endswith("+09:00")
            return httpx.Response(200, json={"value": [
                {"id": "EV-1", "subject": "주간 회의", "isAllDay": False, "isCancelled": False, "webLink": "https://o/ev1",
                 "start": {"dateTime": "2026-11-20T01:00:00.0000000", "timeZone": "UTC"},
                 "end": {"dateTime": "2026-11-20T02:00:00.0000000", "timeZone": "UTC"}},
                {"id": "EV-2", "subject": "취소됨", "isCancelled": True, "start": {"dateTime": "2026-11-20T01:00:00", "timeZone": "UTC"},
                 "end": {"dateTime": "2026-11-20T02:00:00", "timeZone": "UTC"}}]})
        if method == "GET" and path.startswith("/v1.0/me/mailFolders/") and path.count("/") == 4:
            return httpx.Response(200, json={"id": "F-" + path.split("/")[-1]})
        if method == "GET" and "/me/messages/" in path and req.url.params.get("$select") == "parentFolderId":
            mid = path.split("/")[-1]
            if mid in self.parent and self.parent[mid] is None:
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
            return httpx.Response(200, json={"parentFolderId": self.parent.get(mid, "F-myfolder")})
        if method == "GET" and "/me/messages/" in path:
            return httpx.Response(200, json={"body": {"contentType": "text", "content": "가져온 본문"}})
        return httpx.Response(404, json={"error": {"code": "NotFound"}})

    def paths(self, method=None):
        return [p for m, p, _ in self.calls if method in (None, m)]


@pytest.fixture
def fake(monkeypatch):
    for k, v in {"MAIL_SOURCE": "outlook_graph", "MS_GRAPH_CLIENT_ID": "cid", "MS_GRAPH_CLIENT_SECRET": "sec",
                 "MS_GRAPH_REDIRECT_URI": "http://localhost:5173/api/accounts/outlook/callback", "TOKEN_ENCRYPTION_KEY": KEY}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(scheduler, "sync_enabled", lambda: False)  # 테스트 중 백그라운드 동기화가 끼어들지 않게
    f = FakeGraph()
    monkeypatch.setattr(graph, "transport", httpx.MockTransport(f))
    return f


def _connect(client, db) -> Account:
    db.add(User(id=1, name="나"))
    db.commit()
    url = client.post("/api/accounts/outlook/connect").json()["url"]
    q = parse_qs(urlsplit(url).query)
    assert urlsplit(url).path == "/consumers/oauth2/v2.0/authorize"
    assert q["code_challenge_method"] == ["S256"] and "offline_access" in q["scope"][0] and "Mail.Send" in q["scope"][0]
    r = client.get("/api/accounts/outlook/callback", params={"state": q["state"][0], "code": "CODE"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/#/settings/accounts?outlook=connected"
    db.expire_all()
    return db.scalar(select(Account).where(Account.provider == "outlook_graph"))


def test_connect_stores_encrypted_tokens_and_runs_first_sync(client, db, fake):
    account = _connect(client, db)
    assert account.email == "me@example.com"
    assert tokens.decrypt(account.refresh_token_enc) == "RT1" and "RT1" not in account.refresh_token_enc
    token_req = fake.calls[0][2]
    assert token_req["code_verifier"] and token_req["client_secret"] == ["sec"] and token_req["code"] == ["CODE"]
    mails = db.scalars(select(Mail).order_by(Mail.id)).all()
    assert [(m.source_id, m.direction, m.folder, m.read_at) for m in mails] == [("IMM-1", "received", "inbox", None),
                                                                               ("IMM-2", "received", "inbox", None)]
    assert mails[0].sent_at == mails[0].sent_at.replace(hour=9, minute=30)  # 00:30Z → 09:30 KST(시간대 없이 저장)
    assert db.scalar(select(ClassifyJob).where(ClassifyJob.mail_id == mails[0].id)) is not None  # 분류 대기열(더미 적재와 같은 길)
    assert {s.folder: s.delta_link.endswith("deltatoken=1" + graph_sync.SELECT_TAG) for s in db.scalars(select(MailSync))} == {"inbox": True, "sentitems": True}
    listed = client.get("/api/accounts").json()
    assert listed["outlook_enabled"] is True
    assert listed["items"][0]["connected"] is True and listed["items"][0]["last_synced_at"].endswith("+09:00")


def test_callback_state_is_single_use_and_errors_go_back_to_settings(client, db, fake):
    db.add(User(id=1, name="나"))
    db.commit()
    url = client.post("/api/accounts/outlook/connect").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    denied = client.get("/api/accounts/outlook/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False)
    assert denied.headers["location"] == "/#/settings/accounts?outlook=error&reason=denied"
    again = client.get("/api/accounts/outlook/callback", params={"state": state, "code": "C"}, follow_redirects=False)
    assert again.headers["location"] == "/#/settings/accounts?outlook=error&reason=expired"
    assert db.scalar(select(Account)) is None


def test_delta_updates_read_and_removed_without_duplicates(client, db, fake):
    _connect(client, db)
    fake.delta["inbox"] = [msg(1, isRead=True), {"id": "IMM-2", "@removed": {"reason": "deleted"}}, msg(3)]
    r = client.post("/api/accounts/1/sync")
    assert r.json() | {"last_synced_at": None} == {"added": 1, "updated": 1, "removed": 1, "last_synced_at": None}
    db.expire_all()
    by = {m.source_id: m for m in db.scalars(select(Mail))}
    assert by["IMM-1"].read_at is not None and by["IMM-2"].folder == "other" and len(by) == 3


def test_expired_delta_link_restarts_from_scratch(client, db, fake):
    _connect(client, db)
    fake.fail[("GET", "/d/inbox")] = 410
    db.execute(MailSync.__table__.update().where(MailSync.folder == "inbox").values(delta_link=f"{GRAPH}/d/inbox?deltatoken=1" + graph_sync.SELECT_TAG))
    db.commit()
    assert client.post("/api/accounts/1/sync").status_code == 200
    assert len(db.scalars(select(Mail)).all()) == 2  # 처음부터 다시 받아도 두 번 넣지 않는다


def test_delta_link_from_older_select_restarts_and_fills_new_fields(client, db, fake):
    """AI-42: 델타 링크는 처음 요청의 $select를 담는다. importance를 넣기 전 링크면 처음부터 다시 받아 빈 칸을 채운다."""
    _connect(client, db)
    db.execute(MailSync.__table__.update().values(delta_link=f"{GRAPH}/d/inbox?deltatoken=old"))
    db.execute(Mail.__table__.update().values(importance=None))
    db.commit()
    fake.pages["inbox"] = [[{**msg(1), "importance": "high"}], [msg(2)]]
    fake.calls.clear()
    assert client.post("/api/accounts/1/sync").status_code == 200
    assert not any("deltatoken=old" in p for _, p, _ in fake.calls)  # 예전 링크를 부르지 않고 처음부터
    assert {m.source_id: m.importance for m in db.scalars(select(Mail))}["IMM-1"] == "high"


def test_expired_access_token_is_refreshed_and_new_refresh_token_saved(client, db, fake):
    account = _connect(client, db)
    account.expires_at = real_now() - timedelta(minutes=1)
    db.commit()
    client.post("/api/accounts/1/sync")
    db.expire_all()
    assert tokens.decrypt(db.get(Account, 1).refresh_token_enc) == "RT2"  # 갱신 토큰은 바뀐 것으로 저장
    refresh = [b for m, p, b in fake.calls if "token" in p][-1]
    assert refresh["grant_type"] == ["refresh_token"] and refresh["refresh_token"] == ["RT1"]


def test_graph_401_forces_one_refresh_then_retries(client, db, fake):
    _connect(client, db)
    fake.unauthorized_once = True
    assert client.post("/api/accounts/1/sync").status_code == 200
    assert fake.token_n == 2


def test_reply_sends_through_graph_and_sent_sync_does_not_duplicate(client, db, fake):
    _connect(client, db)
    db.add(Task(id=1, mail_id=1, text="회신", status="pending"))
    db.commit()
    r = client.post("/api/mails/1/reply", json={"subject": "RE: 제목 1", "content": "확인했습니다.\n내일 드립니다 <b>"})
    assert r.status_code == 200, r.text
    create = next(b for m, p, b in fake.calls if p.endswith("/IMM-1/createReply"))
    assert create == {"comment": "확인했습니다.<br>내일 드립니다 &lt;b&gt;"}
    assert "/v1.0/me/messages/DRAFT-1/send" in fake.paths("POST")
    sent = db.get(Mail, r.json()["id"])
    assert (sent.source_id, sent.direction, sent.conversation_id, sent.recipients) == ("DRAFT-1", "sent", "conv-1", ["kim@corp.com"])
    fake.delta["sentitems"] = [msg(1, id="DRAFT-1")]
    client.post("/api/accounts/1/sync")
    assert len(db.scalars(select(Mail).where(Mail.source_id == "DRAFT-1")).all()) == 1


def test_send_rejected_deletes_draft_and_records_nothing(client, db, fake):
    _connect(client, db)
    fake.fail[("POST", "/DRAFT-1/send")] = 400
    r = client.post("/api/mails/1/reply", json={"subject": "RE", "content": "답"})
    assert r.status_code == 502
    assert "/v1.0/me/messages/DRAFT-1" in fake.paths("DELETE")
    assert db.scalars(select(Mail).where(Mail.direction == "sent")).all() == []


def test_send_without_answer_keeps_draft_and_says_unknown(client, db, fake):
    _connect(client, db)
    fake.fail[("POST", "/DRAFT-1/send")] = 503  # 받아 놓고 답만 늦었을 수 있다 → 지우면 보낸 사본이 지운 편지함으로 간다
    r = client.post("/api/mails/1/reply", json={"subject": "RE", "content": "답"})
    assert r.status_code == 504 and "보낸 편지함" in r.json()["detail"]
    assert fake.paths("DELETE") == []


def test_forward_and_new_mail(client, db, fake):
    _connect(client, db)
    assert client.post("/api/mails/1/forward", json={"subject": "FW", "content": "참고"}).status_code == 422  # 받는 사람 필수
    r = client.post("/api/mails/1/forward", json={"subject": "FW", "content": "참고", "to": ["lee@corp.com"]})
    assert r.status_code == 200
    fwd = next(b for m, p, b in fake.calls if p.endswith("/createForward"))
    assert fwd["toRecipients"] == [{"emailAddress": {"address": "lee@corp.com"}}]
    r = client.post("/api/mails", json={"subject": "새 메일", "content": "안녕", "to": ["park@corp.com"], "cc": ["a@corp.com"]})
    assert r.status_code == 201
    new = next(b for m, p, b in fake.calls if m == "POST" and p == "/v1.0/me/messages")
    assert new["subject"] == "새 메일" and new["ccRecipients"] == [{"emailAddress": {"address": "a@corp.com"}}]
    assert client.post("/api/mails", json={"subject": "x", "content": "y", "to": ["not an address"]}).status_code == 422


def test_read_writes_to_outlook_pin_stays_local_and_move(client, db, fake):
    _connect(client, db)
    r = client.patch("/api/mails/1", json={"read": True, "pinned": True})
    assert r.status_code == 200 and r.json()["read_at"] and r.json()["pinned_at"]
    patches = [(p, b) for m, p, b in fake.calls if m == "PATCH"]
    assert patches == [("/v1.0/me/messages/IMM-1", {"isRead": True})]  # 고정은 Outlook에 쓰지 않는다
    r = client.post("/api/mails/1/move", json={"folder": "archive"})
    assert r.json()["folder"] == "archive"
    assert ("POST", "/v1.0/me/messages/IMM-1/move", {"destinationId": "archive"}) in fake.calls
    fake.delta["inbox"] = [{"id": "IMM-1", "@removed": {"reason": "deleted"}}]
    client.post("/api/accounts/1/sync")
    db.expire_all()
    assert db.get(Mail, 1).folder == "archive"  # 우리가 옮긴 것은 '다른 곳(other)'으로 덮지 않는다


def test_graph_failure_on_patch_leaves_db_unchanged(client, db, fake):
    _connect(client, db)
    fake.fail[("PATCH", "/IMM-1")] = 500
    assert client.patch("/api/mails/1", json={"read": True}).status_code == 502
    db.expire_all()
    assert db.get(Mail, 1).read_at is None


def test_body_comes_from_graph(client, db, fake):
    _connect(client, db)
    assert client.get("/api/mails/1").json()["body"] == "가져온 본문"


def test_disconnect_stops_sending_but_keeps_mail(client, db, fake):
    _connect(client, db)
    assert client.post("/api/accounts/1/disconnect").json()["connected"] is False
    assert client.post("/api/mails/1/reply", json={"subject": "RE", "content": "답"}).status_code == 409
    assert len(db.scalars(select(Mail)).all()) == 2 and db.scalars(select(MailSync)).all() == []


def test_disconnected_account_mail_is_hidden_only_in_app_and_stays_hidden_after_reconnect(client, db, fake):
    """연결을 끊은 계정 메일도 치울 수 있다 — Outlook에는 쓰지 않고 우리 앱에서만 숨긴다(11-19)."""
    _connect(client, db)
    client.post("/api/accounts/1/disconnect")
    n_calls = len(fake.calls)
    assert client.patch("/api/mails/1", json={"read": True}).status_code == 200
    assert client.post("/api/mails/1/move", json={"folder": "archive"}).status_code == 200
    assert len(fake.calls) == n_calls  # Graph를 부르지 않았다
    assert [m["id"] for m in client.get("/api/dashboard").json()["mails"]] == [2]
    _reconnect = client.post("/api/accounts/outlook/connect").json()["url"]  # 다시 연결 → 처음부터 동기화(받은 편지함에 그대로 있음)
    state = parse_qs(urlsplit(_reconnect).query)["state"][0]
    client.get("/api/accounts/outlook/callback", params={"state": state, "code": "C2"}, follow_redirects=False)
    assert [m["id"] for m in client.get("/api/dashboard").json()["mails"]] == [2]  # 숨긴 채로
    client.post("/api/mails/1/move", json={"folder": "inbox"})
    assert [m["id"] for m in client.get("/api/dashboard").json()["mails"]] == [1, 2]


def test_hidden_mail_tasks_leave_reminders_calendar_awaiting_and_agent(client, db, fake):
    """보관 · 지운 메일의 업무는 대시보드 밖에서도 보이지 않는다(11-19)."""
    from app.agent.resolve import resolve
    from app.reminders import engine, rules

    _connect(client, db)
    due = real_now() + timedelta(hours=2)
    db.add(Task(id=1, mail_id=1, text="견적 회신", status="pending", due_at=due, due_source="rule"))
    db.add(Mail(id=50, account_id=1, source_id="S-50", direction="sent", sender="me@example.com", recipients=["kim@corp.com"],
                subject="자료 요청", sent_at=real_now() - timedelta(days=5), conversation_id="c-50", folder="sentitems"))
    db.commit()
    day = due.date().isoformat()

    def seen():
        db.expire_all()
        cal = client.get("/api/calendar", params={"start": day, "end": day}).json()["items"]
        return ({i["task_id"] for i in engine.items(db, 1)} & {1},
                {i["task_id"] for i in cal if i["task_id"]},
                [m.id for m in rules.awaiting_requests(rules.Context(db, 1, real_now()))],
                resolve(db, 1, {"keyword": "견적"}).task_ids)

    assert seen() == ({1}, {1}, [50], [1])
    client.post("/api/mails/1/move", json={"folder": "deleteditems"})
    db.get(Mail, 50).folder = "deleteditems"
    db.commit()
    assert seen() == (set(), set(), [], [])


def test_dummy_mail_patch_and_move_stay_local(client, db, fake):
    db.add(User(id=1, name="나"))
    db.flush()
    db.add(Account(id=5, user_id=1, provider="dummy", email="me@cne.com"))
    db.flush()
    db.add(Mail(id=9, account_id=5, source_id="M-9", direction="received", sender="a@cne.com", subject="s", sent_at=real_now()))
    db.commit()
    assert client.patch("/api/mails/9", json={"read": True}).json()["read_at"]
    assert client.post("/api/mails/9/move", json={"folder": "deleteditems"}).json()["folder"] == "deleteditems"
    assert fake.calls == []


def test_hidden_mails_lists_only_my_archived_deleted_and_app_hidden(client, db):
    """보관함 · 지운 편지함 보기: 내 받은 메일 중 대시보드가 빼는 것만. 다른 사용자 메일 · 보낸 메일은 섞이지 않는다."""
    db.add_all([User(id=1, name="나"), User(id=2, name="남")])
    db.flush()
    db.add_all([Account(id=5, user_id=1, provider="dummy", email="me@cne.com"),
                Account(id=6, user_id=2, provider="dummy", email="you@cne.com")])
    db.flush()
    at = real_now()

    def mail(i, account_id=5, **kw):
        kw.setdefault("direction", "received")
        db.add(Mail(id=i, account_id=account_id, source_id=f"M-{i}", sender="a@cne.com", subject=f"s{i}",
                    sent_at=at + timedelta(minutes=i), **kw))

    mail(1)  # 받은 편지함(더미 folder 비어 있음)
    mail(2, folder="archive")
    mail(3, folder="deleteditems")
    mail(4, folder="inbox", hidden_at=at)  # 끊긴 계정에서 우리 앱만 숨김
    mail(5, folder="archive", direction="sent")
    mail(6, account_id=6, folder="archive")  # 다른 사용자
    db.commit()
    r = client.get("/api/mails/hidden")
    assert r.status_code == 200
    assert [(m["id"], m["folder"], m["account"]) for m in r.json()] == [(4, "inbox", "me@cne.com"), (3, "deleteditems", "me@cne.com"),
                                                                        (2, "archive", "me@cne.com")]
    assert [m["id"] for m in client.get("/api/mails/hidden", headers={"X-User-Id": "2"}).json()] == [6]
    client.post("/api/mails/2/move", json={"folder": "inbox"})
    assert [m["id"] for m in client.get("/api/mails/hidden").json()] == [4, 3]


def test_settings_require_valid_fernet_key(monkeypatch):
    from app.core.config import check_settings

    for k in ("MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_REDIRECT_URI"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("MAIL_SOURCE", "outlook_graph")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-key")
    assert any("TOKEN_ENCRYPTION_KEY" in e for e in check_settings())


def test_calendar_includes_outlook_events_and_survives_graph_failure(client, db, fake):
    _connect(client, db)
    items = client.get("/api/calendar", params={"start": "2026-11-16", "end": "2026-11-22"}).json()["items"]
    ev = [i for i in items if i.get("outlook_id")]
    assert [(i["title"], i["start"], i["end"], i["event_id"]) for i in ev] ==         [("주간 회의", "2026-11-20T10:00:00+09:00", "2026-11-20T11:00:00+09:00", None)]  # 취소된 일정은 뺀다
    fake.fail[("GET", "/calendarView")] = 503
    assert client.get("/api/calendar", params={"start": "2026-11-16", "end": "2026-11-22"}).status_code == 200


def test_graph_client_only_talks_to_graph_hosts(client, db, fake):
    account = _connect(client, db)
    with pytest.raises(graph.GraphError) as e:  # 응답의 nextLink가 다른 호스트를 가리켜도 보내지 않는다(app/core/egress.py)
        graph.call(db, account, "GET", "https://evil.example.com/steal")
    assert e.value.status == 503 and not [p for m, p, b in fake.calls if "steal" in p]


def test_mail_archived_or_deleted_in_outlook_leaves_dashboard(client, db, fake):
    _connect(client, db)
    db.add(Task(id=1, mail_id=1, text="회신", status="pending"))
    db.add(Task(id=2, mail_id=2, text="검토", status="pending"))
    db.commit()
    fake.parent = {"IMM-1": "F-archive", "IMM-2": None}  # 1은 Outlook에서 보관, 2는 영구 삭제
    fake.delta["inbox"] = [{"id": "IMM-1", "@removed": {"reason": "deleted"}}, {"id": "IMM-2", "@removed": {"reason": "deleted"}}]
    client.post("/api/accounts/1/sync")
    db.expire_all()
    assert (db.get(Mail, 1).folder, db.get(Mail, 2).folder) == ("archive", "deleteditems")
    dash = client.get("/api/dashboard").json()
    assert dash["mails"] == [] and dash["tasks"] == []
    assert db.get(Task, 1) is not None  # 업무는 지우지 않는다(받은 편지함으로 되돌리면 다시 보인다)


def test_mail_moved_in_app_to_archive_leaves_dashboard_and_back(client, db, fake):
    _connect(client, db)
    client.post("/api/mails/1/move", json={"folder": "archive"})
    assert [m["id"] for m in client.get("/api/dashboard").json()["mails"]] == [2]
    client.post("/api/mails/1/move", json={"folder": "inbox"})
    assert [m["id"] for m in client.get("/api/dashboard").json()["mails"]] == [1, 2]


def test_callback_from_another_browser_is_refused(client, db, fake):
    """로그인 CSRF: 남이 시작한 연결 주소(쿠키 없음)로 돌아오면 계정을 붙이지 않는다."""
    db.add(User(id=1, name="나"))
    db.commit()
    url = client.post("/api/accounts/outlook/connect").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    client.cookies.clear()  # 다른 브라우저
    r = client.get("/api/accounts/outlook/callback", params={"state": state, "code": "C"}, follow_redirects=False)
    assert r.headers["location"].endswith("outlook=error&reason=expired")
    assert db.scalar(select(Account)) is None and not [p for m, p, b in fake.calls if "token" in p]


def test_sent_mail_already_synced_is_not_inserted_twice(client, db, fake):
    """보낸 편지함 동기화가 먼저 그 메일을 넣었어도 보내기 기록이 같은 행을 쓴다(유일 제약 500 없음)."""
    account = _connect(client, db)
    db.add(Mail(account_id=account.id, source_id="DRAFT-1", direction="sent", sender="me@example.com", subject="RE: 제목 1",
                sent_at=real_now(), folder="sentitems"))
    db.commit()
    r = client.post("/api/mails/1/reply", json={"subject": "RE", "content": "답", "cc": ["c@corp.com"]})
    assert r.status_code == 200, r.text
    rows = db.scalars(select(Mail).where(Mail.source_id == "DRAFT-1")).all()
    assert len(rows) == 1 and rows[0].category == "기타"


def test_reply_cc_is_recorded(client, db, fake):
    _connect(client, db)
    r = client.post("/api/mails/1/reply", json={"subject": "RE", "content": "답", "cc": ["c@corp.com"]})
    assert db.get(Mail, r.json()["id"]).cc == ["c@corp.com"]


def test_transient_folder_lookup_failure_does_not_mark_other(client, db, fake):
    _connect(client, db)
    fake.parent = {"IMM-1": "F-archive"}
    fake.fail[("GET", "/mailFolders/archive")] = 503  # 잠깐 실패 → 'other'로 굳히지 않고 다음 틱에 다시
    fake.delta["inbox"] = [{"id": "IMM-1", "@removed": {"reason": "deleted"}}]
    assert client.post("/api/accounts/1/sync").status_code == 502
    db.expire_all()
    assert db.get(Mail, 1).folder == "inbox"
    del fake.fail[("GET", "/mailFolders/archive")]
    client.post("/api/accounts/1/sync")
    db.expire_all()
    assert db.get(Mail, 1).folder == "archive"


def test_classify_defers_when_outlook_body_is_temporarily_unavailable(client, db, fake):
    from app.jobs import classify

    _connect(client, db)
    fake.fail[("GET", "/me/messages/IMM-1")] = 503
    job = db.scalar(select(ClassifyJob).where(ClassifyJob.mail_id == 1))
    out = classify._process(db, None, job)
    assert out["status"] == "queued" and db.get(ClassifyJob, job.id).attempts == 0  # 횟수를 세지 않는다


def test_all_day_outlook_event_keeps_its_date(client, db, fake, monkeypatch):
    _connect(client, db)
    orig = fake.__call__

    def all_day(req):
        if req.url.path.endswith("/calendarView"):
            return httpx.Response(200, json={"value": [{"id": "EV-9", "subject": "휴가", "isAllDay": True, "isCancelled": False,
                                                        "start": {"dateTime": "2026-11-20T00:00:00.0000000", "timeZone": "UTC"},
                                                        "end": {"dateTime": "2026-11-21T00:00:00.0000000", "timeZone": "UTC"}}]})
        return orig(req)

    monkeypatch.setattr(graph, "transport", httpx.MockTransport(all_day))
    items = client.get("/api/calendar", params={"start": "2026-11-16", "end": "2026-11-22"}).json()["items"]
    ev = next(i for i in items if i.get("outlook_id") == "EV-9")
    assert (ev["start"], ev["end"], ev["time_stated"]) == ("2026-11-20T00:00:00+09:00", "2026-11-21T00:00:00+09:00", False)


def test_calendar_add_remove_undo_write_to_outlook_and_do_not_show_twice(client, db, fake):
    """BE-7 1c: 넣기 = POST /me/events(참석자 없음, KST), 빼기 = DELETE, 빼기 되돌리기 = 다시 만들기. 우리가 넣은 일정은 한 번만 보인다."""
    _connect(client, db)
    r = client.post("/api/calendar/events", json={"title": "고객 미팅", "start": "2026-11-20T15:00:00+09:00"})
    assert r.status_code == 201
    ev_id = r.json()["item"]["event_id"]
    post = [b for m, p, b in fake.calls if m == "POST" and p == "/v1.0/me/events"]
    assert post == [{"subject": "고객 미팅", "start": {"dateTime": "2026-11-20T15:00:00", "timeZone": "Korea Standard Time"},
                     "end": {"dateTime": "2026-11-20T16:00:00", "timeZone": "Korea Standard Time"}}]
    created = post and fake.draft_n
    fake_id = f"EVW-{created}"

    # Outlook 읽기가 우리가 넣은 일정을 돌려줘도 앱 일정으로 한 번만
    real = fake.__call__

    def with_mine(req):
        if req.url.path.endswith("/calendarView"):
            return httpx.Response(200, json={"value": [{"id": fake_id, "subject": "고객 미팅", "isAllDay": False, "isCancelled": False,
                                                        "start": {"dateTime": "2026-11-20T06:00:00", "timeZone": "UTC"},
                                                        "end": {"dateTime": "2026-11-20T07:00:00", "timeZone": "UTC"}}]})
        return real(req)
    graph.transport = httpx.MockTransport(with_mine)
    items = client.get("/api/calendar", params={"start": "2026-11-16", "end": "2026-11-22"}).json()["items"]
    assert [(i["title"], i["event_id"] is not None) for i in items if i["kind"] == "event"] == [("고객 미팅", True)]
    graph.transport = httpx.MockTransport(fake)

    action = client.delete(f"/api/calendar/events/{ev_id}").json()["action_id"]
    assert ("DELETE", f"/v1.0/me/events/{fake_id}") in [(m, p) for m, p, _ in fake.calls]
    assert client.post(f"/api/actions/{action}/undo").status_code == 200
    assert len([1 for m, p, _ in fake.calls if m == "POST" and p == "/v1.0/me/events"]) == 2  # 되살리면 새로 만든다


def test_calendar_add_survives_outlook_failure(client, db, fake):
    _connect(client, db)
    fake.fail[("POST", "/me/events")] = 503
    r = client.post("/api/calendar/events", json={"title": "회의", "start": "2026-11-20T15:00:00+09:00"})
    assert r.status_code == 201  # 앱 일정은 그대로 넣는다


def test_tick_sync_waits_for_retry_after(client, db, fake):
    """Graph 429 + Retry-After: 그 시간 동안 틱 동기화가 그 계정을 부르지 않는다."""
    from app.mail import graph_sync

    account = _connect(client, db)
    fake.fail[("GET", "/messages/delta")] = 429
    real = fake.__call__

    def throttled(req):
        r = real(req)
        if r.status_code == 429:
            r.headers["Retry-After"] = "120"
        return r
    graph.transport = httpx.MockTransport(throttled)
    graph_sync._resume_at.clear()
    graph_sync.sync_all(db)
    assert account.id in graph_sync._resume_at
    n = len(fake.calls)
    graph_sync.sync_all(db)
    assert len(fake.calls) == n  # 쉬는 동안 부르지 않음
    graph_sync._resume_at.clear()
    assert graph_sync.retry_after("abc") is None and graph_sync.retry_after("99999").total_seconds() == 1800


def test_nudge_reply_all_keeps_conversation_and_sets_recipients(client, db, fake):
    """재촉(T14)은 내 보낸 메일에 createReplyAll로 보내 같은 대화로 잇고, 받는 사람은 PATCH로 재촉 대상에 맞춘다."""
    from app.services.sending import send_graph

    account = _connect(client, db)
    draft = send_graph(db, account, "replyAll", content="회신 부탁드립니다", source_id="SENT-1", to=["kim@corp.com"])
    calls = [(m, p, b) for m, p, b in fake.calls if "/me/messages" in p]
    assert calls[0][:2] == ("POST", "/v1.0/me/messages/SENT-1/createReplyAll") and "toRecipients" not in calls[0][2]
    assert calls[1] == ("PATCH", f"/v1.0/me/messages/{draft['id']}", {"toRecipients": [{"emailAddress": {"address": "kim@corp.com"}}]})
    assert calls[2][:2] == ("POST", f"/v1.0/me/messages/{draft['id']}/send")
    assert draft["conversationId"] == "conv-1"


# ── BE-7 단계 2: 첨부 · 검색 · 예약 보내기 · 변경 알림 · 서명 ──

def test_attachment_is_added_before_send_and_failure_drops_draft(client, db, fake):
    import base64
    _connect(client, db)
    b64 = base64.b64encode(b"hello").decode()
    r = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "자료", "content": "첨부합니다",
                                        "attachments": [{"name": "a.txt", "content_type": "text/plain", "content_b64": b64}]})
    assert r.status_code == 201
    seq = [(m, p.rsplit("/", 1)[-1]) for m, p, _ in fake.calls if "/me/messages" in p]
    assert seq.index(("POST", "attachments")) < seq.index(("POST", "send"))
    att = next(b for m, p, b in fake.calls if p.endswith("/attachments"))
    assert att == {"@odata.type": "#microsoft.graph.fileAttachment", "name": "a.txt", "contentType": "text/plain", "contentBytes": b64}

    fake.fail[("POST", "/attachments")] = 400
    n = len(fake.calls)
    r = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "자료", "content": "첨부합니다",
                                        "attachments": [{"name": "a.txt", "content_b64": b64}]})
    assert r.status_code == 502
    later = [(m, p) for m, p, _ in fake.calls[n:]]
    assert not any(p.endswith("/send") for _, p in later) and any(m == "DELETE" for m, _ in later)  # 첨부가 빠진 메일은 나가지 않는다


def test_attachment_limits(client, db, fake):
    import base64
    _connect(client, db)
    big = base64.b64encode(b"x" * (3 * 1024 * 1024)).decode()
    assert client.post("/api/mails", json={"to": ["a@b.c"], "subject": "s", "content": "c",
                                           "attachments": [{"name": "big", "content_b64": big}]}).status_code == 422
    assert client.post("/api/mails", json={"to": ["a@b.c"], "subject": "s", "content": "c",
                                           "attachments": [{"name": "bad", "content_b64": "@@@"}]}).status_code == 422


def test_list_and_download_attachments(client, db, fake):
    _connect(client, db)
    mail = db.scalar(select(Mail).where(Mail.source_id == "IMM-1"))
    atts = client.get(f"/api/mails/{mail.id}/attachments").json()
    assert [a["name"] for a in atts] == ["견적서.pdf"]  # 본문 그림(isInline)은 뺀다
    r = client.get(f"/api/mails/{mail.id}/attachments/A1")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 fake"
    assert r.headers["content-type"] == "application/octet-stream" and "attachment;" in r.headers["content-disposition"]


def test_outlook_search_marks_known_mails(client, db, fake):
    _connect(client, db)
    hits = client.get("/api/mails/search", params={"q": '견적 "x'}).json()
    assert [(h["subject"], h["mail_id"] is not None, h["web_link"]) for h in hits] == [("제목 1", True, "https://o/1"),
                                                                                     ("작년 견적", False, "https://o/9")]
    assert client.get("/api/mails/search", params={"q": "a"}).status_code == 422  # 두 글자부터


def test_scheduled_send_waits_then_sends_once_and_can_be_canceled(client, db, fake, monkeypatch):
    from datetime import datetime as dt

    from app.api import reply
    from app.models import ScheduledSend
    _connect(client, db)
    r = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "예약", "content": "내일 아침에",
                                        "send_at": "2099-01-01T09:00:00+09:00"})
    assert r.status_code == 202 and r.json()["status"] == "pending" and r.json()["send_at"] == "2099-01-01T09:00:00+09:00"
    sid = r.json()["scheduled_id"]
    assert not any(p.endswith("/send") for _, p, _ in fake.calls)  # 아직 안 나감
    assert [s["scheduled_id"] for s in client.get("/api/scheduled-sends").json()] == [sid]

    assert reply.run_due(db) == 0  # 시각 전
    monkeypatch.setattr(reply, "now", lambda: dt(2099, 1, 1, 9, 0, 1))
    assert reply.run_due(db) == 1 and reply.run_due(db) == 0  # 한 번만
    row = db.get(ScheduledSend, sid)
    db.refresh(row)
    assert row.status == "sent" and row.request_json is None and row.sent_mail_id
    assert sum(1 for _, p, _ in fake.calls if p.endswith("/send")) == 1
    assert client.get("/api/scheduled-sends").json() == []

    r = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "취소할 것", "content": "c",
                                        "send_at": "2099-02-01T09:00:00+09:00"})
    cid = r.json()["scheduled_id"]
    assert client.delete(f"/api/scheduled-sends/{cid}").json()["status"] == "canceled"
    monkeypatch.setattr(reply, "now", lambda: dt(2099, 3, 1))
    assert reply.run_due(db) == 0


def test_scheduled_send_rejects_past_and_naive_time(client, db, fake):
    _connect(client, db)
    assert client.post("/api/mails", json={"to": ["a@b.c"], "subject": "s", "content": "c",
                                           "send_at": "2000-01-01T09:00:00+09:00"}).status_code == 422
    assert client.post("/api/mails", json={"to": ["a@b.c"], "subject": "s", "content": "c",
                                           "send_at": "2099-01-01T09:00:00"}).status_code == 422


def test_scheduled_send_unknown_result_is_recorded(client, db, fake, monkeypatch):
    from datetime import datetime as dt

    from app.api import reply
    from app.models import ScheduledSend
    _connect(client, db)
    sid = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "s", "content": "c",
                                          "send_at": "2099-01-01T09:00:00+09:00"}).json()["scheduled_id"]
    fake.fail[("POST", "/send")] = 503
    monkeypatch.setattr(reply, "now", lambda: dt(2099, 1, 1, 10))
    reply.run_due(db)
    row = db.get(ScheduledSend, sid)
    db.refresh(row)
    assert row.status == "unknown" and "보낸 편지함" in row.error  # 나갔을 수 있다 — 다시 보내지 않는다
    assert [s["status"] for s in client.get("/api/scheduled-sends").json()] == ["unknown"]


def test_change_notifications_subscribe_validate_and_sync_only_matching(client, db, fake, monkeypatch):
    from app.mail import graph_notify
    account = _connect(client, db)
    graph_notify.ensure_all(db)
    assert not [p for _, p, _ in fake.calls if "subscriptions" in p]  # GRAPH_NOTIFY_URL 없으면 구독하지 않는다
    monkeypatch.setenv("GRAPH_NOTIFY_URL", "http://insecure.example.com")
    graph_notify.ensure_all(db)
    assert not [p for _, p, _ in fake.calls if "subscriptions" in p]  # https만

    monkeypatch.setenv("GRAPH_NOTIFY_URL", "https://cne.example.com/")
    graph_notify.ensure_all(db)
    sub = next(b for m, p, b in fake.calls if p == "/v1.0/subscriptions")
    assert sub["notificationUrl"] == "https://cne.example.com/api/graph/notify"
    assert sub["resource"] == "me/mailFolders('inbox')/messages"
    db.refresh(account)
    assert account.subscription_id == "SUB-1" and account.notify_state == sub["clientState"]
    graph_notify.ensure_all(db)
    assert len([1 for m, p, _ in fake.calls if p == "/v1.0/subscriptions"]) == 1  # 아직 넉넉하면 다시 만들지 않는다

    r = client.post("/api/graph/notify", params={"validationToken": "abc 123"})
    assert r.status_code == 200 and r.text == "abc 123" and r.headers["content-type"].startswith("text/plain")

    fake.delta["inbox"] = [msg(7)]
    r = client.post("/api/graph/notify", json={"value": [{"subscriptionId": "SUB-1", "clientState": "wrong"}]})
    assert r.status_code == 202 and db.scalar(select(Mail).where(Mail.source_id == "IMM-7")) is None  # 위조 알림은 버린다
    r = client.post("/api/graph/notify", json={"value": [{"subscriptionId": "SUB-1", "clientState": account.notify_state}]})
    assert r.status_code == 202
    db.expire_all()
    assert db.scalar(select(Mail).where(Mail.source_id == "IMM-7")) is not None  # 그 계정을 바로 받았다

    client.post(f"/api/accounts/{account.id}/disconnect")
    assert ("DELETE", "/v1.0/subscriptions/SUB-1") in [(m, p) for m, p, _ in fake.calls]
    db.refresh(account)
    assert account.subscription_id is None


def test_signature_setting_round_trip(client, db):
    db.add(User(id=1, name="나"))
    db.commit()
    assert client.get("/api/settings").json()["mail_signature"] is None
    r = client.patch("/api/settings", json={"mail_signature": "  문규남 드림\n010-0000-0000  "})
    assert r.json()["mail_signature"] == "문규남 드림\n010-0000-0000"
    assert client.patch("/api/settings", json={"mail_signature": ""}).json()["mail_signature"] is None


# ── AI-32 아웃룩 벤치마킹: 서식 HTML · 중요도 · 큰 첨부(업로드 세션) · 받은 메일 중요도 ──

def test_html_body_is_cleaned_and_importance_is_sent(client, db, fake):
    _connect(client, db)
    r = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "자료", "content": "굵게 보냅니다", "importance": "high",
                                        "content_html": '<p><b>굵게</b> 보냅니다<img src=x onerror="alert(1)"></p>'})
    assert r.status_code == 201
    new = next(b for m, p, b in fake.calls if m == "POST" and p == "/v1.0/me/messages")
    assert new["importance"] == "high" and new["body"]["content"] == "<p><b>굵게</b> 보냅니다</p>"
    # 답장은 초안을 PATCH해 중요도를 넣는다. 보통이면 칸을 보내지 않는다
    client.post("/api/mails/1/reply", json={"subject": "RE", "content": "확인했습니다", "importance": "low"})
    assert ("PATCH" in [m for m, p, b in fake.calls if b and b.get("importance") == "low"])
    assert "isReadReceiptRequested" not in new and "isDeliveryReceiptRequested" not in new  # 끄면 칸을 보내지 않는다


def test_read_and_delivery_receipts_are_requested(client, db, fake):
    """AI-38: 읽음 · 배달 확인을 켜면 새 메일은 초안 만들 때, 답장은 초안 PATCH에 칸이 붙는다."""
    _connect(client, db)
    client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "s", "content": "c",
                                    "read_receipt": True, "delivery_receipt": True})
    new = next(b for m, p, b in fake.calls if m == "POST" and p == "/v1.0/me/messages")
    assert new["isReadReceiptRequested"] is True and new["isDeliveryReceiptRequested"] is True
    client.post("/api/mails/1/reply", json={"subject": "RE", "content": "확인했습니다", "read_receipt": True})
    patch = next(b for m, p, b in fake.calls if m == "PATCH" and b and "isReadReceiptRequested" in b)
    assert "isDeliveryReceiptRequested" not in patch and "importance" not in patch


def test_large_attachment_uses_upload_session_then_is_removed(client, db, fake, monkeypatch, tmp_path):
    from app.api import uploads

    monkeypatch.setattr(uploads, "upload_dir", lambda uid: tmp_path)
    puts = []

    def handler(req: httpx.Request):
        if req.url.host == "outlook.office.com":  # 업로드 세션 주소: 인증 머리를 붙이지 않는다
            assert "Authorization" not in req.headers
            puts.append(req.headers["Content-Range"])
            return httpx.Response(201 if req.headers["Content-Range"].endswith(f"/{size}") and len(puts) == 2 else 200, json={})
        if req.url.path.endswith("/createUploadSession"):
            fake.calls.append((req.method, req.url.path, json.loads(req.content)))
            return httpx.Response(201, json={"uploadUrl": "https://outlook.office.com/api/up/1?authtoken=x"})
        return fake(req)

    monkeypatch.setattr(graph, "transport", httpx.MockTransport(handler))
    _connect(client, db)
    size = graph.UPLOAD_CHUNK + 3 * 1024 * 1024  # 조각 둘
    up = client.post("/api/uploads", content=b"x" * size, headers={"X-File-Name": "%EB%B3%B4%EA%B3%A0%EC%84%9C.pdf",
                                                                   "Content-Type": "application/pdf"})
    assert up.status_code == 201 and up.json()["name"] == "보고서.pdf"
    r = client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "큰 자료", "content": "첨부합니다",
                                        "large_attachments": [up.json()["id"]]})
    assert r.status_code == 201
    assert puts == [f"bytes 0-{graph.UPLOAD_CHUNK - 1}/{size}", f"bytes {graph.UPLOAD_CHUNK}-{size - 1}/{size}"]
    seq = [p.rsplit("/", 1)[-1] for m, p, _ in fake.calls if "/me/messages" in p and m == "POST"]
    assert seq.index("createUploadSession") < seq.index("send")
    assert list(tmp_path.iterdir()) == []  # 보낸 뒤 지운다
    # 없는 id · 3MB 미만은 거절
    assert client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "s", "content": "c",
                                           "large_attachments": [up.json()["id"]]}).status_code == 422
    assert client.post("/api/uploads", content=b"x" * 10, headers={"X-File-Name": "a.txt"}).status_code == 422


def test_sweep_drops_old_uploads_but_keeps_scheduled_and_fresh(client, db, fake, monkeypatch, tmp_path):
    """AI-35: 보내지 않고 하루 지난 큰 첨부는 다음 올리기 때 지운다. 예약 보내기가 잡은 것 · 방금 올린 것은 남긴다."""
    import os
    from app.api import uploads

    monkeypatch.setattr(uploads, "upload_root", lambda: tmp_path)
    _connect(client, db)
    ids = []
    for _ in range(3):
        up = client.post("/api/uploads", content=b"x" * uploads.MIN_BYTES, headers={"X-File-Name": "a.pdf"})
        ids.append(up.json()["id"])
    old, held, fresh = ids
    assert client.post("/api/mails", json={"to": ["kim@corp.com"], "subject": "예약", "content": "첨부",
                                           "send_at": "2099-01-01T09:00:00+09:00",
                                           "large_attachments": [held]}).status_code == 202
    day_ago = time.time() - uploads.KEEP_S - 1
    for f in tmp_path.glob("*/*"):
        if f.stem in (old, held):
            os.utime(f, (day_ago, day_ago))
    assert uploads.sweep(db) == 2  # old의 본문 · .json
    left = {f.stem for f in tmp_path.glob("*/*")}
    assert left == {held, fresh}


def test_received_importance_is_synced(client, db, fake):
    fake.pages["inbox"] = [[{**msg(1), "importance": "high"}], [msg(2)]]
    _connect(client, db)
    imp = {m.source_id: m.importance for m in db.scalars(select(Mail))}
    assert imp["IMM-1"] == "high" and imp["IMM-2"] is None
    shown = {m["source_id"]: m["importance"] for m in client.get("/api/dashboard").json()["mails"]}
    assert shown["IMM-1"] == "high"


def test_detail_has_clean_html_and_inline_image_is_served(client, db, fake, monkeypatch):
    """AI-42: 읽기 화면은 거른 HTML을 받고, 붙여넣은 캡처(cid 그림)는 우리 주소로 바뀌어 그림 바이트로 온다."""
    import base64

    def handler(req: httpx.Request):
        p = req.url.path
        if req.method == "GET" and p == "/v1.0/me/messages/IMM-1" and req.url.params.get("$select") == "body":
            if 'outlook.body-content-type="text"' in req.headers["Prefer"]:
                return httpx.Response(200, json={"body": {"contentType": "text", "content": "잘 받았다\n[cid:img1]"}})
            return httpx.Response(200, json={"body": {"contentType": "html", "content":
                '<p><b>잘 받았다</b><img src="cid:img1"><img src="https://t.example/p.gif"></p><script>x()</script>'}})
        if req.method == "GET" and p == "/v1.0/me/messages/IMM-1/attachments/A2":
            return httpx.Response(200, json={"contentId": "img1", "contentBytes": base64.b64encode(b"\x89PNG").decode()})
        return fake(req)

    monkeypatch.setattr(graph, "transport", httpx.MockTransport(handler))
    _connect(client, db)
    d = client.get("/api/mails/1").json()
    assert d["body_html"] == '<p><b>잘 받았다</b><img src="/api/mails/1/inline/img1"></p>'
    assert d["body"] == "잘 받았다\n[그림]"  # 글 본문의 cid 표시는 [그림]으로
    r = client.get("/api/mails/1/inline/img1")
    assert r.status_code == 200 and r.content == b"\x89PNG" and r.headers["content-type"] == "image/png"
    assert client.get("/api/mails/1/inline/nope").status_code == 404


def test_removed_large_attachment_is_deleted_right_away(client, db, fake, monkeypatch, tmp_path):
    """AI-42: 쓰기 화면에서 [빼기]한 큰 첨부는 하루를 기다리지 않고 지운다. 남의 id · 없는 id는 조용히 넘어간다."""
    from app.api import uploads

    monkeypatch.setattr(uploads, "upload_root", lambda: tmp_path)
    _connect(client, db)
    up = client.post("/api/uploads", content=b"x" * uploads.MIN_BYTES, headers={"X-File-Name": "a.pdf"}).json()
    assert client.delete(f"/api/uploads/{up['id']}").json() == {"id": up["id"], "deleted": True}
    assert list(tmp_path.glob("*/*")) == []
    assert client.delete(f"/api/uploads/{up['id']}").json()["deleted"] is False


def test_image_attachment_can_be_previewed_but_others_cannot(client, db, fake, monkeypatch):
    """AI-42: 그림 첨부는 view=1로 그 형식 그대로(미리보기), 그 밖의 형식은 415 — HTML 등을 우리 출처에서 열지 않는다."""
    def handler(req: httpx.Request):
        if req.method == "GET" and req.url.path.endswith("/attachments/IMG") and req.url.params.get("$select"):
            return httpx.Response(200, json={"name": "사진.jpg", "contentType": "image/jpeg"})
        return fake(req)

    monkeypatch.setattr(graph, "transport", httpx.MockTransport(handler))
    _connect(client, db)
    r = client.get("/api/mails/1/attachments/IMG?view=1")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/mails/1/attachments/A1?view=1").status_code == 415  # 견적서.pdf
    assert client.get("/api/mails/1/attachments/A1").headers["content-type"] == "application/octet-stream"
