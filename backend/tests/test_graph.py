"""Outlook 연결(BE-7): 로그인 · 토큰 갱신 · 델타 동기화 · 보내기 · 읽음 · 옮기기. Graph는 httpx.MockTransport로 흉내 낸다."""
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.clock import real_now
from app.jobs import scheduler
from app.mail import graph, tokens
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
    assert {s.folder: s.delta_link.endswith("deltatoken=1") for s in db.scalars(select(MailSync))} == {"inbox": True, "sentitems": True}
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
    db.execute(MailSync.__table__.update().where(MailSync.folder == "inbox").values(delta_link=f"{GRAPH}/d/inbox?deltatoken=1"))
    db.commit()
    assert client.post("/api/accounts/1/sync").status_code == 200
    assert len(db.scalars(select(Mail)).all()) == 2  # 처음부터 다시 받아도 두 번 넣지 않는다


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
