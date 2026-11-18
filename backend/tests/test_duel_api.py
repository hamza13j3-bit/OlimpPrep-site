import json
import time
from datetime import timedelta

import pytest

from app.main import app
from app.modules.checker import service as checker_service
from app.modules.checker.router import get_queue
from app.modules.duel import presence, service
from app.modules.problems import service as ps
from tests.conftest import auth, register, write_note

SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"
WRONG_PY = "print(-1)\n"


class SyncQueue:
    def __init__(self, factory):
        self.factory = factory

    def submit(self, sid):
        with self.factory() as db:
            checker_service.process_submission(db, sid)


def problem_payload(rating):
    return {
        "rating": rating,
        "tags": ["math"],
        "translations": {"kk": {"title": f"Қосынды {rating}", "statement": "a+b"}},
        "subtasks": [
            {"points": 50, "tests": [{"input": "1 2\n", "output": "3\n", "is_example": True}]},
            {"points": 50, "tests": [{"input": "10 20\n", "output": "30\n"}]},
        ],
    }


@pytest.fixture()
def env(client):
    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    app.dependency_overrides[get_queue] = lambda: SyncQueue(client.session_factory)
    admin = register(client, "admin@example.com")
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    c = register(client, "c@example.com")
    h = lambda r: auth(r["access_token"])  # noqa: E731
    for rating in (1100, 1150, 1200, 1250):
        assert client.post("/problems", json=problem_payload(rating), headers=h(admin)).status_code == 201
    return client, h(admin), (h(a), a["user"]["id"]), (h(b), b["user"]["id"]), (h(c), c["user"]["id"])


def start_duel(client, ha, hb, ida, idb):
    presence.connect(ida)
    presence.connect(idb)
    assert client.post("/duel/queue", headers=ha).status_code == 202
    assert client.post("/duel/queue", headers=hb).status_code == 202
    with client.session_factory() as db:
        result = service.tick(db, service.now())
    assert len(result.created) == 1
    return client.get("/duel/me", headers=ha).json()["match"]


def submit(client, headers, match_id, problem_id, code):
    r = client.post(
        f"/duel/matches/{match_id}/submit",
        json={"problem_id": problem_id, "language": "python", "code": code},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return client.get(f"/submissions/{r.json()['id']}", headers=headers).json()


# ------------------------------------------ queue ------------------------------------


def test_queue_endpoints(env):
    client, _, (ha, ida), _, _ = env
    assert client.post("/duel/queue").status_code == 401
    assert client.get("/duel/me", headers=ha).json() == {"status": "idle", "last_match_id": None}
    r = client.post("/duel/queue", headers=ha)
    assert r.status_code == 202 and r.json()["status"] == "waiting"
    assert client.post("/duel/queue", headers=ha).status_code == 409  # already waiting
    assert client.get("/duel/me", headers=ha).json()["status"] == "waiting"
    assert client.delete("/duel/queue", headers=ha).status_code == 204
    assert client.delete("/duel/queue", headers=ha).status_code == 409
    assert client.get("/duel/me", headers=ha).json()["status"] == "idle"


def test_blocked_user_cannot_join(env):
    client, admin, (ha, ida), _, _ = env
    client.patch(f"/admin/users/{ida}/block", json={"blocked": True}, headers=admin)
    assert client.post("/duel/queue", headers=ha).status_code == 403


def test_cannot_queue_during_a_duel(env):
    client, _, (ha, ida), (hb, idb), _ = env
    start_duel(client, ha, hb, ida, idb)
    assert client.post("/duel/queue", headers=ha).status_code == 409


# ---------------------------------------- full duel ----------------------------------


def test_full_duel_first_to_solve_all_wins(env):
    client, _, (ha, ida), (hb, idb), _ = env
    m = start_duel(client, ha, hb, ida, idb)
    mid, problems = m["id"], [p["problem_id"] for p in m["problems"]]
    assert len(problems) == 3 and m["opponent"] == {"solved": 0, "total": 3, "connected": True}
    assert 3590 <= m["remaining_seconds"] <= 3600

    # B has one correct and one wrong answer; A solves everything
    assert submit(client, hb, mid, problems[0], SUM_PY)["solved"] is True
    assert submit(client, hb, mid, problems[1], WRONG_PY)["solved"] is False
    opp_view = client.get("/duel/me", headers=ha).json()["match"]["opponent"]
    assert opp_view["solved"] == 1  # A sees only B's count
    for p in problems[:2]:
        assert submit(client, ha, mid, p, SUM_PY)["solved"] is True
    assert client.get("/duel/me", headers=ha).json()["status"] == "active"
    last = submit(client, ha, mid, problems[2], SUM_PY)
    assert (last["tests_passed"], last["tests_total"], last["solved"]) == (2, 2, True)

    for h in (ha, hb):
        s = client.get("/duel/me", headers=h).json()
        assert s["status"] == "idle" and s["last_match_id"] == mid
    r = client.get(f"/duel/matches/{mid}/result", headers=hb)
    assert r.status_code == 200
    body = r.json()
    assert body["winner_id"] == ida and body["reason"] == "all_solved" and body["draw"] is False
    pa = next(p for p in body["players"] if p["user_id"] == ida)
    pb = next(p for p in body["players"] if p["user_id"] == idb)
    assert (pa["solved"], pa["total_score"]) == (3, 3.0)
    assert (pb["solved"], pb["failed_submissions"]) == (1, 1)
    assert pb["problems"][1]["failed_submissions"] == 1 and pb["problems"][1]["solved"] is False
    assert (pa["rating_after"], pb["rating_after"]) == (1216.0, 1184.0)

    assert client.get("/duel/rating", headers=ha).json() == {"rating": 1216.0, "games": 1, "wins": 1, "losses": 0, "draws": 0}
    assert client.get("/duel/matches", headers=hb).json()[0]["result"] == "loss"


def test_duels_do_not_change_training_ratings_but_do_count_as_solved(env):
    client, _, (ha, ida), (hb, idb), _ = env
    m = start_duel(client, ha, hb, ida, idb)
    p = m["problems"][0]["problem_id"]
    submit(client, ha, m["id"], p, SUM_PY)
    assert client.get("/rating/me", headers=ha).json()["attempts"] == 0  # training rating untouched
    items = client.get("/archive/problems", headers=ha).json()["items"]
    assert next(i for i in items if i["number"] == p)["status"] == "solved"  # solved=true counts
    assert next(i for i in items if i["number"] == p)["solved_count"] == 1
    # normal submissions are still rated
    other = next(i["number"] for i in items if i["number"] not in [x["problem_id"] for x in m["problems"]])
    write_note(client, ha, other)
    r = client.post("/submissions", json={"problem_id": other, "language": "python", "code": SUM_PY}, headers=ha)
    client.get(f"/submissions/{r.json()['id']}", headers=ha)
    assert client.get("/rating/me", headers=ha).json()["attempts"] == 1


def test_solved_problems_are_not_offered_in_the_next_duel(env):
    client, admin, (ha, ida), (hb, idb), (hc, idc) = env
    m = start_duel(client, ha, hb, ida, idb)
    first = [p["problem_id"] for p in m["problems"]]
    for p in first:
        submit(client, ha, m["id"], p, SUM_PY)  # A wins and has now solved those three
    client.post("/problems", json=problem_payload(1300), headers=admin)
    presence.connect(idc)
    client.post("/duel/queue", headers=ha)
    client.post("/duel/queue", headers=hc)
    with client.session_factory() as db:
        service.tick(db, service.now())
    # only 1 problem is unsolved by A: no 3-problem match is possible
    assert client.get("/duel/me", headers=ha).json()["status"] == "waiting"


def test_nothing_about_the_opponents_code_is_ever_returned(env):
    client, _, (ha, ida), (hb, idb), _ = env
    m = start_duel(client, ha, hb, ida, idb)
    marker = "SECRET_MARKER_12345"
    submit(client, ha, m["id"], m["problems"][0]["problem_id"], f"# {marker}\n" + SUM_PY)
    for url in ("/duel/me", f"/duel/matches/{m['id']}", "/duel/matches", "/duel/rating"):
        assert marker not in client.get(url, headers=hb).text, url
    # B cannot read A's submission either
    sid = client.get("/submissions", headers=ha).json()[0]["id"]
    assert client.get(f"/submissions/{sid}", headers=hb).status_code == 404


# ------------------------------------------ errors -----------------------------------


def test_submit_errors(env):
    client, _, (ha, ida), (hb, idb), (hc, idc) = env
    m = start_duel(client, ha, hb, ida, idb)
    mid, p = m["id"], m["problems"][0]["problem_id"]
    body = {"problem_id": p, "language": "python", "code": SUM_PY}
    url = f"/duel/matches/{mid}/submit"
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json=body, headers=hc).status_code == 404  # not a participant
    assert client.post("/duel/matches/999/submit", json=body, headers=ha).status_code == 404
    outside = client.get("/archive/problems").json()["items"]
    outside = next(i["number"] for i in outside if i["number"] not in [x["problem_id"] for x in m["problems"]])
    assert client.post(url, json={**body, "problem_id": outside}, headers=ha).status_code == 422
    assert client.post(url, json={**body, "language": "java"}, headers=ha).status_code == 422
    assert submit(client, ha, mid, p, SUM_PY)["solved"] is True
    assert client.post(url, json=body, headers=ha).status_code == 409  # already solved


def test_cannot_submit_to_a_finished_match(env):
    client, _, (ha, ida), (hb, idb), _ = env
    m = start_duel(client, ha, hb, ida, idb)
    with client.session_factory() as db:
        service.tick(db, service.now() + timedelta(hours=2))  # deadline passed
    body = {"problem_id": m["problems"][0]["problem_id"], "language": "python", "code": SUM_PY}
    assert client.post(f"/duel/matches/{m['id']}/submit", json=body, headers=ha).status_code == 409


def test_result_access_rules(env):
    client, admin, (ha, ida), (hb, idb), (hc, idc) = env
    m = start_duel(client, ha, hb, ida, idb)
    url = f"/duel/matches/{m['id']}/result"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=ha).status_code == 409  # not finished yet
    assert client.get(f"/duel/matches/{m['id']}", headers=hc).status_code == 404
    with client.session_factory() as db:
        service.tick(db, service.now() + timedelta(hours=2))
    assert client.get(url, headers=hc).status_code == 404  # strangers learn nothing
    assert client.get(url, headers=admin).status_code == 200
    r = client.get(url, headers=ha).json()
    assert r["draw"] is True and r["winner_id"] is None  # nobody solved anything
    assert client.get(f"/duel/matches/{m['id']}", headers=ha).json() == {"status": "finished", "match_id": m["id"]}
    assert client.get("/duel/matches/999/result", headers=ha).status_code == 404


def test_timer_is_server_side(env):
    client, _, (ha, ida), (hb, idb), _ = env
    m = start_duel(client, ha, hb, ida, idb)
    # the client cannot influence the clock: no endpoint accepts a time
    r = client.post(
        f"/duel/matches/{m['id']}/submit",
        json={"problem_id": m["problems"][0]["problem_id"], "language": "python", "code": SUM_PY, "at": "2099-01-01"},
        headers=ha,
    )
    assert r.status_code == 202  # unknown field ignored
    remaining = client.get("/duel/me", headers=ha).json()["match"]["remaining_seconds"]
    time.sleep(1.1)
    assert client.get("/duel/me", headers=ha).json()["match"]["remaining_seconds"] < remaining
    assert "remaining_seconds" in json.dumps(client.get("/duel/me", headers=hb).json())
