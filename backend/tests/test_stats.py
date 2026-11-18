from datetime import datetime, timedelta, timezone

import pytest

from app.main import app
from app.modules.checker.router import get_queue
from app.modules.stats import service as stats
from app.modules.stats.models import RetrySchedule
from tests.conftest import auth, register
from tests.test_rating import FAIL_PY, HALF_PY, SUM_PY, SyncQueue, problem_payload, submit

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)


@pytest.fixture()
def env(client):
    from app.modules.problems import service as ps

    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    app.dependency_overrides[get_queue] = lambda: SyncQueue(client.session_factory)
    admin = auth(register(client, "admin@example.com")["access_token"])
    user = register(client, "user@example.com")
    pid = client.post("/problems", json=problem_payload(tags=("math",)), headers=admin).json()["id"]
    return client, admin, auth(user["access_token"]), user["user"]["id"], pid


def row(client, uid, pid):
    with client.session_factory() as db:
        r = db.get(RetrySchedule, (uid, pid))
        return None if r is None else (r.stage, stats._utc(r.next_due_at))


def attempt(client, uid, pid, best, now, **kw):
    with client.session_factory() as db:
        stats.record_attempt(db, uid, pid, best, now, **kw)
        db.commit()


# ------------------------------ retry-later schedule --------------------------------


def test_intervals_are_1_3_7_14_days():
    assert stats.RETRY_DAYS == (1, 3, 7, 14)


def test_first_unsolved_attempt_comes_back_after_one_day(env):
    client, _, _, uid, pid = env
    attempt(client, uid, pid, 0.5, T0)
    assert row(client, uid, pid) == (0, T0 + DAY)


def test_following_retries_move_through_3_7_14_and_stay_at_14(env):
    client, _, _, uid, pid = env
    attempt(client, uid, pid, 0.0, T0)
    now = T0 + DAY
    expected = [(1, 3), (2, 7), (3, 14), (3, 14), (3, 14)]
    for stage, days in expected:
        attempt(client, uid, pid, 0.5, now)  # retried exactly when due, still below 1
        assert row(client, uid, pid) == (stage, now + days * DAY)
        now = now + days * DAY


def test_an_early_attempt_does_not_rush_the_schedule(env):
    client, _, _, uid, pid = env
    attempt(client, uid, pid, 0.0, T0)
    attempt(client, uid, pid, 0.3, T0 + timedelta(hours=5))  # before the day is over
    assert row(client, uid, pid) == (0, T0 + DAY)


def test_solving_removes_the_problem(env):
    client, _, _, uid, pid = env
    attempt(client, uid, pid, 0.5, T0)
    attempt(client, uid, pid, 1.0, T0 + DAY)
    assert row(client, uid, pid) is None
    attempt(client, uid, pid, 1.0, T0 + 2 * DAY)  # solved problems never get scheduled
    assert row(client, uid, pid) is None


def test_duel_attempts_never_add_but_do_remove(env):
    client, _, _, uid, pid = env
    attempt(client, uid, pid, 0.0, T0, schedule=False)
    assert row(client, uid, pid) is None
    attempt(client, uid, pid, 0.0, T0)
    attempt(client, uid, pid, 1.0, T0 + DAY, schedule=False)  # solved inside a duel
    assert row(client, uid, pid) is None


def test_retry_list_orders_due_first_and_flags_them(env):
    client, admin, _, uid, p1 = env
    p2 = client.post("/problems", json=problem_payload(tags=("math",)), headers=admin).json()["id"]
    p3 = client.post("/problems", json=problem_payload(tags=("math",)), headers=admin).json()["id"]
    attempt(client, uid, p1, 0.0, T0)  # due T0+1d
    attempt(client, uid, p2, 0.0, T0 - 5 * DAY)  # due T0-4d (oldest)
    attempt(client, uid, p3, 0.0, T0 + 10 * DAY)  # due T0+11d (upcoming)
    with client.session_factory() as db:
        items = stats.retry_list(db, uid, "kk", now=T0 + 2 * DAY)
    assert [(i["problem_id"], i["due"]) for i in items] == [(p2, True), (p1, True), (p3, False)]
    assert items[0]["title"] == "Қосынды"


# --------------------------------------- API ----------------------------------------


def get_stats(client, headers):
    r = client.get("/stats/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_login(client):
    assert client.get("/stats/me").status_code == 401


def test_empty_stats_keep_every_tag_axis(env):
    client, _, user, _, _ = env
    s = get_stats(client, user)
    assert s["retry"] == []
    assert {t["tag"] for t in s["tags"]} == {
        "sorting", "recursion", "dp", "graphs", "strings", "math", "greedy", "binary-search"
    }
    assert all(t["avg_score"] == 0 and t["attempted"] == 0 for t in s["tags"])


def test_average_score_per_tag(env):
    client, admin, user, _, p1 = env  # p1: math
    p2 = client.post("/problems", json=problem_payload(tags=("math", "dp")), headers=admin).json()["id"]
    p3 = client.post("/problems", json=problem_payload(tags=("dp",)), headers=admin).json()["id"]
    submit(client, user, p1, SUM_PY)  # math 1.0
    submit(client, user, p2, HALF_PY)  # math + dp 0.5
    submit(client, user, p2, FAIL_PY)  # a worse attempt must not lower the best score
    # p3 not attempted
    tags = {t["tag"]: t for t in get_stats(client, user)["tags"]}
    assert tags["math"]["avg_score"] == pytest.approx(0.75)
    assert (tags["math"]["attempted"], tags["math"]["solved"]) == (2, 1)
    assert tags["dp"]["avg_score"] == pytest.approx(0.5)
    assert (tags["dp"]["attempted"], tags["dp"]["solved"]) == (1, 0)
    assert tags["graphs"]["attempted"] == 0
    assert p3 > 0


def test_stats_are_per_user(env):
    client, _, user, _, pid = env
    other = auth(register(client, "o@example.com")["access_token"])
    submit(client, user, pid, SUM_PY)
    assert {t["tag"]: t for t in get_stats(client, other)["tags"]}["math"]["attempted"] == 0


def test_hidden_tags_are_not_leaked_before_solving(env):
    client, admin, user, _, _ = env
    pid = client.post(
        "/problems", json=problem_payload(tags=("greedy",), hide_tags_until_solved=True), headers=admin
    ).json()["id"]
    submit(client, user, pid, HALF_PY)
    greedy = {t["tag"]: t for t in get_stats(client, user)["tags"]}["greedy"]
    assert greedy["attempted"] == 0  # unsolved problem with hidden tags is not counted
    submit(client, user, pid, SUM_PY)
    greedy = {t["tag"]: t for t in get_stats(client, user)["tags"]}["greedy"]
    assert (greedy["attempted"], greedy["avg_score"]) == (1, 1.0)


def test_failed_submission_enters_retry_list_and_solving_removes_it(env):
    client, _, user, uid, pid = env
    submit(client, user, pid, HALF_PY)
    retry = get_stats(client, user)["retry"]
    assert len(retry) == 1
    item = retry[0]
    assert (item["problem_id"], item["stage"], item["due"]) == (pid, 0, False)  # due tomorrow
    assert item["best_score"] == pytest.approx(0.5)
    due = datetime.fromisoformat(item["next_due_at"])
    assert timedelta(hours=23) < due - datetime.now(timezone.utc) <= DAY
    # make it due by moving the schedule into the past
    with client.session_factory() as db:
        r = db.get(RetrySchedule, (uid, pid))
        r.next_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert get_stats(client, user)["retry"][0]["due"] is True
    submit(client, user, pid, FAIL_PY)  # retried when due, still below 1 -> stage 1 (3 days)
    item = get_stats(client, user)["retry"][0]
    assert (item["stage"], item["due"]) == (1, False)
    assert item["best_score"] == pytest.approx(0.5)  # best, not the last
    submit(client, user, pid, SUM_PY)
    assert get_stats(client, user)["retry"] == []


def test_stats_response_has_no_verdict_labels(env):
    client, _, user, _, pid = env
    submit(client, user, pid, HALF_PY)
    text = client.get("/stats/me", headers=user).text
    for label in ("AC", "WA", "TLE", "MLE", "verdict", "accepted", "wrong"):
        assert label not in text
    s = get_stats(client, user)
    assert set(s["retry"][0]) == {"problem_id", "title", "best_score", "stage", "due", "next_due_at"}
    assert set(s["tags"][0]) == {"tag", "avg_score", "attempted", "solved"}
