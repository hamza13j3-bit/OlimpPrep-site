from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text

from app.modules.checker.models import STATE_DONE, STATE_QUEUED, Submission
from app.modules.problems import service as ps
from app.modules.problems.models import Problem
from app.modules.problems.schemas import ProblemIn
from tests.conftest import auth, register


def make_problem(db, title="Есеп", rating=1000, tags=("math",), source="S", year=2026, hide=False, lang="kk"):
    data = ProblemIn(
        rating=rating,
        source=source,
        year=year,
        tags=list(tags),
        hide_tags_until_solved=hide,
        translations={lang: {"title": title, "statement": "x"}},
        subtasks=[{"points": 100, "tests": [{"input": "1\n", "output": "1\n", "is_example": True}]}],
    )
    return ps.create_problem(db, data).id


def add_sub(db, user_id, problem_id, score=0.0, solved=False, state=STATE_DONE):
    db.add(Submission(user_id=user_id, problem_id=problem_id, language="python", code="x",
                      state=state, score=score, solved=solved, tests_passed=0, tests_total=1))
    db.commit()


@pytest.fixture()
def env(client):
    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    admin = register(client, "admin@example.com")
    user = register(client, "user@example.com")
    return client, auth(admin["access_token"]), auth(user["access_token"]), user["user"]["id"]


def listing(client, query="", headers=None):
    r = client.get(f"/archive/problems?{query}", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def numbers(page):
    return [i["number"] for i in page["items"]]


# ----------------------------------- filters -----------------------------------


def test_basic_listing_and_fields(env):
    client, _, user, _ = env
    with client.session_factory() as db:
        pid = make_problem(db, "Палиндром", rating=900, tags=("strings", "math"))
    page = listing(client, headers=user)
    assert page["total"] == 1 and page["pages"] == 1 and page["per_page"] == 50
    item = page["items"][0]
    assert item["number"] == pid and item["title"] == "Палиндром" and item["rating"] == 900
    assert item["tags"] == ["math", "strings"] and item["solved_count"] == 0 and item["status"] == "unsolved"
    assert item["languages"] == ["kk"] and item["source"] == "S" and item["year"] == 2026


def test_tag_filter_is_and(env):
    client, *_ = env
    with client.session_factory() as db:
        a = make_problem(db, "A", tags=("dp",))
        b = make_problem(db, "B", tags=("dp", "graphs"))
        c = make_problem(db, "C", tags=("graphs",))
    assert numbers(listing(client, "tags=dp")) == [a, b]
    assert numbers(listing(client, "tags=dp&tags=graphs")) == [b]
    assert numbers(listing(client, "tags=dp,graphs")) == [b]
    assert numbers(listing(client, "tags=graphs")) == [b, c]
    assert listing(client, "tags=sorting")["total"] == 0


def test_rating_source_year_lang_filters(env):
    client, *_ = env
    with client.session_factory() as db:
        a = make_problem(db, "A", rating=800, source="X", year=2024)
        b = make_problem(db, "B", rating=1500, source="Y", year=2025, lang="en")
        c = make_problem(db, "C", rating=2000, source="X", year=2026)
    assert numbers(listing(client, "rating_min=1000")) == [b, c]
    assert numbers(listing(client, "rating_max=1500")) == [a, b]
    assert numbers(listing(client, "rating_min=900&rating_max=1600")) == [b]
    assert numbers(listing(client, "rating_min=1600&rating_max=900")) == []
    assert numbers(listing(client, "source=X")) == [a, c]
    assert numbers(listing(client, "year=2025")) == [b]
    assert numbers(listing(client, "lang=en")) == [b]
    assert numbers(listing(client, "lang=kk")) == [a, c]
    assert numbers(listing(client, "source=X&year=2026&rating_min=1900")) == [c]


def test_search_by_title_and_number(env):
    client, *_ = env
    with client.session_factory() as db:
        a = make_problem(db, "Палиндром")
        b = make_problem(db, "Жай сандар")
        c = make_problem(db, "100% дұрыс_жол")
    assert numbers(listing(client, "q=палин")) == [a]  # Cyrillic, case-insensitive
    assert numbers(listing(client, "q=ПАЛИНДРОМ")) == [a]
    assert numbers(listing(client, "q=сандар")) == [b]
    assert numbers(listing(client, f"q={b}")) == [b]  # by number
    assert numbers(listing(client, f"q=%23{c}")) == [c]  # "#3"
    assert numbers(listing(client, "q=%25")) == [c]  # a literal % is not a wildcard
    assert numbers(listing(client, "q=_")) == [c]  # nor is _
    assert listing(client, "q=жоқ")["total"] == 0


def test_title_in_ui_lang_with_fallback(env):
    client, admin, *_ = env
    body = {
        "translations": {"kk": {"title": "Қосынды", "statement": "x"}, "en": {"title": "Sum", "statement": "x"}},
        "subtasks": [{"points": 1, "tests": [{"input": "1", "output": "1"}]}],
    }
    client.post("/problems", json=body, headers=admin)
    assert listing(client)["items"][0]["title"] == "Қосынды"
    assert listing(client, "ui_lang=en")["items"][0]["title"] == "Sum"
    assert listing(client, "ui_lang=ru")["items"][0]["title"] == "Қосынды"  # falls back to kk
    assert listing(client, "lang=en")["items"][0]["title"] == "Sum"
    assert listing(client)["items"][0]["languages"] == ["kk", "en"]


# ------------------------------------ status -----------------------------------


def test_status_calculation(env):
    client, _, user, uid = env
    with client.session_factory() as db:
        none = make_problem(db, "none")
        failed = make_problem(db, "failed")
        partial = make_problem(db, "partial")
        solved = make_problem(db, "solved")
        solved_then_failed = make_problem(db, "stf")
        pending = make_problem(db, "pending")
        add_sub(db, uid, failed, 0.0)
        add_sub(db, uid, partial, 0.6)
        add_sub(db, uid, solved, 1.0, True)
        add_sub(db, uid, solved_then_failed, 1.0, True)
        add_sub(db, uid, solved_then_failed, 0.0)  # a later failure does not undo solved
        add_sub(db, uid, pending, 0.0, state=STATE_QUEUED)  # not checked yet: no attempt
    st = {i["number"]: i["status"] for i in listing(client, headers=user)["items"]}
    assert st == {none: "unsolved", failed: "attempted", partial: "attempted", solved: "solved",
                  solved_then_failed: "solved", pending: "unsolved"}
    assert numbers(listing(client, "status=solved", headers=user)) == [solved, solved_then_failed]
    assert numbers(listing(client, "status=attempted", headers=user)) == [failed, partial]
    assert numbers(listing(client, "status=unsolved", headers=user)) == [none, pending]
    assert listing(client, "status=attempted&rating_min=5000", headers=user)["total"] == 0


def test_status_is_per_user_and_anonymous_has_none(env):
    client, _, user, uid = env
    other = register(client, "o@example.com")
    with client.session_factory() as db:
        p = make_problem(db, "P")
        add_sub(db, other["user"]["id"], p, 1.0, True)
    mine = listing(client, headers=user)["items"][0]
    assert mine["status"] == "unsolved" and mine["solved_count"] == 1
    anon = listing(client)
    assert anon["items"][0]["status"] is None
    assert listing(client, "status=solved")["total"] == 0  # nobody is logged in
    assert listing(client, "status=unsolved")["total"] == 1


def test_solved_count_counts_distinct_users(env):
    client, _, user, uid = env
    other = register(client, "o@example.com")["user"]["id"]
    with client.session_factory() as db:
        p = make_problem(db, "P")
        add_sub(db, uid, p, 1.0, True)
        add_sub(db, uid, p, 1.0, True)  # same user twice
        add_sub(db, other, p, 1.0, True)
        add_sub(db, other, p, 0.2)  # not solving
    assert listing(client)["items"][0]["solved_count"] == 2


# ------------------------------------- tag hiding -----------------------------------


def test_hidden_tags_in_listing_and_tag_filter(env):
    client, admin, user, uid = env
    with client.session_factory() as db:
        shown = make_problem(db, "shown", tags=("dp",))
        hidden = make_problem(db, "hidden", tags=("dp",), hide=True)
    items = {i["number"]: i for i in listing(client, headers=user)["items"]}
    assert items[shown]["tags"] == ["dp"] and items[hidden]["tags"] == [] and items[hidden]["tags_hidden"]
    # filtering by tag must not reveal that the hidden problem has it
    assert numbers(listing(client, "tags=dp", headers=user)) == [shown]
    assert numbers(listing(client, "tags=dp")) == [shown]
    # admin sees everything
    assert numbers(listing(client, "tags=dp", headers=admin)) == [shown, hidden]
    # after solving it, tags show and the filter matches
    with client.session_factory() as db:
        add_sub(db, uid, hidden, 1.0, True)
    items = {i["number"]: i for i in listing(client, headers=user)["items"]}
    assert items[hidden]["tags"] == ["dp"] and not items[hidden]["tags_hidden"]
    assert numbers(listing(client, "tags=dp", headers=user)) == [shown, hidden]


# ------------------------------------ sorting / paging ------------------------------


def seed_many(client, n):
    with client.session_factory() as db:
        return [make_problem(db, f"P{i}", rating=800 + (i * 37) % 1200) for i in range(n)]


def test_pagination_50_per_page(env):
    client, *_ = env
    ids = seed_many(client, 120)
    p1, p2, p3, p4 = (listing(client, f"page={n}") for n in (1, 2, 3, 4))
    assert [len(p["items"]) for p in (p1, p2, p3, p4)] == [50, 50, 20, 0]
    assert p1["total"] == 120 and p1["pages"] == 3 and p1["page"] == 1
    assert numbers(p1) + numbers(p2) + numbers(p3) == ids  # stable, no overlap, no gaps
    assert client.get("/archive/problems?page=0").status_code == 422


def test_sorting(env):
    client, _, user, uid = env
    with client.session_factory() as db:
        a = make_problem(db, "A", rating=1500)
        b = make_problem(db, "B", rating=800)
        c = make_problem(db, "C", rating=1100)
        db.execute(Problem.__table__.update().where(Problem.id == a).values(
            created_at=datetime.now(timezone.utc) - timedelta(days=3)))
        db.execute(Problem.__table__.update().where(Problem.id == c).values(
            created_at=datetime.now(timezone.utc) + timedelta(days=3)))
        db.commit()
    other = register(client, "o@example.com")["user"]["id"]
    third = register(client, "t@example.com")["user"]["id"]
    with client.session_factory() as db:
        add_sub(db, other, b, 1.0, True)
        add_sub(db, third, b, 1.0, True)
        add_sub(db, other, c, 1.0, True)
    assert numbers(listing(client, "sort=number")) == [a, b, c]
    assert numbers(listing(client, "sort=number&order=desc")) == [c, b, a]
    assert numbers(listing(client, "sort=rating")) == [b, c, a]
    assert numbers(listing(client, "sort=rating&order=desc")) == [a, c, b]
    assert numbers(listing(client, "sort=solved")) == [b, c, a]  # most solved first
    assert numbers(listing(client, "sort=solved&order=asc")) == [a, c, b]
    assert numbers(listing(client, "sort=newest")) == [c, b, a]
    assert client.get("/archive/problems?sort=bogus").status_code == 422


def test_no_n_plus_one(env):
    client, _, user, uid = env
    def count_statements(add):
        seed_many(client, add)
        stmts = []
        listener = lambda conn, cur, stmt, *a: stmts.append(stmt)  # noqa: E731
        event.listen(client.engine, "before_cursor_execute", listener)
        try:
            listing(client, "tags=math", headers=user)
        finally:
            event.remove(client.engine, "before_cursor_execute", listener)
        return len(stmts)

    few = count_statements(3)
    many = count_statements(47)  # now 50 problems, all on one page
    assert listing(client, headers=user)["total"] == 50
    assert few == many  # same number of queries for 3 or 50 rows
    assert many <= 8


# ------------------------------------- collections -----------------------------------


def test_collections_crud_order_and_guards(env):
    client, admin, user, uid = env
    with client.session_factory() as db:
        p1, p2, p3 = (make_problem(db, f"P{i}") for i in range(3))
    body = {"title": "Бастау", "description": "d", "problem_ids": [p3, p1, p2]}
    assert client.post("/collections", json=body).status_code == 401
    assert client.post("/collections", json=body, headers=user).status_code == 403
    r = client.post("/collections", json=body, headers=admin)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert [p["number"] for p in r.json()["problems"]] == [p3, p1, p2]  # admin-defined order

    lst = client.get("/collections").json()
    assert lst == [{"id": cid, "title": "Бастау", "description": "d", "problem_count": 3}]
    with client.session_factory() as db:
        add_sub(db, uid, p1, 1.0, True)
    detail = client.get(f"/collections/{cid}", headers=user).json()
    assert [(p["number"], p["status"]) for p in detail["problems"]] == [(p3, "unsolved"), (p1, "solved"), (p2, "unsolved")]

    upd = client.put(f"/collections/{cid}", json={"title": "Жаңа", "problem_ids": [p2, p3]}, headers=admin)
    assert upd.status_code == 200 and [p["number"] for p in upd.json()["problems"]] == [p2, p3]
    # same payload twice (unique keys) still works
    assert client.put(f"/collections/{cid}", json={"title": "Жаңа", "problem_ids": [p2, p3]}, headers=admin).status_code == 200
    assert client.put(f"/collections/{cid}", json=body, headers=user).status_code == 403

    assert client.delete(f"/collections/{cid}", headers=user).status_code == 403
    assert client.delete(f"/collections/{cid}", headers=admin).status_code == 204
    assert client.get(f"/collections/{cid}").status_code == 404
    assert client.delete(f"/collections/{cid}", headers=admin).status_code == 404
    # problems themselves are untouched
    assert listing(client)["total"] == 3


def test_collection_validation(env):
    client, admin, *_ = env
    with client.session_factory() as db:
        p1 = make_problem(db, "P")
    assert client.post("/collections", json={"title": "A", "problem_ids": [p1, 999]}, headers=admin).status_code == 422
    assert client.post("/collections", json={"title": "A", "problem_ids": [p1, p1]}, headers=admin).status_code == 422
    assert client.post("/collections", json={"title": ""}, headers=admin).status_code == 422
    assert client.post("/collections", json={"title": "A"}, headers=admin).status_code == 201
    assert client.post("/collections", json={"title": "A"}, headers=admin).status_code == 409
    assert client.put("/collections/999", json={"title": "Z"}, headers=admin).status_code == 404
    other = client.post("/collections", json={"title": "B"}, headers=admin).json()["id"]
    assert client.put(f"/collections/{other}", json={"title": "A"}, headers=admin).status_code == 409
    # failed update leaves the old data
    assert client.put(f"/collections/{other}", json={"title": "B2", "problem_ids": [999]}, headers=admin).status_code == 422
    assert client.get(f"/collections/{other}").json()["title"] == "B"


def test_deleted_problem_disappears_from_collection(env):
    client, admin, *_ = env
    with client.session_factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        p1, p2 = make_problem(db, "P1"), make_problem(db, "P2")
    cid = client.post("/collections", json={"title": "C", "problem_ids": [p1, p2]}, headers=admin).json()["id"]
    assert client.delete(f"/problems/{p1}", headers=admin).status_code == 204
    assert [p["number"] for p in client.get(f"/collections/{cid}").json()["problems"]] == [p2]
    assert client.get("/collections").json()[0]["problem_count"] == 1


def test_seed_creates_all_collections(client):
    from app.seed.problems_data import COLLECTIONS
    from app.seed.run import seed

    with client.session_factory() as db:
        seed(db)
        seed(db)  # idempotent
    cols = client.get("/collections").json()
    assert len(cols) == len(COLLECTIONS) and all(c["problem_count"] >= 5 for c in cols)
    assert sum(c["problem_count"] for c in cols) == listing(client)["total"] >= 30
