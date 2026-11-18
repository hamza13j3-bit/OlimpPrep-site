"""Duel Elo, separate from the training rating: K = 32, win 1 / draw 0.5 / loss 0, floor 800."""

START_RATING = 1200.0
FLOOR = 800.0
K = 32.0


def expected(r_player: float, r_opponent: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_opponent - r_player) / 400.0))


def _apply(old: float, delta: float) -> float:
    return max(old + delta, min(old, FLOOR))


def update(r_a: float, r_b: float, score_a: float) -> tuple[float, float]:
    """New ratings after a game where player A scored `score_a` (1, 0.5 or 0)."""
    e_a = expected(r_a, r_b)
    return _apply(r_a, K * (score_a - e_a)), _apply(r_b, K * ((1.0 - score_a) - (1.0 - e_a)))
