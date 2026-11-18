import pytest

from app.main import app
from app.modules.checker import service
from app.modules.checker.jobs import CheckQueue
from app.modules.checker.router import get_queue
from tests.conftest import auth, register, write_note

SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"
WRONG_PY = "print(0)\n"
RESULT_KEYS = {"id", "tests_passed", "tests_total", "score", "solved"}


class SyncQueue:
    """Processes immediately, using the test database."""

    def __init__(self, factory):
        self.factory = factory

    def submit(self, sid):
        with self.factory() as db:
            service.process_submission(db, sid)


class NullQueue:
    def submit(self, sid):
        pass


def problem_payload(**over):
    body = {
        "rating": 900,
        "tags": ["math"],
        "time_limit_ms": 1000,
        "translations": {"kk": {"title": "Қосынды", "statement": "a+b"}},
        "subtasks": [
            {"points": 50, "tests": [{"input": "1 2\n", "output": "3\n", "is_example": True}]},
            {"points": 50, "tests": [{"input": "10 20\n", "output": "30\n"}]},
        ],
    }
    body.update(over)
    return body


@pytest.fixture()
def env(client):
    from app.modules.problems import service as ps

    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    app.dependency_overrides[get_queue] = lambda: SyncQueue(client.session_factory)
    admin = auth(register(client, "admin@example.com")["access_token"])
    user = register(client, "user@example.com")
    pid = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    return client, admin, auth(user["access_token"]), user["user"]["id"], pid


def submit(client, headers, pid, code=SUM_PY, language="python"):
    write_note(client, headers, pid)  # the editor needs the idea note
    r = client.post(
        "/submissions", json={"problem_id": pid, "language": language, "code": code}, headers=headers
    )
    assert r.status_code == 202, r.text
    return r.json()["id"]


def test_submit_and_result_has_only_the_four_fields(env):
    client, _, user, _, pid = env
    sid = submit(client, user, pid)
    r = client.get(f"/submissions/{sid}", headers=user)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == RESULT_KEYS
    assert (body["tests_passed"], body["tests_total"], body["score"], body["solved"]) == (2, 2, 1.0, True)


def test_wrong_solution_partial_score(env):
    client, _, user, _, pid = env
    code = "a, b = map(int, input().split())\nprint(a + b if a < 5 else 0)\n"
    body = client.get(f"/submissions/{submit(client, user, pid, code)}", headers=user).json()
    assert (body["tests_passed"], body["tests_total"]) == (1, 2)
    assert body["score"] == pytest.approx(0.5) and body["solved"] is False
    assert set(body) == RESULT_KEYS  # no verdict-like extras


def test_pending_submission_returns_202_without_result(env):
    client, _, user, _, pid = env
    app.dependency_overrides[get_queue] = lambda: NullQueue()
    sid = submit(client, user, pid)
    r = client.get(f"/submissions/{sid}", headers=user)
    assert r.status_code == 202 and r.json() == {"id": sid}
    # and nothing pending shows up in the history
    assert client.get("/submissions", headers=user).json() == []


def test_pending_limit(env):
    client, _, user, _, pid = env
    app.dependency_overrides[get_queue] = lambda: NullQueue()
    for _ in range(service.MAX_PENDING_PER_USER):
        submit(client, user, pid)
    r = client.post("/submissions", json={"problem_id": pid, "language": "python", "code": "x"}, headers=user)
    assert r.status_code == 429


def test_auth_and_validation(env):
    client, admin, user, _, pid = env
    ok = {"problem_id": pid, "language": "python", "code": "print(1)"}
    assert client.post("/submissions", json=ok).status_code == 401
    assert client.post("/submissions", json={**ok, "language": "java"}, headers=user).status_code == 422
    assert client.post("/submissions", json={**ok, "code": ""}, headers=user).status_code == 422
    assert client.post("/submissions", json={**ok, "code": "x" * 70_000}, headers=user).status_code == 422
    assert client.post("/submissions", json={**ok, "problem_id": 999}, headers=user).status_code == 404


def test_blocked_user_cannot_submit(env):
    client, admin, user, uid, pid = env
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    r = client.post("/submissions", json={"problem_id": pid, "language": "python", "code": "x"}, headers=user)
    assert r.status_code == 403


def test_submission_visibility(env):
    client, admin, user, _, pid = env
    sid = submit(client, user, pid)
    other = auth(register(client, "other@example.com")["access_token"])
    assert client.get(f"/submissions/{sid}", headers=other).status_code == 404
    assert client.get(f"/submissions/{sid}", headers=admin).status_code == 200
    assert client.get(f"/submissions/{sid}").status_code == 401
    assert client.get("/submissions/999", headers=user).status_code == 404


def test_history_and_summary(env):
    client, _, user, _, pid = env
    submit(client, user, pid, WRONG_PY)
    submit(client, user, pid, SUM_PY)
    hist = client.get(f"/submissions?problem_id={pid}", headers=user).json()
    assert len(hist) == 2 and hist[0]["solved"] is True and hist[1]["solved"] is False  # newest first
    assert set(hist[0]) == RESULT_KEYS | {"problem_id", "language", "created_at"}
    s = client.get(f"/submissions/problem/{pid}/summary", headers=user).json()
    assert s == {"solved_count": 1, "best_score": 1.0}
    other = auth(register(client, "other@example.com")["access_token"])
    s2 = client.get(f"/submissions/problem/{pid}/summary", headers=other).json()
    assert s2 == {"solved_count": 1, "best_score": 0.0}
    anon = client.get(f"/submissions/problem/{pid}/summary")  # public: "N people solved"
    assert anon.status_code == 200 and anon.json() == {"solved_count": 1, "best_score": 0.0}


def test_solving_unlocks_hidden_tags(env):
    client, admin, user, _, _ = env
    pid = client.post("/problems", json=problem_payload(hide_tags_until_solved=True), headers=admin).json()["id"]
    assert client.get(f"/problems/{pid}", headers=user).json()["tags"] == []
    submit(client, user, pid, WRONG_PY)
    assert client.get(f"/problems/{pid}", headers=user).json()["tags_hidden"] is True  # attempted != solved
    submit(client, user, pid, SUM_PY)
    shown = client.get(f"/problems/{pid}", headers=user).json()
    assert shown["tags"] == ["math"] and shown["tags_hidden"] is False


def test_infinite_loop_via_api_is_just_not_passed(env):
    client, admin, user, _, _ = env
    pid = client.post("/problems", json=problem_payload(time_limit_ms=300), headers=admin).json()["id"]
    body = client.get(f"/submissions/{submit(client, user, pid, 'while True: pass')}", headers=user).json()
    assert (body["tests_passed"], body["score"], body["solved"]) == (0, 0.0, False)
    assert set(body) == RESULT_KEYS


def test_deleted_problem_submission_does_not_crash(env):
    client, admin, user, _, pid = env
    app.dependency_overrides[get_queue] = lambda: NullQueue()
    sid = submit(client, user, pid)
    with client.session_factory() as db:
        from app.modules.problems.models import Problem

        db.execute(Problem.__table__.delete())  # bypass FK pragma-less in-memory DB
        db.commit()
        service.process_submission(db, sid)  # must not raise
    assert client.get(f"/submissions/{sid}", headers=user).status_code == 200


def test_background_queue_processes_and_recovers(env):
    client, _, user, _, pid = env
    app.dependency_overrides[get_queue] = lambda: NullQueue()
    sid = submit(client, user, pid)  # stays queued (as after a crash)
    with client.session_factory() as db:
        from app.modules.checker.models import STATE_RUNNING, Submission

        db.get(Submission, sid).state = STATE_RUNNING  # interrupted mid-check
        db.commit()
    q = CheckQueue(client.session_factory, workers=2)
    q.start()
    try:
        q.recover()
        q.join()
    finally:
        q.stop()
    body = client.get(f"/submissions/{sid}", headers=user).json()
    assert body["solved"] is True and body["tests_total"] == 2
