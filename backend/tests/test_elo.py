import pytest

from app.modules.rating import elo


def test_expected_basics():
    assert elo.expected(1200, 1200) == pytest.approx(0.5)
    assert elo.expected(1600, 1200) == pytest.approx(1 / (1 + 10 ** (-1)))  # 0.909...
    assert elo.expected(1200, 1600) == pytest.approx(1 / (1 + 10))  # 0.0909...
    # symmetric: E(a vs b) + E(b vs a) == 1
    assert elo.expected(1337, 1021) + elo.expected(1021, 1337) == pytest.approx(1.0)


def test_k_schedule():
    assert [elo.k_player(n) for n in (0, 1, 9)] == [40, 40, 40]
    assert [elo.k_player(n) for n in (10, 11, 29)] == [24, 24, 24]
    assert [elo.k_player(n) for n in (30, 31, 500)] == [16, 16, 16]
    assert elo.K_PROBLEM == 8


def test_known_value():
    # R=1200 vs problem 1200, solved fully, first attempt: 1200 + 40 * 0.5 = 1220
    assert elo.apply_delta(1200, elo.player_delta(1200, 1200, 1.0, 0)) == pytest.approx(1220)
    # S = E gives no change
    e = elo.expected(1500, 1300)
    assert elo.player_delta(1500, 1300, e, 12) == pytest.approx(0)


def test_beating_an_easy_problem_gives_little():
    gain = elo.player_delta(1500, 1000, 1.0, attempts_before=15)
    assert 0 < gain < 2


def test_failing_an_easy_problem_costs_a_lot():
    loss = elo.player_delta(1500, 1000, 0.0, attempts_before=15)
    assert loss < -20
    assert abs(loss) > 10 * elo.player_delta(1500, 1000, 1.0, attempts_before=15)


def test_beating_a_hard_problem_gives_a_lot():
    gain = elo.player_delta(1000, 1500, 1.0, attempts_before=15)
    assert gain > 20
    assert gain > 10 * elo.player_delta(1500, 1000, 1.0, attempts_before=15)


def test_failing_a_hard_problem_costs_little():
    assert -2 < elo.player_delta(1000, 1500, 0.0, attempts_before=15) < 0


def test_partial_score_is_between():
    lo = elo.player_delta(1200, 1200, 0.0, 15)
    mid = elo.player_delta(1200, 1200, 0.5, 15)
    hi = elo.player_delta(1200, 1200, 1.0, 15)
    assert lo < mid < hi and mid == pytest.approx(0)


def test_newcomers_move_faster():
    assert elo.player_delta(1200, 1200, 1.0, 0) > elo.player_delta(1200, 1200, 1.0, 15) > elo.player_delta(
        1200, 1200, 1.0, 40
    )


def test_problem_is_the_mirror_with_k8():
    pd = elo.problem_delta(1300, 1200, 1.0)  # player solved it -> problem gets easier
    assert pd < 0
    # zero-sum up to the K ratio: problem change = -(8/K_player) * player change
    pl = elo.player_delta(1300, 1200, 1.0, 15)
    assert pd == pytest.approx(-pl * elo.K_PROBLEM / elo.k_player(15))
    assert elo.problem_delta(1300, 1200, 0.0) > 0  # player failed -> problem harder


def test_floor():
    assert elo.apply_delta(805, -50) == 800
    assert elo.apply_delta(800, -10) == 800
    assert elo.apply_delta(900, -10) == 890
    # a value already below the floor is not pushed up
    assert elo.apply_delta(500, 0) == 500 and elo.apply_delta(500, -5) == 500


def test_hint_multipliers():
    assert elo.effective_score(1.0, 0) == 1.0
    assert elo.effective_score(1.0, 1) == pytest.approx(0.9)
    assert elo.effective_score(1.0, 2) == pytest.approx(0.8)
    assert elo.effective_score(1.0, 3) == pytest.approx(0.7)
    assert elo.effective_score(0.4, 3) == pytest.approx(0.28)
    assert 0 <= elo.effective_score(1.7, 9) <= 1  # clamped
