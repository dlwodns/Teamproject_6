def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert {k: body[k] for k in ("status", "app_mode", "db")} == {"status": "ok", "app_mode": "dev", "db": "ok"}
    assert set(body["egress"]) == {"allow", "local", "ai_service", "graph", "blocked", "hosts"}  # 외부 송신 기록(시연 ⑧)
