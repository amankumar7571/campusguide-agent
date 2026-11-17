"""Auth + graph integration tests (run against the seeded SQLite DB)."""
from backend.auth import create_token, hash_password, verify_password
from backend.db import SessionLocal, init_db
from backend.graph import _answer_from_passages, _route


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)
    assert h != "secret123"


def test_jwt_roundtrip():
    from backend.auth import decode_token
    token = create_token("student@campus.local", "student")
    payload = decode_token(token)
    assert payload["sub"] == "student@campus.local"
    assert payload["role"] == "student"


def test_supervisor_routing():
    assert _route({"question": "How many offers did SampleTech make?"}) == "sql_agent"
    assert _route({"question": "Draft a notice about library timings"}) == "writer_agent"
    assert _route({"question": "What is the minimum attendance?"}) == "retriever_agent"


def test_answer_from_passages_has_citations():
    passages = [{"text": "Library is open 8 AM to 8 PM.",
                 "citation": "Library Timings — Library Hours"}]
    answer, citations = _answer_from_passages("library hours?", passages)
    assert "Library Timings" in answer
    assert citations == ["Library Timings — Library Hours"]


def test_answer_from_no_passages_is_idk():
    answer, citations = _answer_from_passages("quantum physics?", [])
    assert "I don't know" in answer
    assert citations == []


def test_change_password_endpoint():
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.db import SessionLocal, User

    email = "pwchange.test@campus.local"
    with TestClient(app) as client:
        try:
            r = client.post("/auth/register", json={
                "email": email, "password": "oldpass1", "role": "student"})
            assert r.status_code == 200, r.text
            headers = {"Authorization": f"Bearer {r.json()['token']}"}
            # Wrong current password -> 401.
            r = client.post("/auth/change-password", json={
                "current_password": "nope1234",
                "new_password": "newpass1"}, headers=headers)
            assert r.status_code == 401
            # A student cannot change someone else's password -> 403.
            r = client.post("/auth/change-password", json={
                "current_password": "oldpass1", "new_password": "newpass1",
                "email": "admin@campus.local"}, headers=headers)
            assert r.status_code == 403
            # Correct change -> 200; old password dead, new one works.
            r = client.post("/auth/change-password", json={
                "current_password": "oldpass1",
                "new_password": "newpass1"}, headers=headers)
            assert r.status_code == 200, r.text
            assert client.post("/auth/login", json={
                "email": email, "password": "oldpass1"}).status_code == 401
            assert client.post("/auth/login", json={
                "email": email, "password": "newpass1"}).status_code == 200
        finally:
            db = SessionLocal()
            db.query(User).filter(User.email == email).delete()
            db.commit()
            db.close()


def test_chat_returns_503_not_500_when_graph_fails(monkeypatch):
    """B-04: an embedder/graph failure must surface as a clean 503,
    never a raw 500 with a traceback."""
    from fastapi.testclient import TestClient

    import backend.app as app_mod
    from backend.db import SessionLocal, User

    monkeypatch.setattr(app_mod, "get_graph", lambda: object())
    monkeypatch.setattr(
        app_mod, "graph_ask",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    email = "chat503.test@campus.local"
    with TestClient(app_mod.app) as client:
        try:
            r = client.post("/auth/register", json={
                "email": email, "password": "testpass1", "role": "student"})
            assert r.status_code == 200, r.text
            headers = {"Authorization": f"Bearer {r.json()['token']}"}
            r = client.post("/chat", json={
                "question": "What is the attendance rule?"}, headers=headers)
            assert r.status_code == 503, r.text
            assert "temporarily unavailable" in r.text.lower()
        finally:
            db = SessionLocal()
            db.query(User).filter(User.email == email).delete()
            db.commit()
            db.close()


def test_answer_quotes_top_five_passages():
    passages = [{"text": f"Passage {i} text.",
                 "citation": f"Doc — Section {i}"} for i in range(5)]
    answer, _ = _answer_from_passages("q?", passages)
    for i in range(5):
        assert f"Section {i}" in answer
