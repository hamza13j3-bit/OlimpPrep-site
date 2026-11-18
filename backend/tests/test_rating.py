import pytest

from app.main import app
from app.modules.checker import service as checker_service
from app.modules.checker.router import get_queue
from app.modules.rating import elo
from app.modules.rating import service as rating_service
from app.modules.rating.models import PlayerRating, RatingEvent
from tests.conftest import auth, register, write_note

SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"
HALF_PY = "a, b = map(int, input().split())\nprint(a + b if a < 5 else 0)\n"  # passes subtask 1 only
FAIL_PY = "print(0)\n"


class SyncQueue:
    def __init__(self, factory):
        self.factory = factory

    def submit(self, sid):
        with self.factory() as db:
            checker_service.process_submission(db, sid)


def problem_payload(rating=1200, tags=("math", "greedy"), **over):
    body = {
        "rating": rating,
        "tags": list(tags),
        "translations": {"kk": {"title": "Қосынды", "statement": "a+b"}},
        "subtasks": [
            {"points": 50, "tests": [{"input": "1 2\n", "output": "3\n", "is_example": True}]},
            {"points": 50, "tests": [{"input": "10 20\n", "output": "30\n"}]},
        ],
        "hints": [
            {"level": 1, "lang": "kk", "text": "бағыт"},
            {"level": 2, "lang": "kk", "text": "алгоритм"},
            {"level": 3, "lang": "kk", "text": "псевдокод"},
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
    uh = auth(user["access_token"])
    pid = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    return client, admin, uh, user["user"]["id"], pid


def submit(client, headers, pid, code):
    write_note(client, headers, pid)
    r = client.post("/submissions", json={"problem_id": pid, "language": "python", "code": code}, headers=headers)
    assert r.status_code == 202, r.text
    return client.get(f"/submissions/{r.json()['id']}", headers=headers).json()


def my_rating(client, headers):
    return client.get("/rating/me", headers=headers).json()


def problem_rating(client, admin, pid):
    return client.get(f"/problems/{pid}/admin", headers=admin).json()["rating"]


def test_new_user_defaults(env):
    client, _, user, _, _ = env
    assert my_rating(client, user) == {"rating": 1200.0, "attempts": 0, "tags": []}
    assert client.get("/rating/me/history", headers=user).json() == []
    assert client.get("/rating/me").status_code == 401


def test_solving_raises_player_and_lowers_problem(env):
    client, admin, user, _, pid = env
    assert submit(client, user, pid, SUM_PY)["solved"] is True
    r = my_rating(client, user)
    assert r["rating"] == pytest.approx(1220.0)  # K=40, E=0.5, S=1
    assert r["attempts"] == 1
    assert {t["tag"] for t in r["tags"]} == {"math", "greedy"}
    assert all(t["rating"] == pytest.approx(1220.0) and t["attempts"] == 1 for t in r["tags"])
    assert problem_rating(client, admin, pid) == 1196  # 1200 - 8 * (1 - 0.5)


def test_failing_lowers_player_and_raises_problem(env):
    client, admin, user, _, pid = env
    submit(client, user, pid, FAIL_PY)
    assert my_rating(client, user)["rating"] == pytest.approx(1180.0)
    assert problem_rating(client, admin, pid) == 1204


def test_partial_score_uses_s(env):
    client, _, user, _, pid = env
    res = submit(client, user, pid, HALF_PY)
    assert res["score"] == pytest.approx(0.5)
    assert my_rating(client, user)["rating"] == pytest.approx(1200.0)  # S == E


def test_history_endpoint(env):
    client, _, user, _, pid = env
    submit(client, user, pid, FAIL_PY)
    submit(client, user, pid, SUM_PY)
    h = client.get("/rating/me/history", headers=user).json()
    # fail: 1200 -> 1180, problem becomes 1204; then solve with K=40 against 1204
    e2 = elo.expected(1180, 1204)
    assert [(p["old_rating"], p["new_rating"]) for p in h] == [
        (1200.0, 1180.0),
        (1180.0, pytest.approx(round(1180 + 40 * (1 - e2), 2), abs=0.01)),
    ]
    assert h[0]["new_rating"] == pytest.approx(h[1]["old_rating"])  # chain is continuous
    assert h[0]["problem_id"] == pid
    tag = client.get("/rating/me/history?tag=math", headers=user).json()
    assert len(tag) == 2
    assert client.get("/rating/me/history?tag=dp", headers=user).json() == []


def test_only_improvements_are_rated(env):
    client, _, user, _, pid = env
    submit(client, user, pid, FAIL_PY)  # rated (first)
    after_first = my_rating(client, user)
    submit(client, user, pid, FAIL_PY)  # same score: ignored
    assert my_rating(client, user) == after_first
    submit(client, user, pid, HALF_PY)  # better: rated
    assert my_rating(client, user)["attempts"] == 2
    submit(client, user, pid, FAIL_PY)  # worse than best: ignored
    assert my_rating(client, user)["attempts"] == 2
    submit(client, user, pid, SUM_PY)  # solved: rated
    assert my_rating(client, user)["attempts"] == 3
    done = my_rating(client, user)
    submit(client, user, pid, SUM_PY)  # already solved: nothing more to gain
    submit(client, user, pid, FAIL_PY)
    assert my_rating(client, user) == done


def test_apply_is_idempotent_per_submission(env):
    client, _, user, uid, pid = env
    sub = submit(client, user, pid, SUM_PY)
    with client.session_factory() as db:
        assert rating_service.apply_result(db, uid, sub["id"], pid, 1.0) is False
        assert db.query(RatingEvent).filter_by(submission_id=sub["id"], scope="global").count() == 1
    assert my_rating(client, user)["attempts"] == 1


def test_k_drops_after_ten_attempts(env):
    client, admin, user, uid, _ = env
    with client.session_factory() as db:
        db.add(PlayerRating(user_id=uid, rating=1200.0, attempts=10))
        db.commit()
    pid = client.post("/problems", json=problem_payload(rating=1200, tags=("math",)), headers=admin).json()["id"]
    submit(client, user, pid, SUM_PY)
    assert my_rating(client, user)["rating"] == pytest.approx(1212.0)  # K=24 * 0.5


def test_floor_in_integration(env):
    client, admin, user, uid, _ = env
    with client.session_factory() as db:
        db.add(PlayerRating(user_id=uid, rating=805.0, attempts=0))
        db.commit()
    pid = client.post("/problems", json=problem_payload(rating=800), headers=admin).json()["id"]
    submit(client, user, pid, FAIL_PY)  # would be -20 -> floored
    assert my_rating(client, user)["rating"] == 800.0
    assert problem_rating(client, admin, pid) >= 800


def test_per_tag_ratings_use_their_own_attempts(env):
    client, admin, user, _, pid = env  # tags math + greedy
    p2 = client.post("/problems", json=problem_payload(tags=("math",)), headers=admin).json()["id"]
    submit(client, user, pid, SUM_PY)
    submit(client, user, p2, SUM_PY)
    tags = {t["tag"]: t for t in my_rating(client, user)["tags"]}
    assert tags["math"]["attempts"] == 2 and tags["greedy"]["attempts"] == 1
    assert tags["math"]["rating"] > tags["greedy"]["rating"]


def test_problem_without_tags_still_rates_globally(env):
    client, admin, user, _, _ = env
    pid = client.post("/problems", json=problem_payload(tags=()), headers=admin).json()["id"]
    submit(client, user, pid, SUM_PY)
    r = my_rating(client, user)
    assert r["tags"] == [] and r["rating"] > 1200


def test_admin_edit_of_problem_rating_restarts_from_it(env):
    client, admin, user, _, pid = env
    other = auth(register(client, "o@example.com")["access_token"])
    submit(client, other, pid, SUM_PY)  # problem -> 1196
    body = problem_payload(rating=2000)
    assert client.put(f"/problems/{pid}", json=body, headers=admin).status_code == 200
    submit(client, user, pid, SUM_PY)  # player 1200 vs problem 2000 -> big gain
    assert my_rating(client, user)["rating"] > 1230
    assert problem_rating(client, admin, pid) <= 2000


# ----------------------------------- hints ------------------------------------


def test_hint_endpoints(env):
    client, _, user, _, pid = env
    assert client.post(f"/problems/{pid}/hints/1").status_code == 401
    assert client.get(f"/problems/{pid}/hints", headers=user).json() == []
    r = client.post(f"/problems/{pid}/hints/2", headers=user)
    assert r.status_code == 200 and r.json() == {"level": 2, "text": "алгоритм"}
    client.post(f"/problems/{pid}/hints/2", headers=user)  # twice: still one record
    client.post(f"/problems/{pid}/hints/1", headers=user)
    assert client.get(f"/problems/{pid}/hints", headers=user).json() == [
        {"level": 1, "text": "бағыт"},
        {"level": 2, "text": "алгоритм"},
    ]
    assert client.post(f"/problems/{pid}/hints/4", headers=user).status_code == 422
    assert client.post("/problems/999/hints/1", headers=user).status_code == 404


def test_missing_hint_is_404_and_not_recorded(env):
    client, admin, user, uid, _ = env
    pid = client.post("/problems", json=problem_payload(hints=[]), headers=admin).json()["id"]
    assert client.post(f"/problems/{pid}/hints/1", headers=user).status_code == 404
    from app.modules.problems import service as ps

    with client.session_factory() as db:
        assert ps.max_hint_level(db, uid, pid) == 0


def test_blocked_user_cannot_open_hints(env):
    client, admin, user, uid, pid = env
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    assert client.post(f"/problems/{pid}/hints/1", headers=user).status_code == 403


def test_hints_reduce_rated_score_not_the_checker_result(env):
    client, _, user, _, pid = env
    client.post(f"/problems/{pid}/hints/3", headers=user)
    res = submit(client, user, pid, SUM_PY)
    assert res["score"] == 1.0 and res["solved"] is True  # checker result untouched
    r = my_rating(client, user)
    assert r["rating"] == pytest.approx(1200 + 40 * (0.7 - 0.5))  # S_eff = 0.7
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.hint_level == 3 and ev.raw_score == 1.0 and ev.effective_score == pytest.approx(0.7)


def test_more_hints_means_smaller_gain(env):
    client, admin, user, _, _ = env
    other = auth(register(client, "o@example.com")["access_token"])
    p1 = client.post("/problems", json=problem_payload(tags=()), headers=admin).json()["id"]
    p2 = client.post("/problems", json=problem_payload(tags=()), headers=admin).json()["id"]
    client.post(f"/problems/{p1}/hints/1", headers=user)
    submit(client, user, p1, SUM_PY)  # S_eff 0.9
    submit(client, other, p2, SUM_PY)  # S_eff 1.0
    assert 1200 < my_rating(client, user)["rating"] < my_rating(client, other)["rating"]


def test_hint_opened_after_a_rated_submission_does_not_change_it(env):
    client, _, user, _, pid = env
    submit(client, user, pid, HALF_PY)  # rated with no hints
    client.post(f"/problems/{pid}/hints/3", headers=user)
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.hint_level == 0


def test_expected_matches_formula_in_history(env):
    client, _, user, uid, pid = env
    submit(client, user, pid, SUM_PY)
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.expected == pytest.approx(elo.expected(1200, 1200))
        assert ev.new_rating == pytest.approx(ev.old_rating + ev.k * (ev.effective_score - ev.expected))


@pytest.mark.parametrize("opened, multiplier", [([], 1.0), ([1], 0.9), ([2], 0.8), ([3], 0.7)])
def test_hint_multiplier_per_level(env, opened, multiplier):
    client, _, user, _, pid = env
    for level in opened:
        assert client.post(f"/problems/{pid}/hints/{level}", headers=user).status_code == 200
    submit(client, user, pid, SUM_PY)
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.effective_score == pytest.approx(multiplier)
        assert ev.new_rating == pytest.approx(1200 + 40 * (multiplier - 0.5))


def test_lowest_multiplier_of_the_used_hints_applies(env):
    client, _, user, _, pid = env
    for level in (1, 3, 2):  # order does not matter, nothing stacks
        client.post(f"/problems/{pid}/hints/{level}", headers=user)
    submit(client, user, pid, SUM_PY)
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.hint_level == 3 and ev.effective_score == pytest.approx(0.7)  # not 0.9*0.8*0.7


def test_hint_multiplier_scales_partial_scores(env):
    client, _, user, _, pid = env
    client.post(f"/problems/{pid}/hints/2", headers=user)
    res = submit(client, user, pid, HALF_PY)
    assert res["score"] == pytest.approx(0.5)  # the checker result is not touched
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.raw_score == pytest.approx(0.5) and ev.effective_score == pytest.approx(0.4)


def test_server_records_hint_usage(env):
    from app.modules.problems.models import HintUsage

    client, _, user, uid, pid = env
    client.post(f"/problems/{pid}/hints/2", headers=user)
    client.post(f"/problems/{pid}/hints/2", headers=user)  # repeat: still one record
    client.post(f"/problems/{pid}/hints/9", headers=user)  # invalid level: nothing recorded
    with client.session_factory() as db:
        rows = db.query(HintUsage).filter_by(user_id=uid, problem_id=pid).all()
        assert [r.level for r in rows] == [2] and rows[0].created_at is not None


def test_hints_of_one_user_do_not_penalise_another(env):
    client, _, user, _, pid = env
    other = auth(register(client, "o@example.com")["access_token"])
    client.post(f"/problems/{pid}/hints/3", headers=user)
    submit(client, other, pid, SUM_PY)
    with client.session_factory() as db:
        ev = db.query(RatingEvent).filter_by(scope="global").one()
        assert ev.hint_level == 0 and ev.effective_score == pytest.approx(1.0)
