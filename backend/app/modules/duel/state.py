"""Duel rules as a pure state machine (no I/O, the clock is always passed in).

Time is judged by the SERVER only: `now` comes from the server clock, submission times from
the moment the server accepted the submission.

Per player we track, per match problem: best score, solve time (minutes from the start of the
first solved=true result) and the number of failed submissions made before that.

    solved count   = problems with a solved=true result
    total score    = sum of the best score on each problem
    penalty        = minutes to the LAST solve + 5 * failed submissions
                     (submissions to an already solved problem are ignored)

Finishing, checked in this order:
    1. a player solved every problem  -> wins (both: the earlier last solve wins)
    2. a player was disconnected for >= 60 s -> loses (both: the earlier disconnect loses)
    3. the deadline passed -> more solved, then higher total score, then lower penalty,
       otherwise a draw. `hold_timeout` postpones this while submissions are still being checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

MATCH_SECONDS = 60 * 60
GRACE_SECONDS = 60
FAIL_PENALTY_MINUTES = 5
SCORE_PRECISION = 6  # scores/minutes are rounded before comparing, to ignore float noise

ACTIVE = "active"
FINISHED = "finished"

REASON_ALL_SOLVED = "all_solved"
REASON_TIMEOUT = "timeout"
REASON_FORFEIT = "forfeit"


@dataclass
class PlayerState:
    user_id: int
    solved_at: dict[int, float] = field(default_factory=dict)  # problem_id -> minutes
    best_score: dict[int, float] = field(default_factory=dict)
    failed: dict[int, int] = field(default_factory=dict)
    disconnected_at: datetime | None = None


@dataclass
class MatchState:
    problems: tuple[int, ...]
    started_at: datetime
    ends_at: datetime
    players: dict[int, PlayerState]
    status: str = ACTIVE


@dataclass(frozen=True)
class Outcome:
    winner_id: int | None  # None = draw
    reason: str


# ---- derived numbers ---------------------------------------------------------------


def solved_count(p: PlayerState) -> int:
    return len(p.solved_at)


def total_score(state: MatchState, p: PlayerState) -> float:
    return sum(p.best_score.get(pid, 0.0) for pid in state.problems)


def last_solve_minutes(p: PlayerState) -> float:
    return max(p.solved_at.values(), default=0.0)


def failed_count(p: PlayerState) -> int:
    return sum(p.failed.values())


def penalty(p: PlayerState) -> float:
    return last_solve_minutes(p) + FAIL_PENALTY_MINUTES * failed_count(p)


def problem_penalty(p: PlayerState, problem_id: int) -> float:
    """Shown on the result page: solve time (if solved) + 5 per failed submission on that problem."""
    return p.solved_at.get(problem_id, 0.0) + FAIL_PENALTY_MINUTES * p.failed.get(problem_id, 0)


def minutes_between(start: datetime, t: datetime) -> float:
    return (t - start).total_seconds() / 60


# ---- events -------------------------------------------------------------------------


def apply_submission(
    state: MatchState, user_id: int, problem_id: int, score: float, solved: bool, submitted_at: datetime
) -> bool:
    """Record a checked submission. Returns False if it does not count."""
    p = state.players.get(user_id)
    if state.status != ACTIVE or p is None or problem_id not in state.problems:
        return False
    if submitted_at > state.ends_at or problem_id in p.solved_at:
        return False
    p.best_score[problem_id] = max(p.best_score.get(problem_id, 0.0), score)
    if solved:
        p.solved_at[problem_id] = max(0.0, minutes_between(state.started_at, submitted_at))
        p.best_score[problem_id] = max(p.best_score[problem_id], 1.0)
    else:
        p.failed[problem_id] = p.failed.get(problem_id, 0) + 1
    return True


def mark_disconnected(state: MatchState, user_id: int, now: datetime) -> None:
    p = state.players.get(user_id)
    if p is not None and p.disconnected_at is None:
        p.disconnected_at = now


def mark_connected(state: MatchState, user_id: int) -> None:
    p = state.players.get(user_id)
    if p is not None:
        p.disconnected_at = None


# ---- decisions ----------------------------------------------------------------------


def _rank_key(state: MatchState, p: PlayerState) -> tuple[int, float, float]:
    return (
        -solved_count(p),
        -round(total_score(state, p), SCORE_PRECISION),
        round(penalty(p), SCORE_PRECISION),
    )


def tiebreak(state: MatchState) -> int | None:
    """Winner by solved count, then total score, then penalty; None if completely equal."""
    a, b = state.players.values()
    ka, kb = _rank_key(state, a), _rank_key(state, b)
    if ka == kb:
        return None
    return a.user_id if ka < kb else b.user_id


def check_finish(state: MatchState, now: datetime, hold_timeout: bool = False) -> Outcome | None:
    if state.status != ACTIVE:
        return None
    players = list(state.players.values())
    total = len(state.problems)

    done = [p for p in players if solved_count(p) == total]
    if done:
        if len(done) == 1:
            return Outcome(done[0].user_id, REASON_ALL_SOLVED)
        a, b = sorted(done, key=last_solve_minutes)
        if round(last_solve_minutes(a), SCORE_PRECISION) < round(last_solve_minutes(b), SCORE_PRECISION):
            return Outcome(a.user_id, REASON_ALL_SOLVED)
        return Outcome(tiebreak(state), REASON_ALL_SOLVED)

    grace = timedelta(seconds=GRACE_SECONDS)
    gone = [p for p in players if p.disconnected_at is not None and now - p.disconnected_at >= grace]
    if len(gone) == 1:
        other = next(p for p in players if p is not gone[0])
        return Outcome(other.user_id, REASON_FORFEIT)
    if len(gone) == 2:
        first, second = sorted(gone, key=lambda p: p.disconnected_at)  # type: ignore[arg-type,return-value]
        if first.disconnected_at != second.disconnected_at:
            return Outcome(second.user_id, REASON_FORFEIT)  # the one who left first loses
        return Outcome(tiebreak(state), REASON_FORFEIT)

    if now >= state.ends_at and not hold_timeout:
        return Outcome(tiebreak(state), REASON_TIMEOUT)
    return None
