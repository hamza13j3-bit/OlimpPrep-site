"""Duel orchestration: matchmaking, persistence, timers, results.

All time decisions use the SERVER clock (`now()`); the client never sends a time. Anything
that changes a match runs under one process-wide lock, and a match is re-loaded from SQLite
inside the lock, so the 1-second supervisor tick, checker worker threads and WebSocket
handlers cannot finish a match twice.
"""

import logging
import math
import random
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth import service as auth_service
from app.modules.auth.models import User
from app.modules.checker import service as checker_service
from app.modules.duel import elo, presence
from app.modules.duel import state as st
from app.modules.duel.models import (
    DuelMatch,
    DuelMatchProblem,
    DuelParticipant,
    DuelPlayerProblem,
    DuelRating,
)
from app.modules.duel.waiting import Waiting, waiting
from app.modules.problems import service as problems_service

log = logging.getLogger(__name__)

PROBLEMS_PER_MATCH = 3
POOL_SIZE = 9  # pick the 3 problems at random among the 9 closest to the pair's rating
HOLD_TIMEOUT_MAX_SECONDS = 120  # wait at most this long for in-flight checks after the deadline

_lock = threading.RLock()


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything stored here is UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class DuelError(Exception):
    pass


class AlreadyInDuel(DuelError):
    pass


class AlreadyWaiting(DuelError):
    pass


class NotWaiting(DuelError):
    pass


class MatchNotFound(DuelError):
    pass


class MatchNotActive(DuelError):
    pass


class BadProblem(DuelError):
    pass


class ProblemAlreadySolved(DuelError):
    pass


# ---- ratings ---------------------------------------------------------------------


def get_duel_rating(db: Session, user_id: int) -> DuelRating:
    r = db.get(DuelRating, user_id)
    if r is None:
        r = DuelRating(user_id=user_id, rating=elo.START_RATING)
        db.add(r)
        db.flush()
    return r


def rating_view(db: Session, user_id: int) -> dict:
    r = db.get(DuelRating, user_id)
    if r is None:
        return {"rating": elo.START_RATING, "games": 0, "wins": 0, "losses": 0, "draws": 0}
    return {"rating": r.rating, "games": r.games, "wins": r.wins, "losses": r.losses, "draws": r.draws}


# ---- loading / saving ------------------------------------------------------------


def _load(db: Session, match_id: int) -> tuple[DuelMatch, st.MatchState] | None:
    db.expire_all()
    match = db.get(DuelMatch, match_id)
    if match is None:
        return None
    parts = db.scalars(
        select(DuelParticipant).where(DuelParticipant.match_id == match_id).order_by(DuelParticipant.user_id)
    ).all()
    problems = db.scalars(
        select(DuelMatchProblem).where(DuelMatchProblem.match_id == match_id).order_by(DuelMatchProblem.position)
    ).all()
    progress = db.scalars(select(DuelPlayerProblem).where(DuelPlayerProblem.match_id == match_id)).all()
    players = {}
    for p in parts:
        mine = [x for x in progress if x.user_id == p.user_id]
        players[p.user_id] = st.PlayerState(
            user_id=p.user_id,
            solved_at={x.problem_id: x.solved_minutes for x in mine if x.solved_minutes is not None},
            best_score={x.problem_id: x.best_score for x in mine},
            failed={x.problem_id: x.failed for x in mine},
            disconnected_at=_aware(p.disconnected_at),
        )
    state = st.MatchState(
        problems=tuple(x.problem_id for x in problems),
        started_at=_aware(match.started_at),  # type: ignore[arg-type]
        ends_at=_aware(match.ends_at),  # type: ignore[arg-type]
        players=players,
        status=match.status,
    )
    return match, state


def _save(db: Session, match: DuelMatch, state: st.MatchState) -> None:
    rows = {
        (x.user_id, x.problem_id): x
        for x in db.scalars(select(DuelPlayerProblem).where(DuelPlayerProblem.match_id == match.id))
    }
    for uid, p in state.players.items():
        for pid in state.problems:
            row = rows[(uid, pid)]
            row.best_score = p.best_score.get(pid, 0.0)
            row.failed = p.failed.get(pid, 0)
            row.solved_minutes = p.solved_at.get(pid)
    for part in db.scalars(select(DuelParticipant).where(DuelParticipant.match_id == match.id)):
        part.disconnected_at = state.players[part.user_id].disconnected_at


# ---- queue -------------------------------------------------------------------------


def active_match_id(db: Session, user_id: int) -> int | None:
    return db.scalar(
        select(DuelMatch.id)
        .join(DuelParticipant, DuelParticipant.match_id == DuelMatch.id)
        .where(DuelParticipant.user_id == user_id, DuelMatch.status == st.ACTIVE)
    )


def join_queue(db: Session, user_id: int, at: datetime) -> None:
    with _lock:
        if active_match_id(db, user_id) is not None:
            raise AlreadyInDuel
        rating = get_duel_rating(db, user_id).rating
        db.commit()
        if not waiting.join(user_id, rating, at.timestamp()):
            raise AlreadyWaiting


def leave_queue(user_id: int) -> None:
    if not waiting.leave(user_id):
        raise NotWaiting


# ---- matchmaking -------------------------------------------------------------------


def _pick_problems(db: Session, a: int, b: int, avg_rating: float, rng: random.Random) -> list[int] | None:
    solved = checker_service.solved_problem_ids(db, a) | checker_service.solved_problem_ids(db, b)
    available = [(pid, r) for pid, r in problems_service.problem_ratings(db) if pid not in solved]
    if len(available) < PROBLEMS_PER_MATCH:
        return None  # not enough unsolved problems: keep waiting
    available.sort(key=lambda x: (abs(x[1] - avg_rating), x[0]))
    chosen = rng.sample(available[:POOL_SIZE], PROBLEMS_PER_MATCH)
    chosen.sort(key=lambda x: (x[1], x[0]))  # easiest first
    return [pid for pid, _ in chosen]


def _create_match(db: Session, a: Waiting, b: Waiting, problem_ids: list[int], at: datetime) -> DuelMatch:
    match = DuelMatch(
        status=st.ACTIVE, started_at=at, ends_at=at + timedelta(seconds=st.MATCH_SECONDS)
    )
    db.add(match)
    db.flush()
    for pos, pid in enumerate(problem_ids):
        db.add(DuelMatchProblem(match_id=match.id, problem_id=pid, position=pos))
    for w in (a, b):
        rating = get_duel_rating(db, w.user_id).rating
        # a player without an open WebSocket gets the 60 s reconnect grace right away
        db.add(
            DuelParticipant(
                match_id=match.id, user_id=w.user_id, rating_before=rating,
                disconnected_at=None if presence.is_connected(w.user_id) else at,
            )
        )
        for pid in problem_ids:
            db.add(DuelPlayerProblem(match_id=match.id, user_id=w.user_id, problem_id=pid))
    db.commit()
    return match


def matchmake(db: Session, at: datetime, rng: random.Random | None = None) -> list[int]:
    """Create matches for compatible waiting players. Returns the new match ids."""
    rng = rng or random.Random()
    with _lock:
        pairs = waiting.find_matches(
            at.timestamp(),
            lambda x, y: _pick_problems(db, x.user_id, y.user_id, (x.rating + y.rating) / 2, rng),
        )
        return [_create_match(db, x, y, problems, at).id for x, y, problems in pairs]


# ---- finishing -------------------------------------------------------------------


def _finish(db: Session, match: DuelMatch, state: st.MatchState, outcome: st.Outcome, at: datetime) -> None:
    if match.status != st.ACTIVE:
        return
    state.status = st.FINISHED
    match.status = st.FINISHED
    match.winner_id = outcome.winner_id
    match.reason = outcome.reason
    match.finished_at = at

    a_id, b_id = list(state.players)
    ra, rb = get_duel_rating(db, a_id), get_duel_rating(db, b_id)
    score_a = 0.5 if outcome.winner_id is None else (1.0 if outcome.winner_id == a_id else 0.0)
    new_a, new_b = elo.update(ra.rating, rb.rating, score_a)
    parts = {
        p.user_id: p for p in db.scalars(select(DuelParticipant).where(DuelParticipant.match_id == match.id))
    }
    for uid, rating_row, new, score in ((a_id, ra, new_a, score_a), (b_id, rb, new_b, 1.0 - score_a)):
        parts[uid].rating_after = new
        rating_row.rating = new
        rating_row.games += 1
        if score == 1.0:
            rating_row.wins += 1
        elif score == 0.0:
            rating_row.losses += 1
        else:
            rating_row.draws += 1


def _try_finish(db: Session, match: DuelMatch, state: st.MatchState, at: datetime) -> bool:
    """Apply the finishing rules; must be called with the lock held. Does not commit."""
    hold = (
        at >= state.ends_at
        and at < state.ends_at + timedelta(seconds=HOLD_TIMEOUT_MAX_SECONDS)
        and checker_service.pending_duel_count(db, match.id) > 0
    )
    outcome = st.check_finish(state, at, hold_timeout=hold)
    if outcome is None:
        return False
    _finish(db, match, state, outcome, at)
    return True


@dataclass
class TickResult:
    created: list[int]
    finished: list[int]


def tick(db: Session, at: datetime, rng: random.Random | None = None) -> TickResult:
    """One supervisor step: matchmaking, then deadline / reconnect-grace checks."""
    created = matchmake(db, at, rng)
    finished: list[int] = []
    with _lock:
        ids = list(db.scalars(select(DuelMatch.id).where(DuelMatch.status == st.ACTIVE)))
        for match_id in ids:
            loaded = _load(db, match_id)
            if loaded is None:
                continue
            match, state = loaded
            # presence is the truth: a player with no open socket whose disconnect was not
            # recorded (e.g. the write was lost) starts the 60 s countdown now
            lost = [
                uid for uid, p in state.players.items()
                if p.disconnected_at is None and not presence.is_connected(uid)
            ]
            for uid in lost:
                st.mark_disconnected(state, uid, at)
            if lost:
                _save(db, match, state)
            if _try_finish(db, match, state, at):
                finished.append(match_id)
            db.commit()
    return TickResult(created, finished)


def recover(db: Session, at: datetime) -> None:
    """After a restart no sockets exist: every active player gets a fresh 60 s to reconnect."""
    with _lock:
        for match_id in list(db.scalars(select(DuelMatch.id).where(DuelMatch.status == st.ACTIVE))):
            loaded = _load(db, match_id)
            if loaded is None:
                continue
            match, state = loaded
            for uid in state.players:
                if not presence.is_connected(uid):
                    state.players[uid].disconnected_at = at
            _save(db, match, state)
            db.commit()


# ---- presence ----------------------------------------------------------------------


def on_connected(db: Session, user_id: int, at: datetime) -> None:
    with _lock:
        match_id = active_match_id(db, user_id)
        if match_id is None:
            return
        loaded = _load(db, match_id)
        if loaded is None:
            return
        match, state = loaded
        # a reconnect that arrives after the grace expired is too late
        if not _try_finish(db, match, state, at):
            st.mark_connected(state, user_id)
            _save(db, match, state)
        db.commit()


def on_disconnected(db: Session, user_id: int, at: datetime) -> None:
    with _lock:
        match_id = active_match_id(db, user_id)
        if match_id is None:
            return
        loaded = _load(db, match_id)
        if loaded is None:
            return
        match, state = loaded
        st.mark_disconnected(state, user_id, at)
        _save(db, match, state)
        db.commit()


# ---- submissions ----------------------------------------------------------------


def submit(db: Session, user: User, match_id: int, problem_id: int, language: str, code: str, at: datetime):
    """Create a checker submission tagged with the match. Returns the Submission."""
    with _lock:
        loaded = _load(db, match_id)
        if loaded is None or user.id not in loaded[1].players:
            raise MatchNotFound  # same answer for strangers: do not reveal other matches
        match, state = loaded
        if state.status != st.ACTIVE or at >= state.ends_at:
            raise MatchNotActive
        if problem_id not in state.problems:
            raise BadProblem
        if problem_id in state.players[user.id].solved_at:
            raise ProblemAlreadySolved
        return checker_service.create_submission(db, user, problem_id, language, code, duel_match_id=match.id)


def on_checked(db: Session, c: checker_service.CheckedSubmission) -> None:
    """Checker listener: record the result of a duel submission, maybe finish the match."""
    if c.duel_match_id is None:
        return
    with _lock:
        loaded = _load(db, c.duel_match_id)
        if loaded is None:
            return
        match, state = loaded
        if state.status != st.ACTIVE:
            return
        # the time that counts is when the player SUBMITTED, not when checking got to it
        if st.apply_submission(state, c.user_id, c.problem_id, c.score, c.solved, _aware(c.created_at)):  # type: ignore[arg-type]
            _save(db, match, state)
        _try_finish(db, match, state, now())
        db.commit()


def register() -> None:
    checker_service.add_listener(on_checked)


# ---- views ---------------------------------------------------------------------------


def _last_finished_id(db: Session, user_id: int) -> int | None:
    return db.scalar(
        select(func.max(DuelMatch.id))
        .join(DuelParticipant, DuelParticipant.match_id == DuelMatch.id)
        .where(DuelParticipant.user_id == user_id, DuelMatch.status == st.FINISHED)
    )


def state_for_user(db: Session, user_id: int, at: datetime) -> dict:
    """Live state for one player. The opponent is represented ONLY by a solved count (and
    whether they are connected): never their code, scores or submissions."""
    last = _last_finished_id(db, user_id)
    match_id = active_match_id(db, user_id)
    if match_id is not None:
        loaded = _load(db, match_id)
        if loaded is not None:
            match, state = loaded
            me = state.players[user_id]
            opp = next(p for uid, p in state.players.items() if uid != user_id)
            remaining = max(0, math.ceil((state.ends_at - at).total_seconds()))
            return {
                "status": "active",
                "last_match_id": last,
                "match": {
                    "id": match.id,
                    "remaining_seconds": remaining,
                    "ends_at": state.ends_at.isoformat(),
                    "problems": [
                        {
                            "problem_id": pid,
                            "number": pid,
                            "solved": pid in me.solved_at,
                            "best_score": round(me.best_score.get(pid, 0.0), 4),
                        }
                        for pid in state.problems
                    ],
                    "me": {"solved": st.solved_count(me), "total": len(state.problems)},
                    "opponent": {
                        "solved": st.solved_count(opp),
                        "total": len(state.problems),
                        "connected": opp.disconnected_at is None,
                    },
                },
            }
    w = waiting.get(user_id)
    if w is not None:
        return {
            "status": "waiting",
            "last_match_id": last,
            "waiting": {"seconds": int(max(0, at.timestamp() - w.joined_at))},
        }
    return {"status": "idle", "last_match_id": last}


def _player_result(db: Session, state: st.MatchState, part: DuelParticipant, user: User | None) -> dict:
    p = state.players[part.user_id]
    return {
        "user_id": part.user_id,
        "name": user.name if user else "?",
        "solved": st.solved_count(p),
        "total_score": round(st.total_score(state, p), 4),
        "penalty_minutes": round(st.penalty(p), 2),
        "failed_submissions": st.failed_count(p),
        "rating_before": round(part.rating_before, 2),
        "rating_after": round(part.rating_after, 2) if part.rating_after is not None else None,
        "rating_change": round(part.rating_after - part.rating_before, 2) if part.rating_after is not None else None,
        "problems": [
            {
                "problem_id": pid,
                "solved": pid in p.solved_at,
                "best_score": round(p.best_score.get(pid, 0.0), 4),
                "failed_submissions": p.failed.get(pid, 0),
                "solved_minutes": round(p.solved_at[pid], 2) if pid in p.solved_at else None,
                "penalty_minutes": round(st.problem_penalty(p, pid), 2),
            }
            for pid in state.problems
        ],
    }


def result_view(db: Session, match_id: int, viewer: User, lang: str) -> dict:
    """Post-match page. Only participants (and admins) may see it, only once finished."""
    loaded = _load(db, match_id)
    if loaded is None:
        raise MatchNotFound
    match, state = loaded
    if viewer.id not in state.players and viewer.role != "admin":
        raise MatchNotFound
    if state.status != st.FINISHED:
        raise MatchNotActive
    parts = db.scalars(
        select(DuelParticipant).where(DuelParticipant.match_id == match_id).order_by(DuelParticipant.user_id)
    ).all()
    titles = problems_service.titles_for(db, list(state.problems), lang)
    return {
        "match_id": match.id,
        "started_at": state.started_at.isoformat(),
        "finished_at": _aware(match.finished_at).isoformat() if match.finished_at else None,
        "winner_id": match.winner_id,
        "draw": match.winner_id is None,
        "reason": match.reason,
        "problems": [{"problem_id": pid, "number": pid, "title": titles.get(pid, "")} for pid in state.problems],
        "players": [_player_result(db, state, part, auth_service.get_user(db, part.user_id)) for part in parts],
    }


def live_view(db: Session, match_id: int, viewer: User, at: datetime) -> dict:
    loaded = _load(db, match_id)
    if loaded is None or viewer.id not in loaded[1].players:
        raise MatchNotFound
    return state_for_user(db, viewer.id, at) if loaded[1].status == st.ACTIVE else {"status": "finished", "match_id": match_id}


def history(db: Session, user_id: int, limit: int = 50) -> list[dict]:
    rows = db.execute(
        select(DuelMatch, DuelParticipant)
        .join(DuelParticipant, DuelParticipant.match_id == DuelMatch.id)
        .where(DuelParticipant.user_id == user_id, DuelMatch.status == st.FINISHED)
        .order_by(DuelMatch.id.desc())
        .limit(limit)
    ).all()
    out = []
    for m, part in rows:
        out.append(
            {
                "match_id": m.id,
                "finished_at": _aware(m.finished_at).isoformat() if m.finished_at else None,
                "result": "draw" if m.winner_id is None else ("win" if m.winner_id == user_id else "loss"),
                "reason": m.reason,
                "rating_change": round(part.rating_after - part.rating_before, 2) if part.rating_after is not None else None,
            }
        )
    return out


def set_rating_manually(db: Session, user_id: int, new_rating: float) -> float:
    """Admin correction of the duel rating. Returns the old value."""
    with _lock:
        row = get_duel_rating(db, user_id)
        old = float(row.rating)
        row.rating = new_rating
        db.commit()
        return old
