import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.auth.models import User
from app.modules.checker.models import STATE_DONE, STATE_QUEUED, Submission
from app.modules.checker.service import CheckedSubmission
from app.modules.duel import presence, service, state as st
from app.modules.duel.models import DuelMatch, DuelParticipant, DuelRating
from app.modules.duel.waiting import waiting
from app.modules.problems import service as ps
from app.modules.problems.schemas import ProblemIn
from tests.conftest import register

T0 = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
DEADLINE = T0 + timedelta(seconds=st.MATCH_SECONDS)


def at(minutes: float = 0.0, seconds: float = 0.0) -> datetime:
    return T0 + timedelta(minutes=minutes, seconds=seconds)


class Env:
    def __init__(self, client, monkeypatch):
        self.client = client
        self.db = client.session_factory()
        self.t = T0
        monkeypatch.setattr(service, "now", lambda: self.t)
        ps.ensure_default_tags(self.db)
        ids = [register(client, f"u{i}@example.com")["user"]["id"] for i in range(4)]
        self.admin, self.a, self.b, self.c = ids
        self.problems: list[int] = []

    def problem(self, rating: int) -> int:
        data = ProblemIn(
            rating=rating,
            translations={"kk": {"title": f"P{rating}", "statement": "x"}},
            subtasks=[{"points": 100, "tests": [{"input": "1\n", "output": "1\n", "is_example": True}]}],
        )
        pid = ps.create_problem(self.db, data).id
        self.problems.append(pid)
        return pid

    def problems_n(self, n: int = 6) -> list[int]:
        return [self.problem(900 + 100 * i) for i in range(n)]

    def set_duel_rating(self, user: int, rating: float) -> None:
        service.get_duel_rating(self.db, user).rating = rating
        self.db.commit()

    def mark_solved_in_archive(self, user: int, problem: int) -> None:
        self.db.add(Submission(user_id=user, problem_id=problem, language="python", code="x",
                               state=STATE_DONE, score=1.0, solved=True, tests_total=1, tests_passed=1))
        self.db.commit()

    def match(self, connect: bool = True, a: int | None = None, b: int | None = None) -> int:
        a, b = a or self.a, b or self.b
        if connect:
            presence.connect(a)
            presence.connect(b)
        service.join_queue(self.db, a, self.t)
        service.join_queue(self.db, b, self.t)
        created = service.matchmake(self.db, self.t, random.Random(1))
        assert len(created) == 1
        return created[0]

    def problems_of(self, match_id: int) -> list[int]:
        return list(st_problems(self.db, match_id))

    def checked(self, match_id, user, problem, *, solved, minutes, score=None):
        """Feed one finished duel submission to the duel module, `minutes` after the start."""
        score = (1.0 if solved else 0.0) if score is None else score
        self.t = max(self.t, at(minutes))
        service.on_checked(
            self.db,
            CheckedSubmission(user_id=user, problem_id=problem, submission_id=0, duel_match_id=match_id,
                              created_at=at(minutes), score=score, solved=solved, tests_total=1),
        )

    def load(self, match_id):
        return service._load(self.db, match_id)

    def rating(self, user) -> DuelRating:
        self.db.expire_all()
        return self.db.get(DuelRating, user)

    def row(self, match_id) -> DuelMatch:
        self.db.expire_all()
        return self.db.get(DuelMatch, match_id)


def st_problems(db, match_id):
    from sqlalchemy import select

    from app.modules.duel.models import DuelMatchProblem

    return db.scalars(
        select(DuelMatchProblem.problem_id).where(DuelMatchProblem.match_id == match_id).order_by(DuelMatchProblem.position)
    )


@pytest.fixture()
def env(client, monkeypatch):
    e = Env(client, monkeypatch)
    yield e
    e.db.close()


# ------------------------------------- queue / matchmaking ---------------------------


def test_match_gets_three_problems_neither_player_solved(env):
    p = env.problems_n(6)
    env.mark_solved_in_archive(env.a, p[0])
    env.mark_solved_in_archive(env.a, p[1])
    env.mark_solved_in_archive(env.b, p[2])
    mid = env.match()
    assert sorted(env.problems_of(mid)) == [p[3], p[4], p[5]]  # the only ones left
    row = env.row(mid)
    assert row.status == "active"
    assert service._aware(row.ends_at) - service._aware(row.started_at) == timedelta(minutes=60)
    assert len(waiting) == 0  # both left the waiting list


def test_problems_are_ordered_easiest_first_and_come_from_the_pairs_range(env):
    for r in (800, 900, 1000, 1900, 2000, *range(1190, 1290, 10)):  # ten problems right around 1200
        env.problem(r)
    mid = env.match()
    ratings = [ps.get_problem(env.db, pid).rating for pid in env.problems_of(mid)]
    assert ratings == sorted(ratings) and len(ratings) == 3
    assert all(1190 <= r <= 1270 for r in ratings)  # from the 9 closest to 1200, never 800 / 2000


def test_not_enough_unsolved_problems_keeps_players_waiting(env):
    p = env.problems_n(4)
    env.mark_solved_in_archive(env.a, p[0])
    env.mark_solved_in_archive(env.b, p[1])  # only 2 problems are unsolved by both
    service.join_queue(env.db, env.a, env.t)
    service.join_queue(env.db, env.b, env.t)
    assert service.matchmake(env.db, env.t) == []
    assert len(waiting) == 2
    env.problem(1500)  # now 3 are unsolved by both
    assert len(service.matchmake(env.db, env.t)) == 1


def test_rating_window_widens_over_time(env):
    env.problems_n(6)
    env.set_duel_rating(env.a, 1200)
    env.set_duel_rating(env.b, 1500)
    service.join_queue(env.db, env.a, T0)
    service.join_queue(env.db, env.b, T0)
    assert service.matchmake(env.db, T0) == []
    assert service.matchmake(env.db, T0 + timedelta(seconds=59)) == []  # window 250 < 300
    assert len(service.matchmake(env.db, T0 + timedelta(seconds=60))) == 1  # window 300


def test_cannot_join_twice_or_while_in_a_duel_and_leave(env):
    env.problems_n(6)
    service.join_queue(env.db, env.a, env.t)
    with pytest.raises(service.AlreadyWaiting):
        service.join_queue(env.db, env.a, env.t)
    service.leave_queue(env.a)
    with pytest.raises(service.NotWaiting):
        service.leave_queue(env.a)
    mid = env.match()
    assert mid
    with pytest.raises(service.AlreadyInDuel):
        service.join_queue(env.db, env.a, env.t)
    # a third player is matched against a fourth, not into the running duel
    assert service.active_match_id(env.db, env.c) is None


def test_players_are_not_matched_with_themselves_or_across_three(env):
    env.problems_n(6)
    for u in (env.a, env.b, env.c):
        service.join_queue(env.db, u, env.t)
    assert len(service.matchmake(env.db, env.t)) == 1  # 3 players -> one match, one waits
    assert len(waiting) == 1


# ------------------------------------------ finishing --------------------------------


def test_first_to_solve_all_wins_and_elo_is_k32(env):
    env.problems_n(6)
    mid = env.match()
    p1, p2, p3 = env.problems_of(mid)
    env.checked(mid, env.b, p1, solved=True, minutes=5)
    env.checked(mid, env.a, p1, solved=True, minutes=6)
    env.checked(mid, env.a, p2, solved=True, minutes=9)
    assert env.row(mid).status == "active"
    env.checked(mid, env.a, p3, solved=True, minutes=12)
    m = env.row(mid)
    assert (m.status, m.winner_id, m.reason) == ("finished", env.a, "all_solved")
    ra, rb = env.rating(env.a), env.rating(env.b)
    assert (ra.rating, rb.rating) == (1216.0, 1184.0)
    assert (ra.games, ra.wins, ra.losses) == (1, 1, 0) and (rb.games, rb.wins, rb.losses) == (1, 0, 1)
    parts = {p.user_id: p for p in env.db.query(DuelParticipant).filter_by(match_id=mid)}
    assert (parts[env.a].rating_before, parts[env.a].rating_after) == (1200.0, 1216.0)
    assert parts[env.b].rating_after == 1184.0


def test_duel_rating_is_separate_from_training_rating(env):
    from app.modules.rating.models import PlayerRating

    env.problems_n(6)
    mid = env.match()
    for pid, m in zip(env.problems_of(mid), (1, 2, 3)):
        env.checked(mid, env.a, pid, solved=True, minutes=m)
    assert env.db.get(PlayerRating, env.a) is None  # training rating untouched


def test_timeout_more_solved_wins(env):
    env.problems_n(6)
    mid = env.match()
    p1, p2, _ = env.problems_of(mid)
    env.checked(mid, env.a, p1, solved=True, minutes=40)
    env.checked(mid, env.a, p2, solved=True, minutes=50)
    env.checked(mid, env.b, p1, solved=True, minutes=2)
    assert service.tick(env.db, DEADLINE - timedelta(seconds=1)).finished == []
    assert service.tick(env.db, DEADLINE).finished == [mid]
    m = env.row(mid)
    assert (m.winner_id, m.reason) == (env.a, "timeout")


def test_timeout_total_score_then_penalty_tiebreaks(env):
    env.problems_n(6)
    mid = env.match()
    p1, p2, _ = env.problems_of(mid)
    # equal solved (1 each); B has more partial credit although a worse time
    env.checked(mid, env.a, p1, solved=True, minutes=5)
    env.checked(mid, env.b, p1, solved=True, minutes=30)
    env.checked(mid, env.a, p2, solved=False, minutes=6, score=0.2)
    env.checked(mid, env.b, p2, solved=False, minutes=31, score=0.7)
    service.tick(env.db, DEADLINE)
    assert env.row(mid).winner_id == env.b

    # second match: equal solved and equal score -> lower penalty wins (failures cost 5 min)
    env.problems_n(6)
    mid2 = env.match()
    q1, _, _ = env.problems_of(mid2)
    for m in (1, 2, 3):
        env.checked(mid2, env.a, q1, solved=False, minutes=m)  # 3 failed submissions = +15
    env.checked(mid2, env.a, q1, solved=True, minutes=4)  # penalty 4 + 15 = 19
    env.checked(mid2, env.b, q1, solved=True, minutes=18)  # penalty 18
    service.tick(env.db, env.t + timedelta(hours=2))
    assert env.row(mid2).winner_id == env.b


def test_full_tie_is_a_draw_with_half_a_point(env):
    env.problems_n(6)
    env.set_duel_rating(env.a, 1300)
    env.set_duel_rating(env.b, 1200)
    mid = env.match()
    p1 = env.problems_of(mid)[0]
    env.checked(mid, env.a, p1, solved=True, minutes=10)
    env.checked(mid, env.b, p1, solved=True, minutes=10)
    service.tick(env.db, DEADLINE)
    m = env.row(mid)
    assert m.status == "finished" and m.winner_id is None and m.reason == "timeout"
    ra, rb = env.rating(env.a), env.rating(env.b)
    assert ra.rating < 1300 and rb.rating > 1200  # the favourite loses a little, the underdog gains
    assert ra.rating + rb.rating == pytest.approx(2500)
    assert (ra.draws, rb.draws, ra.wins, rb.wins) == (1, 1, 0, 0)


def test_submission_after_the_deadline_does_not_count(env):
    env.problems_n(6)
    mid = env.match()
    p1 = env.problems_of(mid)[0]
    env.checked(mid, env.a, p1, solved=True, minutes=61)
    service.tick(env.db, DEADLINE + timedelta(seconds=1))
    assert env.row(mid).winner_id is None  # nobody solved anything in time


def test_deadline_waits_for_submissions_still_being_checked(env):
    env.problems_n(6)
    mid = env.match()
    p1 = env.problems_of(mid)[0]
    queued = Submission(user_id=env.a, problem_id=p1, language="python", code="x", state=STATE_QUEUED,
                        duel_match_id=mid)
    env.db.add(queued)
    env.db.commit()
    assert service.tick(env.db, DEADLINE + timedelta(seconds=10)).finished == []  # held
    # the check finishes: it was submitted in time, so it counts
    env.t = DEADLINE + timedelta(seconds=11)
    queued.state = STATE_DONE
    env.db.commit()
    env.checked(mid, env.a, p1, solved=True, minutes=59.9)
    service.tick(env.db, DEADLINE + timedelta(seconds=12))
    assert env.row(mid).winner_id == env.a

    # a check that never finishes cannot block the result forever
    env.problems_n(6)
    mid2 = env.match()
    env.db.add(Submission(user_id=env.a, problem_id=env.problems_of(mid2)[0], language="python", code="x",
                          state=STATE_QUEUED, duel_match_id=mid2))
    env.db.commit()
    start = env.t
    end = start + timedelta(seconds=st.MATCH_SECONDS)
    assert service.tick(env.db, end + timedelta(seconds=service.HOLD_TIMEOUT_MAX_SECONDS - 1)).finished == []
    assert service.tick(env.db, end + timedelta(seconds=service.HOLD_TIMEOUT_MAX_SECONDS)).finished == [mid2]


def test_finishing_is_idempotent(env):
    env.problems_n(6)
    mid = env.match()
    for pid, m in zip(env.problems_of(mid), (1, 2, 3)):
        env.checked(mid, env.a, pid, solved=True, minutes=m)
    before = (env.rating(env.a).rating, env.rating(env.b).rating)
    service.tick(env.db, DEADLINE)
    service.tick(env.db, DEADLINE + timedelta(hours=1))
    env.checked(mid, env.b, env.problems_of(mid)[0], solved=True, minutes=20)  # late result of the loser
    assert (env.rating(env.a).rating, env.rating(env.b).rating) == before
    assert env.rating(env.a).games == 1


# --------------------------------------- reconnect ------------------------------------


def test_reconnect_within_60_seconds_keeps_the_match(env):
    env.problems_n(6)
    mid = env.match()
    service.on_disconnected(env.db, env.a, at(10))
    assert service.tick(env.db, at(10, 59)).finished == []
    service.on_connected(env.db, env.a, at(10, 59))
    _, state = env.load(mid)
    assert state.players[env.a].disconnected_at is None
    assert service.tick(env.db, at(30)).finished == []  # the old drop no longer counts


def test_staying_away_60_seconds_is_an_automatic_loss(env):
    env.problems_n(6)
    mid = env.match()
    p1 = env.problems_of(mid)[0]
    env.checked(mid, env.a, p1, solved=True, minutes=3)  # A is ahead, but leaves
    service.on_disconnected(env.db, env.a, at(10))
    assert service.tick(env.db, at(10, 59)).finished == []
    assert service.tick(env.db, at(11)).finished == [mid]
    m = env.row(mid)
    assert (m.winner_id, m.reason) == (env.b, "forfeit")
    assert (env.rating(env.b).rating, env.rating(env.a).rating) == (1216.0, 1184.0)


def test_a_reconnect_that_comes_too_late_does_not_save_the_match(env):
    env.problems_n(6)
    mid = env.match()
    service.on_disconnected(env.db, env.a, at(10))
    service.on_connected(env.db, env.a, at(10, 61))  # the supervisor tick has not run yet
    assert env.row(mid).winner_id == env.b


def test_player_who_never_connects_loses_after_the_grace(env):
    env.problems_n(6)
    presence.connect(env.a)  # only A has a socket
    service.join_queue(env.db, env.a, env.t)
    service.join_queue(env.db, env.b, env.t)
    mid = service.matchmake(env.db, env.t)[0]
    assert service.tick(env.db, at(0, 59)).finished == []
    assert service.tick(env.db, at(0, 60)).finished == [mid]
    assert env.row(mid).winner_id == env.a


def test_tick_notices_a_player_whose_disconnect_was_never_recorded(env):
    env.problems_n(6)
    mid = env.match()
    presence.disconnect(env.a)  # the socket is gone, but on_disconnected never ran
    assert service.tick(env.db, at(5)).finished == []  # the countdown starts at this tick
    _, state = env.load(mid)
    assert state.players[env.a].disconnected_at == at(5) and state.players[env.b].disconnected_at is None
    assert service.tick(env.db, at(5, 59)).finished == []
    assert service.tick(env.db, at(6)).finished == [mid]
    assert env.row(mid).winner_id == env.b


def test_nobody_connects_is_decided_by_the_tiebreak(env):
    env.problems_n(6)
    mid = env.match(connect=False)
    service.tick(env.db, at(0, 60))
    m = env.row(mid)
    assert m.status == "finished" and m.winner_id is None and m.reason == "forfeit"


def test_all_solved_wins_even_if_the_opponent_is_gone(env):
    env.problems_n(6)
    mid = env.match()
    service.on_disconnected(env.db, env.b, at(1))
    for pid, m in zip(env.problems_of(mid), (1.2, 1.3, 1.4)):  # all inside B's 60 s grace
        env.checked(mid, env.a, pid, solved=True, minutes=m)
    assert (env.row(mid).winner_id, env.row(mid).reason) == (env.a, "all_solved")


def test_restart_gives_everyone_a_fresh_grace_period(env):
    env.problems_n(6)
    mid = env.match()
    presence.clear()  # the process restarted: no sockets any more
    service.recover(env.db, at(20))
    _, state = env.load(mid)
    assert all(p.disconnected_at == at(20) for p in state.players.values())
    presence.connect(env.a)  # A's browser reconnects
    service.on_connected(env.db, env.a, at(20, 30))
    assert service.tick(env.db, at(21)).finished == [mid]  # B never came back
    assert env.row(mid).winner_id == env.a


# ------------------------------------------ views -------------------------------------


def test_opponent_is_only_a_solved_count(env):
    env.problems_n(6)
    mid = env.match()
    p1, p2, _ = env.problems_of(mid)
    env.checked(mid, env.a, p1, solved=True, minutes=5)
    env.checked(mid, env.a, p2, solved=False, minutes=6, score=0.37)
    for_b = service.state_for_user(env.db, env.b, at(7))
    for_a = service.state_for_user(env.db, env.a, at(7))
    assert for_b["status"] == "active"
    assert for_b["match"]["opponent"] == {"solved": 1, "total": 3, "connected": True}
    assert for_b["match"]["me"] == {"solved": 0, "total": 3}
    assert "0.37" not in json.dumps(for_b)  # A's partial score never reaches B
    assert for_a["match"]["problems"][1]["best_score"] == 0.37  # but A sees their own
    assert for_b["match"]["remaining_seconds"] == 3600 - 7 * 60
    text = json.dumps(for_b).lower()
    assert "code" not in text and "language" not in text and "submission" not in text


def test_state_for_idle_and_waiting_players(env):
    assert service.state_for_user(env.db, env.c, T0) == {"status": "idle", "last_match_id": None}
    service.join_queue(env.db, env.c, T0)
    s = service.state_for_user(env.db, env.c, T0 + timedelta(seconds=7))
    assert s["status"] == "waiting" and s["waiting"]["seconds"] == 7


def test_last_match_id_points_to_the_finished_match(env):
    env.problems_n(6)
    mid = env.match()
    service.tick(env.db, DEADLINE)
    s = service.state_for_user(env.db, env.a, DEADLINE)
    assert s["status"] == "idle" and s["last_match_id"] == mid


def test_result_view_has_solved_score_and_penalty_per_player_and_problem(env):
    env.problems_n(6)
    mid = env.match()
    p1, p2, p3 = env.problems_of(mid)
    env.checked(mid, env.a, p1, solved=False, minutes=3)
    env.checked(mid, env.a, p1, solved=False, minutes=4)
    env.checked(mid, env.a, p1, solved=True, minutes=10)  # 10 + 2 * 5 on this problem
    env.checked(mid, env.a, p2, solved=False, minutes=12, score=0.4)
    env.checked(mid, env.b, p3, solved=True, minutes=20)
    service.tick(env.db, DEADLINE)

    viewer = env.db.get(User, env.a)
    with pytest.raises(service.MatchNotFound):
        service.result_view(env.db, 999, viewer, "kk")
    r = service.result_view(env.db, mid, viewer, "kk")
    assert r["winner_id"] == env.a and r["draw"] is False and r["reason"] == "timeout"
    assert [p["problem_id"] for p in r["problems"]] == [p1, p2, p3]
    assert r["problems"][0]["title"].startswith("P")
    pa = next(p for p in r["players"] if p["user_id"] == env.a)
    pb = next(p for p in r["players"] if p["user_id"] == env.b)
    assert (pa["solved"], pa["total_score"], pa["failed_submissions"]) == (1, 1.4, 3)
    assert pa["penalty_minutes"] == 10 + 5 * 3
    assert pa["problems"][0] == {"problem_id": p1, "solved": True, "best_score": 1.0, "failed_submissions": 2,
                                 "solved_minutes": 10.0, "penalty_minutes": 20.0}
    assert pa["problems"][1]["solved"] is False and pa["problems"][1]["best_score"] == 0.4
    assert pa["problems"][1]["penalty_minutes"] == 5.0
    assert (pb["solved"], pb["total_score"], pb["penalty_minutes"]) == (1, 1.0, 20.0)
    assert pa["rating_after"] is not None and pa["rating_change"] == pytest.approx(pa["rating_after"] - 1200)


def test_result_view_access_rules(env):
    env.problems_n(6)
    mid = env.match()
    a, c, admin = (env.db.get(User, u) for u in (env.a, env.c, env.admin))
    with pytest.raises(service.MatchNotActive):  # still running
        service.result_view(env.db, mid, a, "kk")
    service.tick(env.db, DEADLINE)
    with pytest.raises(service.MatchNotFound):  # a stranger learns nothing
        service.result_view(env.db, mid, c, "kk")
    assert service.result_view(env.db, mid, admin, "kk")["match_id"] == mid


def test_history_and_rating_view(env):
    env.problems_n(6)
    mid = env.match()
    for pid, m in zip(env.problems_of(mid), (1, 2, 3)):
        env.checked(mid, env.a, pid, solved=True, minutes=m)
    h = service.history(env.db, env.a)
    assert h == [{"match_id": mid, "finished_at": h[0]["finished_at"], "result": "win",
                  "reason": "all_solved", "rating_change": 16.0}]
    assert service.history(env.db, env.b)[0]["result"] == "loss"
    assert service.rating_view(env.db, env.a) == {"rating": 1216.0, "games": 1, "wins": 1, "losses": 0, "draws": 0}
    assert service.rating_view(env.db, env.c)["games"] == 0


# ---------------------------------------- submit --------------------------------------


def test_submit_rules(env):
    env.problems_n(6)
    mid = env.match()
    p1, p2, _ = env.problems_of(mid)
    a, c = env.db.get(User, env.a), env.db.get(User, env.c)
    sub = service.submit(env.db, a, mid, p1, "python", "print(1)", env.t)
    assert sub.duel_match_id == mid and sub.state == STATE_QUEUED
    with pytest.raises(service.MatchNotFound):
        service.submit(env.db, c, mid, p1, "python", "x", env.t)  # not a participant
    with pytest.raises(service.MatchNotFound):
        service.submit(env.db, a, 999, p1, "python", "x", env.t)
    outside = [p for p in env.problems if p not in env.problems_of(mid)][0]
    with pytest.raises(service.BadProblem):
        service.submit(env.db, a, mid, outside, "python", "x", env.t)
    with pytest.raises(service.MatchNotActive):
        service.submit(env.db, a, mid, p2, "python", "x", DEADLINE)  # the clock decides, not the client
    sub.state = STATE_DONE  # its check is over (otherwise the deadline would wait for it)
    env.db.commit()
    env.checked(mid, env.a, p1, solved=True, minutes=5)
    with pytest.raises(service.ProblemAlreadySolved):
        service.submit(env.db, a, mid, p1, "python", "x", at(6))
    service.tick(env.db, DEADLINE)
    with pytest.raises(service.MatchNotActive):
        service.submit(env.db, a, mid, p2, "python", "x", at(1))  # finished matches accept nothing


def test_non_duel_submissions_are_ignored_by_the_duel_module(env):
    env.problems_n(6)
    mid = env.match()
    p1 = env.problems_of(mid)[0]
    service.on_checked(env.db, CheckedSubmission(env.a, p1, 1, None, at(1), 1.0, True, 1))
    _, state = env.load(mid)
    assert st.solved_count(state.players[env.a]) == 0
