"""WebSocket behaviour. Uses a file-based SQLite database (several real connections) because the
socket handlers run in other threads, like in production."""

import json
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.core import db as core_db
from app.main import app
from app.modules.checker import service as checker_service
from app.modules.checker.router import get_queue
from app.modules.duel import presence, service, ws
from app.modules.duel.deps import get_session_factory
from app.modules.duel.models import DuelParticipant
from app.modules.duel.waiting import waiting
from app.modules.problems import service as ps
from tests.conftest import auth, register

SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"
MARKER = "TOP_SECRET_SOLUTION_MARKER"


class SyncQueue:
    def __init__(self, factory):
        self.factory = factory

    def submit(self, sid):
        with self.factory() as db:
            checker_service.process_submission(db, sid)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'duel.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    core_db.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[core_db.get_db] = get_db
    app.dependency_overrides[get_session_factory] = lambda: Session
    app.dependency_overrides[get_queue] = lambda: SyncQueue(Session)
    monkeypatch.setattr(ws, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(ws, "HEARTBEAT_SECONDS", 0.3)
    waiting.clear()
    presence.clear()

    client = TestClient(app)
    with Session() as db:
        ps.ensure_default_tags(db)
    admin = register(client, "admin@example.com")
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    for rating in (1100, 1150, 1200):
        body = {
            "rating": rating, "tags": ["math"],
            "translations": {"kk": {"title": f"P{rating}", "statement": "a+b"}},
            "subtasks": [{"points": 100, "tests": [{"input": "1 2\n", "output": "3\n", "is_example": True}]}],
        }
        assert client.post("/problems", json=body, headers=auth(admin["access_token"])).status_code == 201
    yield client, Session, a, b, admin
    app.dependency_overrides.clear()
    engine.dispose()


def open_socket(client, token):
    sock = client.websocket_connect("/duel/ws")
    return sock


def login(sock, token):
    sock.send_json({"type": "auth", "token": token})
    assert sock.receive_json() == {"type": "auth_ok"}


def wait_for(sock, predicate, tries=100):
    for _ in range(tries):
        msg = sock.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError("expected message never arrived")


def poll(fn, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def disconnected_at(Session, user_id):
    with Session() as db:
        return db.query(DuelParticipant).filter_by(user_id=user_id).one().disconnected_at


# ------------------------------------------ auth -------------------------------------


def test_first_frame_must_be_a_valid_auth(env):
    client, Session, a, b, _ = env
    for first in ({"type": "hello"}, {"type": "auth", "token": "garbage"}, {"type": "auth"}, [1, 2]):
        with client.websocket_connect("/duel/ws") as sock:
            sock.send_json(first)
            with pytest.raises(WebSocketDisconnect) as exc:
                sock.receive_json()
            assert exc.value.code == 4401, first


def test_blocked_user_is_refused(env):
    client, Session, a, b, admin = env
    client.patch(f"/admin/users/{a['user']['id']}/block", json={"blocked": True}, headers=auth(admin["access_token"]))
    with client.websocket_connect("/duel/ws") as sock:
        sock.send_json({"type": "auth", "token": a["access_token"]})
        with pytest.raises(WebSocketDisconnect) as exc:
            sock.receive_json()
        assert exc.value.code == 4403


def test_authenticated_socket_gets_state_and_answers_ping(env):
    client, Session, a, b, _ = env
    with client.websocket_connect("/duel/ws") as sock:
        login(sock, a["access_token"])
        assert wait_for(sock, lambda m: m["type"] == "state") == {
            "type": "state", "status": "idle", "last_match_id": None
        }
        sock.send_json({"type": "ping"})
        assert wait_for(sock, lambda m: m["type"] == "pong")["type"] == "pong"
        sock.send_text("not json at all")  # garbage is ignored, the socket stays alive
        sock.send_json({"type": "ping"})
        wait_for(sock, lambda m: m["type"] == "pong")


# --------------------------------------- live match ----------------------------------


def test_match_is_pushed_and_the_opponent_is_only_a_count(env):
    client, Session, a, b, _ = env
    ha, hb = auth(a["access_token"]), auth(b["access_token"])
    with client.websocket_connect("/duel/ws") as sa, client.websocket_connect("/duel/ws") as sb:
        login(sa, a["access_token"])
        login(sb, b["access_token"])
        assert client.post("/duel/queue", headers=ha).status_code == 202
        assert client.post("/duel/queue", headers=hb).status_code == 202
        wait_for(sa, lambda m: m.get("status") == "waiting")
        with Session() as db:
            assert len(service.tick(db, service.now()).created) == 1  # the supervisor's job

        seen = []
        msg_a = wait_for(sa, lambda m: seen.append(m) or m.get("status") == "active")
        msg_b = wait_for(sb, lambda m: seen.append(m) or m.get("status") == "active")
        match = msg_b["match"]
        assert set(match["opponent"]) == {"solved", "total", "connected"}
        assert match["opponent"]["solved"] == 0 and match["me"]["total"] == 3
        mid, first = msg_a["match"]["id"], msg_a["match"]["problems"][0]["problem_id"]

        # A submits code containing a marker; B's socket must show a count and nothing else
        r = client.post(
            f"/duel/matches/{mid}/submit",
            json={"problem_id": first, "language": "python", "code": f"# {MARKER}\n" + SUM_PY},
            headers=ha,
        )
        assert r.status_code == 202
        updated = wait_for(sb, lambda m: seen.append(m) or m.get("match", {}).get("opponent", {}).get("solved") == 1)
        assert updated["match"]["me"]["solved"] == 0
        for m in seen:
            text = json.dumps(m)
            assert MARKER not in text and "code" not in text and "submission" not in text
        # A sees their own progress
        mine = wait_for(sa, lambda m: m.get("match", {}).get("me", {}).get("solved") == 1)
        assert mine["match"]["problems"][0]["solved"] is True


def test_finish_is_pushed_to_both_players(env):
    client, Session, a, b, _ = env
    ha, hb = auth(a["access_token"]), auth(b["access_token"])
    with client.websocket_connect("/duel/ws") as sa, client.websocket_connect("/duel/ws") as sb:
        login(sa, a["access_token"])
        login(sb, b["access_token"])
        client.post("/duel/queue", headers=ha)
        client.post("/duel/queue", headers=hb)
        with Session() as db:
            service.tick(db, service.now())
        active = wait_for(sa, lambda m: m.get("status") == "active")
        with Session() as db:
            service.tick(db, service.now() + timedelta(hours=2))  # the deadline passes (server clock)
        # (skip the idle states that were buffered before the match existed)
        done_a = wait_for(sa, lambda m: m.get("status") == "idle" and m.get("last_match_id"))
        done_b = wait_for(sb, lambda m: m.get("status") == "idle" and m.get("last_match_id"))
        assert done_a["last_match_id"] == done_b["last_match_id"] == active["match"]["id"]


# ---------------------------------------- reconnect ----------------------------------


def test_closing_the_socket_starts_the_grace_and_reconnecting_clears_it(env):
    client, Session, a, b, _ = env
    ha, hb = auth(a["access_token"]), auth(b["access_token"])
    uid_a, uid_b = a["user"]["id"], b["user"]["id"]
    sb = client.websocket_connect("/duel/ws")
    with sb as sock_b:
        login(sock_b, b["access_token"])
        with client.websocket_connect("/duel/ws") as sock_a:
            login(sock_a, a["access_token"])
            client.post("/duel/queue", headers=ha)
            client.post("/duel/queue", headers=hb)
            with Session() as db:
                service.tick(db, service.now())
            wait_for(sock_a, lambda m: m.get("status") == "active")
            assert disconnected_at(Session, uid_a) is None
        # A's only socket closed
        assert poll(lambda: disconnected_at(Session, uid_a) is not None), "disconnect was not recorded"
        assert not presence.is_connected(uid_a)
        opp = wait_for(sock_b, lambda m: m.get("match", {}).get("opponent", {}).get("connected") is False)
        assert opp["match"]["opponent"]["solved"] == 0

        # back within the grace period: the countdown is cancelled and B is told
        with Session() as db:
            assert service.tick(db, service.now() + timedelta(seconds=30)).finished == []
        with client.websocket_connect("/duel/ws") as sock_a2:
            login(sock_a2, a["access_token"])
            assert poll(lambda: disconnected_at(Session, uid_a) is None)
            wait_for(sock_b, lambda m: m.get("match", {}).get("opponent", {}).get("connected") is True)
            wait_for(sock_a2, lambda m: m.get("status") == "active")  # state restored for the player
        # ... and leaving again for 60 s is a loss
        assert poll(lambda: disconnected_at(Session, uid_a) is not None)
        with Session() as db:
            assert service.tick(db, service.now() + timedelta(seconds=61)).finished
        done = wait_for(sock_b, lambda m: m.get("status") == "idle" and m.get("last_match_id"))
        r = client.get(f"/duel/matches/{done['last_match_id']}/result", headers=hb).json()
        assert r["winner_id"] == uid_b and r["reason"] == "forfeit"


def test_a_second_tab_keeps_the_player_present(env):
    client, Session, a, b, _ = env
    ha, hb = auth(a["access_token"]), auth(b["access_token"])
    uid_a = a["user"]["id"]
    with client.websocket_connect("/duel/ws") as s1, client.websocket_connect("/duel/ws") as sb:
        login(s1, a["access_token"])
        login(sb, b["access_token"])
        client.post("/duel/queue", headers=ha)
        client.post("/duel/queue", headers=hb)
        with Session() as db:
            service.tick(db, service.now())
        wait_for(s1, lambda m: m.get("status") == "active")
        with client.websocket_connect("/duel/ws") as s2:
            login(s2, a["access_token"])
        # one tab closed, one still open: no disconnect
        time.sleep(0.3)
        assert presence.is_connected(uid_a) and disconnected_at(Session, uid_a) is None
