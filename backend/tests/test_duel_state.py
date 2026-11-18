from datetime import datetime, timedelta, timezone

import pytest

from app.modules.duel import elo, state as st
from app.modules.duel.waiting import WaitingList, Waiting, window

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
PROBLEMS = (10, 20, 30)
A, B = 1, 2


def minutes(m: float) -> datetime:
    return T0 + timedelta(minutes=m)


def new_state() -> st.MatchState:
    return st.MatchState(
        problems=PROBLEMS,
        started_at=T0,
        ends_at=T0 + timedelta(seconds=st.MATCH_SECONDS),
        players={A: st.PlayerState(A), B: st.PlayerState(B)},
    )


def solve(s, user, problem, at_min):
    assert st.apply_submission(s, user, problem, 1.0, True, minutes(at_min))


def fail(s, user, problem, at_min, score=0.0):
    assert st.apply_submission(s, user, problem, score, False, minutes(at_min))


END = T0 + timedelta(seconds=st.MATCH_SECONDS)


# ------------------------------- recording submissions -------------------------------


def test_solved_records_minutes_and_score():
    s = new_state()
    solve(s, A, 10, 12.5)
    assert s.players[A].solved_at == {10: 12.5} and s.players[A].best_score[10] == 1.0
    assert st.solved_count(s.players[A]) == 1 and st.solved_count(s.players[B]) == 0


def test_failed_submissions_keep_best_score_and_count():
    s = new_state()
    fail(s, A, 10, 1, score=0.4)
    fail(s, A, 10, 2, score=0.2)
    assert s.players[A].best_score[10] == 0.4  # best, not last
    assert s.players[A].failed[10] == 2 and st.solved_count(s.players[A]) == 0


def test_submissions_after_solving_are_ignored():
    s = new_state()
    solve(s, A, 10, 5)
    assert st.apply_submission(s, A, 10, 0.0, False, minutes(6)) is False
    assert st.apply_submission(s, A, 10, 1.0, True, minutes(7)) is False
    assert s.players[A].solved_at[10] == 5 and s.players[A].failed.get(10, 0) == 0


def test_irrelevant_submissions_are_ignored():
    s = new_state()
    assert st.apply_submission(s, A, 999, 1.0, True, minutes(1)) is False  # not a match problem
    assert st.apply_submission(s, 77, 10, 1.0, True, minutes(1)) is False  # not a player
    assert st.apply_submission(s, A, 10, 1.0, True, END + timedelta(seconds=1)) is False  # too late
    assert st.apply_submission(s, A, 10, 1.0, True, END) is True  # exactly at the deadline counts
    s.status = st.FINISHED
    assert st.apply_submission(s, B, 10, 1.0, True, minutes(1)) is False


def test_penalty_is_last_solve_plus_five_per_failure():
    s = new_state()
    fail(s, A, 10, 3)
    fail(s, A, 10, 4)
    solve(s, A, 10, 10)
    fail(s, A, 20, 11)  # failures on a problem that stays unsolved count too
    solve(s, A, 30, 25)
    p = s.players[A]
    assert st.last_solve_minutes(p) == 25 and st.failed_count(p) == 3
    assert st.penalty(p) == 25 + 5 * 3
    assert st.problem_penalty(p, 10) == 10 + 5 * 2
    assert st.problem_penalty(p, 20) == 5  # unsolved: only the failures
    assert st.penalty(st.PlayerState(9)) == 0


# ---------------------------------- first to solve all -------------------------------


def test_first_to_solve_all_wins_immediately():
    s = new_state()
    solve(s, B, 10, 5)
    solve(s, A, 10, 6)
    solve(s, A, 20, 7)
    assert st.check_finish(s, minutes(8)) is None
    solve(s, A, 30, 9)
    assert st.check_finish(s, minutes(9)) == st.Outcome(A, st.REASON_ALL_SOLVED)


def test_all_solved_beats_timeout_and_disconnect():
    s = new_state()
    for p, m in zip(PROBLEMS, (1, 2, 3)):
        solve(s, A, p, m)
    st.mark_disconnected(s, A, minutes(0))  # even if the winner's grace ran out
    assert st.check_finish(s, END + timedelta(hours=1)).winner_id == A


def test_both_solved_all_earlier_last_solve_wins():
    s = new_state()
    for p, m in zip(PROBLEMS, (1, 2, 30)):
        solve(s, A, p, m)
    for p, m in zip(PROBLEMS, (1, 2, 20)):
        solve(s, B, p, m)
    assert st.check_finish(s, minutes(31)) == st.Outcome(B, st.REASON_ALL_SOLVED)


# ---------------------------------------- timeout ------------------------------------


def test_nothing_happens_before_the_deadline():
    s = new_state()
    solve(s, A, 10, 1)
    assert st.check_finish(s, END - timedelta(seconds=1)) is None
    assert st.check_finish(s, END) is not None


def test_timeout_more_solved_wins():
    s = new_state()
    solve(s, A, 10, 50)
    solve(s, A, 20, 55)
    solve(s, B, 10, 1)  # B is faster and has a higher penalty advantage, but fewer solved
    out = st.check_finish(s, END)
    assert out == st.Outcome(A, st.REASON_TIMEOUT)


def test_timeout_equal_solved_higher_total_score_wins():
    s = new_state()
    solve(s, A, 10, 10)
    solve(s, B, 10, 30)  # worse penalty ...
    fail(s, A, 20, 12, score=0.3)
    fail(s, B, 20, 13, score=0.6)  # ... but more partial credit
    assert st.total_score(s, s.players[A]) == pytest.approx(1.3)
    assert st.total_score(s, s.players[B]) == pytest.approx(1.6)
    assert st.check_finish(s, END).winner_id == B


def test_timeout_equal_solved_and_score_lower_penalty_wins():
    s = new_state()
    solve(s, A, 10, 30)
    solve(s, B, 10, 20)
    assert st.penalty(s.players[B]) < st.penalty(s.players[A])
    assert st.check_finish(s, END).winner_id == B
    # failed submissions count 5 minutes each: A is faster but made 3 failed attempts
    s = new_state()
    solve(s, A, 10, 10)
    solve(s, B, 10, 20)
    for m in (1, 2, 3):
        fail(s, A, 20, m)
    assert st.penalty(s.players[A]) == 10 + 15 and st.penalty(s.players[B]) == 20
    assert st.check_finish(s, END).winner_id == B


def test_timeout_complete_tie_is_a_draw():
    s = new_state()
    solve(s, A, 10, 15)
    solve(s, B, 10, 15)
    assert st.check_finish(s, END) == st.Outcome(None, st.REASON_TIMEOUT)
    assert st.check_finish(new_state(), END) == st.Outcome(None, st.REASON_TIMEOUT)  # nobody solved


def test_hold_timeout_waits_for_pending_checks():
    s = new_state()
    solve(s, A, 10, 1)
    assert st.check_finish(s, END + timedelta(seconds=5), hold_timeout=True) is None
    assert st.check_finish(s, END + timedelta(seconds=5), hold_timeout=False).winner_id == A


def test_finished_match_never_finishes_again():
    s = new_state()
    s.status = st.FINISHED
    assert st.check_finish(s, END + timedelta(days=1)) is None


# ---------------------------------------- reconnect ----------------------------------


def test_disconnect_within_grace_is_fine():
    s = new_state()
    st.mark_disconnected(s, A, minutes(10))
    assert st.check_finish(s, minutes(10) + timedelta(seconds=59)) is None


def test_disconnect_for_60_seconds_is_a_loss():
    s = new_state()
    solve(s, A, 10, 1)  # even the player who is ahead loses by forfeit
    st.mark_disconnected(s, A, minutes(10))
    out = st.check_finish(s, minutes(10) + timedelta(seconds=60))
    assert out == st.Outcome(B, st.REASON_FORFEIT)


def test_reconnecting_resets_the_grace_period():
    s = new_state()
    st.mark_disconnected(s, A, minutes(10))
    st.mark_connected(s, A)
    assert s.players[A].disconnected_at is None
    assert st.check_finish(s, minutes(30)) is None
    st.mark_disconnected(s, A, minutes(30))  # a NEW drop gets a new 60 s
    assert st.check_finish(s, minutes(30) + timedelta(seconds=59)) is None


def test_mark_disconnected_keeps_the_first_timestamp():
    s = new_state()
    st.mark_disconnected(s, A, minutes(10))
    st.mark_disconnected(s, A, minutes(11))
    assert s.players[A].disconnected_at == minutes(10)


def test_both_gone_the_earlier_disconnect_loses():
    s = new_state()
    st.mark_disconnected(s, A, minutes(10))
    st.mark_disconnected(s, B, minutes(10) + timedelta(seconds=5))
    assert st.check_finish(s, minutes(20)).winner_id == B  # A left first


def test_both_gone_at_the_same_instant_uses_the_tiebreak():
    s = new_state()
    solve(s, B, 10, 5)
    st.mark_disconnected(s, A, minutes(10))
    st.mark_disconnected(s, B, minutes(10))
    assert st.check_finish(s, minutes(20)) == st.Outcome(B, st.REASON_FORFEIT)


def test_only_one_expired_when_the_other_just_dropped():
    s = new_state()
    st.mark_disconnected(s, A, minutes(10))
    st.mark_disconnected(s, B, minutes(10) + timedelta(seconds=50))
    out = st.check_finish(s, minutes(10) + timedelta(seconds=61))
    assert out == st.Outcome(B, st.REASON_FORFEIT)  # A expired, B is still inside its grace


# ------------------------------------- matchmaking -----------------------------------


def accept(a, b):
    return "ok"


def test_window_widens_by_50_every_15_seconds():
    e = Waiting(1, 1200, joined_at=1000.0)
    assert [window(e, 1000 + s) for s in (0, 14.9, 15, 29.9, 30, 60)] == [100, 100, 150, 150, 200, 300]


def test_within_100_matches_immediately_outside_does_not():
    wl = WaitingList()
    wl.join(1, 1200, 0.0)
    wl.join(2, 1300, 0.0)
    assert len(wl.find_matches(0.0, accept)) == 1
    wl = WaitingList()
    wl.join(1, 1200, 0.0)
    wl.join(2, 1301, 0.0)
    assert wl.find_matches(0.0, accept) == [] and len(wl) == 2  # both keep waiting


def test_gap_closes_at_15_seconds():
    wl = WaitingList()
    wl.join(1, 1200, 0.0)
    wl.join(2, 1340, 0.0)
    assert wl.find_matches(14.9, accept) == []
    pairs = wl.find_matches(15.0, accept)
    assert [(a.user_id, b.user_id) for a, b, _ in pairs] == [(1, 2)] and len(wl) == 0


def test_the_narrower_window_decides():
    wl = WaitingList()
    wl.join(1, 1200, 0.0)  # waited 60 s -> window 300
    wl.join(2, 1450, 60.0)  # just joined -> window 100
    assert wl.find_matches(60.0, accept) == []
    assert len(wl.find_matches(60.0 + 45, accept)) == 1  # 2 has waited 45 s -> window 250 >= 250


def test_closest_opponent_is_chosen_and_each_player_matches_once():
    wl = WaitingList()
    wl.join(1, 1200, 0.0)
    wl.join(2, 1290, 1.0)
    wl.join(3, 1210, 2.0)
    pairs = wl.find_matches(2.0, accept)
    assert [(a.user_id, b.user_id) for a, b, _ in pairs] == [(1, 3)]
    assert [e.user_id for e in [wl.get(2)] if e] == [2]  # 2 is still waiting


def test_try_pair_can_veto_and_the_next_candidate_is_tried():
    wl = WaitingList()
    wl.join(1, 1200, 0.0)
    wl.join(2, 1210, 0.0)
    wl.join(3, 1250, 0.0)
    pairs = wl.find_matches(0.0, lambda a, b: None if {a.user_id, b.user_id} == {1, 2} else "ok")
    assert [(a.user_id, b.user_id) for a, b, _ in pairs] == [(1, 3)]


def test_join_leave():
    wl = WaitingList()
    assert wl.join(1, 1200, 0.0) is True and wl.join(1, 1200, 5.0) is False
    assert wl.get(1).joined_at == 0.0  # the second join did not reset the wait
    assert wl.leave(1) is True and wl.leave(1) is False and len(wl) == 0


# ------------------------------------------ elo --------------------------------------


def test_duel_elo_k32():
    assert elo.update(1200, 1200, 1.0) == (1216.0, 1184.0)
    assert elo.update(1200, 1200, 0.0) == (1184.0, 1216.0)
    assert elo.update(1200, 1200, 0.5) == (1200.0, 1200.0)


def test_duel_elo_upset_and_expected_win():
    ra, rb = elo.update(1000, 1400, 1.0)  # underdog wins: big swing
    assert ra - 1000 > 28 and 1400 - rb > 28
    ra, rb = elo.update(1400, 1000, 1.0)  # favourite wins: small swing
    assert 0 < ra - 1400 < 4
    ra, rb = elo.update(1000, 1400, 0.5)  # draw helps the underdog
    assert ra > 1000 and rb < 1400


def test_duel_elo_zero_sum_and_floor():
    ra, rb = elo.update(1337, 1111, 0.0)
    assert ra + rb == pytest.approx(1337 + 1111)
    assert elo.update(805, 805, 0.0)[0] == 800  # -16 would go below the floor
    assert elo.update(800, 1200, 0.0)[0] == 800
    assert elo.update(805, 1200, 0.0)[0] == pytest.approx(802.0, abs=0.1)  # a small loss stays above it
