"""Pure Elo math (no I/O).

E  = 1 / (1 + 10^((R_problem - R_player) / 400))
R' = R + K * (S - E)            S = score in [0, 1] (reduced when hints were used)
Problems play the mirror game: R_p' = R_p + K_p * ((1 - S) - (1 - E)) = R_p - K_p * (S - E).
"""

START_RATING = 1200.0
FLOOR = 800.0

K_NEWBIE, K_MID, K_VETERAN = 40.0, 24.0, 16.0
NEWBIE_ATTEMPTS = 10  # attempts 1..10  -> K = 40
MID_ATTEMPTS = 30  # attempts 11..30 -> K = 24, afterwards 16
K_PROBLEM = 8.0

# Multiplier on S per hint level. When several hints were opened before the rated submission
# the lowest multiplier applies, i.e. the one of the deepest level (they never stack).
HINT_MULTIPLIER = {0: 1.0, 1: 0.9, 2: 0.8, 3: 0.7}


def expected(r_player: float, r_problem: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_problem - r_player) / 400.0))


def k_player(attempts_before: int) -> float:
    """K for a player who has already made `attempts_before` rated attempts."""
    if attempts_before < NEWBIE_ATTEMPTS:
        return K_NEWBIE
    if attempts_before < MID_ATTEMPTS:
        return K_MID
    return K_VETERAN


def effective_score(score: float, hint_level: int) -> float:
    score = min(1.0, max(0.0, score))
    return score * HINT_MULTIPLIER[min(3, max(0, hint_level))]


def apply_delta(old: float, delta: float, floor: float = FLOOR) -> float:
    """Never drop below the floor (a value already under it is not pushed up)."""
    return max(old + delta, min(old, floor))


def player_delta(r_player: float, r_problem: float, s: float, attempts_before: int) -> float:
    return k_player(attempts_before) * (s - expected(r_player, r_problem))


def problem_delta(r_player: float, r_problem: float, s: float) -> float:
    return -K_PROBLEM * (s - expected(r_player, r_problem))
