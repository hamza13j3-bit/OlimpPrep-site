import pytest

from app.main import app
from app.modules.auth.models import User
from app.modules.checker.router import get_queue
from app.modules.duel.models import DuelRating
from app.modules.rating.models import PlayerRating, TagRating
from tests.conftest import auth, register
from tests.test_rating import SUM_PY, SyncQueue, problem_payload, submit


@pytest.fixture()
def env(client):
    from app.modules.problems import service as ps

    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    app.dependency_overrides[get_queue] = lambda: SyncQueue(client.session_factory)
    admin = auth(register(client, "admin@example.com", name="Admin")["access_token"])
    return client, admin


def add_users(client, ratings, *, kind="global", tag=None, attempts=1):
    """Create one user per rating (names u0, u1, ...); returns their ids."""
    ids = []
    with client.session_factory() as db:
        base = db.query(User).count()
        for i, r in enumerate(ratings):
            u = User(email=f"u{base + i}@example.com", password_hash="x", name=f"u{i}")
            db.add(u)
            db.flush()
            ids.append(u.id)
            if kind == "global":
                db.add(PlayerRating(user_id=u.id, rating=r, attempts=attempts))
            elif kind == "tag":
                db.add(TagRating(user_id=u.id, tag=tag, rating=r, attempts=attempts))
            else:
                db.add(DuelRating(user_id=u.id, rating=r, games=attempts))
        db.commit()
    return ids


def board(client, path="/leaderboards/global", headers=None, **params):
    r = client.get(path, params=params, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def ranks(page):
    return [(i["name"], i["rank"], i["rating"]) for i in page["items"]]


# ----------------------------------------- ranking ------------------------------------------


def test_empty_board(env):
    client, _ = env
    assert board(client) == {"items": [], "total": 0, "page": 1, "page_size": 50, "me": None}


def test_rank_with_ties_skips_after_a_tie(env):
    client, _ = env
    add_users(client, [1500, 1400, 1400, 1400, 1300, 1200])
    assert ranks(board(client)) == [
        ("u0", 1, 1500), ("u1", 2, 1400), ("u2", 2, 1400), ("u3", 2, 1400), ("u4", 5, 1300), ("u5", 6, 1200),
    ]


def test_ties_are_decided_on_the_displayed_integer_rating(env):
    client, _ = env
    add_users(client, [1400.4, 1399.6, 1399.4])
    assert ranks(board(client)) == [("u0", 1, 1400), ("u1", 1, 1400), ("u2", 3, 1399)]


def test_equal_ratings_are_ordered_by_solved_then_id(env):
    client, admin = env
    pid = [client.post("/problems", json=problem_payload(), headers=admin).json()["id"] for _ in range(2)]
    a, b, c = add_users(client, [1500, 1500, 1500])
    from app.modules.checker.models import Submission

    with client.session_factory() as db:  # b solved 2 problems, c solved 1, a none
        for user, problems in ((b, pid), (c, pid[:1])):
            for p in problems:
                db.add(Submission(user_id=user, problem_id=p, language="python", code="x", state="done", solved=True, score=1.0))
        db.commit()
    page = board(client)
    assert [(i["user_id"], i["rank"], i["solved"]) for i in page["items"]] == [(b, 1, 2), (c, 1, 1), (a, 1, 0)]


def test_tie_across_the_page_boundary_keeps_the_same_rank(env):
    client, _ = env
    # 49 distinct, then 3 users tied at the 50th..52nd place, then 1 lower
    add_users(client, [3000 - i for i in range(49)] + [1000, 1000, 1000, 900])
    p1, p2 = board(client), board(client, page=2)
    assert len(p1["items"]) == 50 and len(p2["items"]) == 3
    assert [i["rank"] for i in p1["items"]][-1] == 50  # first of the tie
    assert [i["rank"] for i in p2["items"]] == [50, 50, 53]
    assert p1["total"] == p2["total"] == 53


def test_pagination_is_50_per_page(env):
    client, _ = env
    add_users(client, [5000 - i for i in range(120)])
    sizes = [len(board(client, page=n)["items"]) for n in (1, 2, 3, 4)]
    assert sizes == [50, 50, 20, 0]
    p3 = board(client, page=3)
    assert p3["items"][0]["rank"] == 101 and p3["items"][-1]["rank"] == 120 and p3["page_size"] == 50
    assert client.get("/leaderboards/global?page=0").status_code == 422


# ------------------------------------- who is on the board -----------------------------------


def test_blocked_and_unrated_players_are_left_out(env):
    client, admin = env
    a, b, c = add_users(client, [1500, 1400, 1300])
    add_users(client, [1700], attempts=0)  # never made a rated attempt
    client.patch(f"/admin/users/{b}/block", json={"blocked": True}, headers=admin)
    assert [(i["user_id"], i["rank"]) for i in board(client)["items"]] == [(a, 1), (c, 2)]
    client.patch(f"/admin/users/{b}/block", json={"blocked": False}, headers=admin)
    assert [i["user_id"] for i in board(client)["items"]] == [a, b, c]


def test_rows_expose_no_private_data(env):
    client, _ = env
    add_users(client, [1500])
    item = board(client)["items"][0]
    assert set(item) == {"rank", "user_id", "name", "rating", "solved", "is_me"}


def test_real_solving_puts_a_player_on_the_global_board(env):
    client, admin = env
    pid = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    user = register(client, "user@example.com", name="Aigerim")
    h = auth(user["access_token"])
    assert board(client)["items"] == []
    submit(client, h, pid, SUM_PY)
    items = board(client)["items"]
    assert [(i["name"], i["rating"], i["solved"], i["rank"]) for i in items] == [("Aigerim", 1220, 1, 1)]


# --------------------------------------- tag and duel boards --------------------------------


def test_tag_board_uses_tag_ratings_and_tag_solved_counts(env):
    client, admin = env
    p_math = client.post("/problems", json=problem_payload(tags=("math",)), headers=admin).json()["id"]
    p_dp = client.post("/problems", json=problem_payload(tags=("dp",)), headers=admin).json()["id"]
    user = register(client, "user@example.com", name="Aigerim")
    h = auth(user["access_token"])
    submit(client, h, p_math, SUM_PY)
    submit(client, h, p_dp, SUM_PY)
    math, dp = board(client, "/leaderboards/tag/math"), board(client, "/leaderboards/tag/dp")
    assert [(i["name"], i["solved"]) for i in math["items"]] == [("Aigerim", 1)]  # only math problems
    assert [(i["name"], i["solved"]) for i in dp["items"]] == [("Aigerim", 1)]
    assert board(client, "/leaderboards/tag/graphs")["items"] == []
    assert board(client)["items"][0]["solved"] == 2
    assert client.get("/leaderboards/tag/unknown").status_code == 404
    add_users(client, [1600, 1600, 1500], kind="tag", tag="graphs")
    assert [(i["rank"], i["rating"]) for i in board(client, "/leaderboards/tag/graphs")["items"]] == [
        (1, 1600), (1, 1600), (3, 1500),
    ]


def test_duel_board(env):
    client, _ = env
    add_users(client, [1300, 1250, 1250], kind="duel")
    add_users(client, [2000], kind="duel", attempts=0)  # no games played
    assert ranks(board(client, "/leaderboards/duel")) == [("u0", 1, 1300), ("u1", 2, 1250), ("u2", 2, 1250)]
    assert board(client)["items"] == []  # separate from the training board


# --------------------------------------- my position -----------------------------------------


def test_current_user_is_highlighted_with_position_and_page(env):
    client, _ = env
    ids = add_users(client, [5000 - i for i in range(120)])
    me = ids[74]  # 75th place -> page 2
    with client.session_factory() as db:
        from app.core.security import create_access_token

        token = create_access_token(me)
    h = auth(token)
    p2 = board(client, headers=h, page=2)
    mine = [i for i in p2["items"] if i["is_me"]]
    assert [i["user_id"] for i in mine] == [me] and mine[0]["rank"] == 75
    assert p2["me"] == {"rank": 75, "position": 75, "page": 2, "rating": 4926, "solved": 0}
    assert not any(i["is_me"] for i in board(client, headers=h, page=1)["items"])
    assert board(client, headers=h, page=1)["me"]["page"] == 2  # the "my position" button target


def test_my_position_with_ties(env):
    client, _ = env
    ids = add_users(client, [1500, 1400, 1400, 1400, 1300])
    from app.core.security import create_access_token

    h = auth(create_access_token(ids[3]))
    me = board(client, headers=h)["me"]
    assert (me["rank"], me["position"], me["page"]) == (2, 4, 1)  # shares rank 2, 4th row


def test_my_position_is_null_when_not_on_the_board(env):
    client, admin = env
    add_users(client, [1500])
    assert board(client, headers=admin)["me"] is None  # admin never made a rated attempt
    assert board(client)["me"] is None  # anonymous
    assert board(client, "/leaderboards/duel", headers=admin)["me"] is None


def test_blocked_viewer_has_no_position(env):
    client, admin = env
    (uid,) = add_users(client, [1500])
    from app.core.security import create_access_token

    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    assert board(client, headers=auth(create_access_token(uid)))["me"] is None
