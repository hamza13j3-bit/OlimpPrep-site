import copy

import pytest

from app.core import db as core_db
from app.main import app
from app.modules.problems.deps import get_solved_ids
from tests.conftest import auth, register


def payload(**over):
    base = {
        "rating": 1000,
        "source": "Test",
        "year": 2026,
        "author": "me",
        "tags": ["math"],
        "translations": {"kk": {"title": "Қосынды", "statement": "$a+b$ табыңыз"}},
        "subtasks": [
            {
                "points": 40,
                "tests": [
                    {"input": "1 2\n", "output": "3\n", "is_example": True},
                    {"input": "5 5\n", "output": "10\n"},
                ],
            },
            {"points": 60, "tests": [{"input": "100 200\n", "output": "300\n"}]},
        ],
        "hints": [
            {"level": 1, "lang": "kk", "text": "Қосыңыз"},
            {"level": 2, "lang": "kk", "text": "Арифметика"},
            {"level": 3, "lang": "kk", "text": "print(a+b)"},
        ],
    }
    base.update(over)
    return base


@pytest.fixture()
def env(client):
    from app.modules.problems import service

    gen = app.dependency_overrides[core_db.get_db]()
    db = next(gen)
    service.ensure_default_tags(db)
    admin = register(client, "admin@example.com")["access_token"]
    user = register(client, "user@example.com")["access_token"]
    yield client, auth(admin), auth(user)
    app.dependency_overrides.pop(get_solved_ids, None)
    db.close()


def test_create_and_defaults(env):
    client, admin, _ = env
    body = payload()
    del body["rating"]
    r = client.post("/problems", json=body, headers=admin)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["rating"] == 1200 and out["time_limit_ms"] == 1000 and out["memory_limit_mb"] == 256
    assert out["number"] == out["id"] and out["tags"] == ["math"]
    assert [h["level"] for h in out["hints"]] == [1, 2, 3]
    assert [s["points"] for s in out["subtasks"]] == [40, 60]


def test_role_guards(env):
    client, admin, user = env
    pid = client.post("/problems", json=payload(), headers=admin).json()["id"]
    for method, url, body in [
        ("post", "/problems", payload()),
        ("put", f"/problems/{pid}", payload()),
        ("delete", f"/problems/{pid}", None),
        ("get", f"/problems/{pid}/admin", None),
        ("post", "/tags", {"slug": "x"}),
    ]:
        kw = {"json": body} if body is not None else {}
        assert getattr(client, method)(url, **kw).status_code == 401, (method, url)
        assert getattr(client, method)(url, headers=user, **kw).status_code == 403, (method, url)


def test_validation(env):
    client, admin, _ = env
    bad = [
        payload(subtasks=[]),
        payload(translations={}),
        payload(rating=5),
        payload(time_limit_ms=1),
        payload(subtasks=[{"points": 10, "tests": []}]),
        payload(hints=[{"level": 4, "lang": "kk", "text": "x"}]),
        payload(
            hints=[
                {"level": 1, "lang": "kk", "text": "a"},
                {"level": 1, "lang": "kk", "text": "b"},
            ]
        ),
        payload(translations={"fr": {"title": "x", "statement": "y"}}),
        payload(subtasks=[{"points": 1, "tests": [{"input": "x" * (5 * 1024 * 1024 + 1), "output": ""}]}]),
    ]
    for b in bad:
        assert client.post("/problems", json=b, headers=admin).status_code == 422
    r = client.post("/problems", json=payload(tags=["nope"]), headers=admin)
    assert r.status_code == 422 and "nope" in r.text


def test_public_view_hides_tests_and_hints(env):
    client, admin, _ = env
    pid = client.post("/problems", json=payload(), headers=admin).json()["id"]
    r = client.get(f"/problems/{pid}")  # anonymous is fine
    assert r.status_code == 200
    out = r.json()
    assert out["examples"] == [{"input": "1 2\n", "output": "3\n"}]
    assert "5 5" not in r.text and "300" not in r.text  # non-example tests never leak
    assert "hints" not in out and "Қосыңыз" not in r.text
    assert client.get("/problems/999").status_code == 404


def test_translation_fallback(env):
    client, admin, _ = env
    tr = {
        "kk": {"title": "KK", "statement": "kk text"},
        "en": {"title": "EN", "statement": "en text"},
    }
    pid = client.post("/problems", json=payload(translations=tr), headers=admin).json()["id"]
    assert client.get(f"/problems/{pid}?lang=en").json()["title"] == "EN"
    ru = client.get(f"/problems/{pid}?lang=ru").json()  # missing -> kk
    assert ru["title"] == "KK" and ru["lang"] == "kk" and ru["languages"] == ["kk", "en"]

    only_en = {"en": tr["en"]}
    pid2 = client.post("/problems", json=payload(translations=only_en), headers=admin).json()["id"]
    assert client.get(f"/problems/{pid2}").json()["title"] == "EN"
    assert client.get(f"/problems/{pid}?lang=xx").status_code == 422


def test_tag_hiding(env):
    client, admin, user = env
    pid = client.post("/problems", json=payload(hide_tags_until_solved=True), headers=admin).json()["id"]
    open_id = client.post("/problems", json=payload(), headers=admin).json()["id"]

    anon = client.get(f"/problems/{pid}").json()
    assert anon["tags"] == [] and anon["tags_hidden"] is True
    assert client.get(f"/problems/{pid}", headers=user).json()["tags"] == []
    # problems without the flag always show tags
    assert client.get(f"/problems/{open_id}").json()["tags"] == ["math"]
    # admin always sees tags
    assert client.get(f"/problems/{pid}", headers=admin).json()["tags"] == ["math"]
    # once solved, the user sees them
    app.dependency_overrides[get_solved_ids] = lambda: {pid}
    shown = client.get(f"/problems/{pid}", headers=user).json()
    assert shown["tags"] == ["math"] and shown["tags_hidden"] is False


def test_update_replaces_children(env):
    client, admin, _ = env
    pid = client.post("/problems", json=payload(), headers=admin).json()["id"]
    new = payload(
        rating=1500,
        tags=["dp", "greedy"],
        translations={"kk": {"title": "Жаңа", "statement": "жаңа"}},
        subtasks=[{"points": 100, "tests": [{"input": "1\n", "output": "1\n", "is_example": True}]}],
        hints=[{"level": 1, "lang": "kk", "text": "жаңа кеңес"}],
    )
    r = client.put(f"/problems/{pid}", json=new, headers=admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["rating"] == 1500 and out["tags"] == ["dp", "greedy"]
    assert len(out["subtasks"]) == 1 and out["subtasks"][0]["points"] == 100
    assert len(out["hints"]) == 1 and out["translations"]["kk"]["title"] == "Жаңа"
    # same payload again (same unique keys) must also work
    assert client.put(f"/problems/{pid}", json=new, headers=admin).status_code == 200
    assert client.put("/problems/999", json=new, headers=admin).status_code == 404
    assert client.put(f"/problems/{pid}", json=payload(tags=["zzz"]), headers=admin).status_code == 422
    # failed update leaves data intact
    assert client.get(f"/problems/{pid}/admin", headers=admin).json()["rating"] == 1500


def test_delete(env):
    client, admin, _ = env
    pid = client.post("/problems", json=payload(), headers=admin).json()["id"]
    assert client.delete(f"/problems/{pid}", headers=admin).status_code == 204
    assert client.get(f"/problems/{pid}").status_code == 404
    assert client.delete(f"/problems/{pid}", headers=admin).status_code == 404


def test_tags_endpoints(env):
    client, admin, _ = env
    slugs = [t["slug"] for t in client.get("/tags").json()]
    assert "binary-search" in slugs and len(slugs) == 8
    assert client.post("/tags", json={"slug": "geometry"}, headers=admin).status_code == 201
    assert client.post("/tags", json={"slug": "geometry"}, headers=admin).status_code == 409
    assert client.post("/tags", json={"slug": "Bad Slug"}, headers=admin).status_code == 422


def test_payload_not_mutated_between_tests():
    # guard: payload() must build fresh structures each call
    a, b = payload(), payload()
    a["tags"].append("x")
    assert b["tags"] == ["math"] and copy.deepcopy(a) != b
