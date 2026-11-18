import json
from datetime import datetime, timedelta, timezone

import pytest

from app.main import app
from app.modules.admin import audit
from app.modules.admin.models import AuditLog
from app.modules.checker.models import Submission
from app.modules.checker.router import get_queue
from app.modules.rating.models import PlayerRating, TagRating
from tests.conftest import auth, register, write_note
from tests.test_rating import SUM_PY, SyncQueue, problem_payload, submit


@pytest.fixture()
def env(client):
    from app.modules.problems import service as ps

    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    app.dependency_overrides[get_queue] = lambda: SyncQueue(client.session_factory)
    admin = register(client, "admin@example.com", name="Admin")
    user = register(client, "user@example.com", name="Aigerim")
    pid = client.post("/problems", json=problem_payload(), headers=auth(admin["access_token"])).json()["id"]
    return client, auth(admin["access_token"]), auth(user["access_token"]), admin["user"]["id"], user["user"]["id"], pid


def audit_rows(client):
    with client.session_factory() as db:
        return [(a.action, a.admin_id, a.target_id) for a in db.query(AuditLog).order_by(AuditLog.id)]


# ------------------------------ role guards on EVERY admin endpoint ------------------------------

ADMIN_ENDPOINTS = [
    ("GET", "/admin/users", None),
    ("PATCH", "/admin/users/{uid}/block", {"blocked": True}),
    ("POST", "/admin/users/{uid}/promote", None),
    ("POST", "/admin/users/{uid}/rating", {"scope": "global", "rating": 1500, "reason": "manual fix"}),
    ("GET", "/admin/stats", None),
    ("GET", "/admin/audit", None),
    # admin-only endpoints of the other modules
    ("POST", "/tags", {"slug": "newtag"}),
    ("POST", "/problems", None),
    ("PUT", "/problems/{pid}", None),
    ("DELETE", "/problems/{pid}", None),
    ("GET", "/problems/{pid}/admin", None),
    ("GET", "/problems/{pid}/notes", None),
    ("POST", "/collections", {"title": "c", "description": "", "problem_ids": []}),
    ("PUT", "/collections/1", {"title": "c", "description": "", "problem_ids": []}),
    ("DELETE", "/collections/1", None),
    ("GET", "/archive/problems/{pid}/export", None),
    ("POST", "/archive/import", None),
]


def call(client, method, path, body, headers=None):
    kw = {"headers": headers or {}}
    if body is not None:
        kw["json"] = body
    return client.request(method, path, **kw)


@pytest.mark.parametrize("method, path, body", ADMIN_ENDPOINTS)
def test_every_admin_endpoint_rejects_anonymous_and_plain_users(env, method, path, body):
    client, _, user, _, uid, pid = env
    path = path.format(uid=uid, pid=pid)
    assert call(client, method, path, body).status_code == 401
    assert call(client, method, path, body, user).status_code == 403


def test_blocked_admin_is_rejected_too(env):
    client, admin, _, aid, uid, _ = env
    other = register(client, "second@example.com")
    client.post(f"/admin/users/{other['user']['id']}/promote", headers=admin)
    h = auth(other["access_token"])
    assert client.get("/admin/users", headers=h).status_code == 200
    client.patch(f"/admin/users/{other['user']['id']}/block", json={"blocked": True}, headers=admin)
    assert client.get("/admin/users", headers=h).status_code == 403
    assert client.get("/admin/audit", headers=h).status_code == 403


def test_admin_endpoints_work_for_admin(env):
    client, admin, _, _, uid, pid = env
    for i in (0, 3, 4, 5, 2, 1):  # block last, a blocked user cannot be promoted
        method, path, body = ADMIN_ENDPOINTS[i]
        r = call(client, method, path.format(uid=uid, pid=pid), body, admin)
        assert r.status_code == 200, (method, path, r.text)


# -------------------------------------- blocked users ---------------------------------------


def test_blocked_user_cannot_log_in_or_submit(env):
    client, admin, user, _, uid, pid = env
    write_note(client, user, pid)
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "password1"})
    assert login.status_code == 403
    # a token issued before the block no longer lets them submit
    body = {"problem_id": pid, "language": "python", "code": SUM_PY}
    assert client.post("/submissions", json=body, headers=user).status_code == 403
    client.patch(f"/admin/users/{uid}/block", json={"blocked": False}, headers=admin)
    assert client.post("/auth/login", json={"email": "user@example.com", "password": "password1"}).status_code == 200
    assert client.post("/submissions", json=body, headers=user).status_code == 202


# ------------------------------------------- users ---------------------------------------------


def test_users_table_search_and_paging(env):
    client, admin, _, _, uid, _ = env
    register(client, "kairat@example.com", name="Қайрат Ахмет")
    r = client.get("/admin/users", headers=admin).json()
    assert r["total"] == 3 and r["page_size"] == 50 and "password_hash" not in json.dumps(r)
    assert [u["email"] for u in client.get("/admin/users?q=aigerim", headers=admin).json()["items"]] == [
        "user@example.com"
    ]
    assert [u["email"] for u in client.get("/admin/users?q=ҚАЙРАТ", headers=admin).json()["items"]] == [
        "kairat@example.com"
    ]  # Cyrillic, case-insensitive
    assert client.get("/admin/users?q=EXAMPLE.com", headers=admin).json()["total"] == 3
    assert client.get("/admin/users?q=nobody", headers=admin).json()["items"] == []
    assert client.get("/admin/users?page=2", headers=admin).json()["items"] == []


def test_users_table_shows_rating(env):
    client, admin, user, _, uid, pid = env
    submit(client, user, pid, SUM_PY)
    rows = {u["id"]: u for u in client.get("/admin/users", headers=admin).json()["items"]}
    assert rows[uid]["rating"] == pytest.approx(1220.0)
    assert rows[1]["rating"] is None


def test_block_unblock_promote_and_audit(env):
    client, admin, _, aid, uid, _ = env
    r = client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    assert r.status_code == 200 and r.json()["is_blocked"] is True
    assert client.patch(f"/admin/users/{uid}/block", json={"blocked": False}, headers=admin).json()["is_blocked"] is False
    assert client.patch(f"/admin/users/{aid}/block", json={"blocked": True}, headers=admin).status_code == 400
    assert client.patch("/admin/users/999/block", json={"blocked": True}, headers=admin).status_code == 404
    p = client.post(f"/admin/users/{uid}/promote", headers=admin)
    assert p.status_code == 200 and p.json()["role"] == "admin"
    assert client.post(f"/admin/users/{uid}/promote", headers=admin).status_code == 409
    assert client.post("/admin/users/999/promote", headers=admin).status_code == 404
    # the new admin really is one
    new_admin = auth(client.post("/auth/login", json={"email": "user@example.com", "password": "password1"}).json()["access_token"])
    assert client.get("/admin/users", headers=new_admin).status_code == 200
    # only successful actions are logged, in order
    assert [a for a, _, _ in audit_rows(client)][-3:] == ["user.block", "user.unblock", "user.promote"]


def test_blocked_user_cannot_be_promoted(env):
    client, admin, _, _, uid, _ = env
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    assert client.post(f"/admin/users/{uid}/promote", headers=admin).status_code == 409


# ------------------------------------------- stats --------------------------------------------


def test_stats_counts_and_days(env):
    client, admin, user, _, uid, pid = env
    s = client.get("/admin/stats", headers=admin).json()
    assert (s["users_total"], s["users_blocked"], s["admins"], s["submissions_total"]) == (2, 0, 1, 0)
    days = s["submissions_per_day"]
    assert len(days) == 30 and all(d["count"] == 0 for d in days)
    today = datetime.now(timezone.utc).date()
    assert days[-1]["day"] == today.isoformat() and days[0]["day"] == (today - timedelta(days=29)).isoformat()
    assert [d["day"] for d in days] == sorted(d["day"] for d in days)

    submit(client, user, pid, SUM_PY)
    submit(client, user, pid, "print(0)")
    with client.session_factory() as db:  # an old submission outside the window, one 5 days ago
        db.add(Submission(user_id=uid, problem_id=pid, language="python", code="x", state="done",
                          created_at=datetime.now(timezone.utc) - timedelta(days=40)))
        db.add(Submission(user_id=uid, problem_id=pid, language="python", code="x", state="done",
                          created_at=datetime.now(timezone.utc) - timedelta(days=5)))
        db.commit()
    s = client.get("/admin/stats", headers=admin).json()
    assert s["submissions_total"] == 4
    days = {d["day"]: d["count"] for d in s["submissions_per_day"]}
    assert days[today.isoformat()] == 2
    assert days[(today - timedelta(days=5)).isoformat()] == 1
    assert sum(days.values()) == 3  # the 40-day-old one is outside the 30-day window


def test_most_and_least_solved(env):
    client, admin, user, _, _, p1 = env
    p2 = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    p3 = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    other = auth(register(client, "o@example.com")["access_token"])
    submit(client, user, p2, SUM_PY)
    submit(client, other, p2, SUM_PY)
    submit(client, user, p3, SUM_PY)
    submit(client, user, p1, "print(0)")  # attempted, not solved
    s = client.get("/admin/stats", headers=admin).json()
    assert [(x["problem_id"], x["solved"]) for x in s["most_solved"]] == [(p2, 2), (p3, 1), (p1, 0)]
    assert [(x["problem_id"], x["solved"]) for x in s["least_solved"]] == [(p1, 0), (p3, 1), (p2, 2)]
    assert s["most_solved"][0]["title"] == "Қосынды"


# ------------------------------------- rating correction -------------------------------------


def body(**over):
    b = {"scope": "global", "rating": 1500, "reason": "contest result fix"}
    b.update(over)
    return b


def test_rating_correction_global_tag_duel_and_audit(env):
    client, admin, user, aid, uid, pid = env
    submit(client, user, pid, SUM_PY)  # 1220
    r = client.post(f"/admin/users/{uid}/rating", json=body(), headers=admin)
    assert r.status_code == 200 and r.json() == {"old_rating": 1220.0, "new_rating": 1500.0}
    assert client.get("/rating/me", headers=user).json()["rating"] == 1500.0

    r = client.post(f"/admin/users/{uid}/rating", json=body(scope="tag", tag="math", rating=1300), headers=admin)
    assert r.json()["old_rating"] == 1220.0
    with client.session_factory() as db:
        assert db.get(TagRating, (uid, "math")).rating == 1300.0
    r = client.post(f"/admin/users/{uid}/rating", json=body(scope="duel", rating=1111), headers=admin)
    assert r.json() == {"old_rating": 1200.0, "new_rating": 1111.0}
    assert client.get("/duel/rating", headers=user).json()["rating"] == 1111.0

    rows = client.get("/admin/audit", headers=admin).json()["items"]
    top = rows[0]
    assert (top["action"], top["admin_id"], top["admin_name"], top["target_id"]) == ("rating.adjust", aid, "Admin", uid)
    assert top["details"] == {"scope": "duel", "tag": None, "old": 1200.0, "new": 1111.0, "reason": "contest result fix"}
    assert top["target_label"] == "user@example.com" and top["created_at"]
    assert [r["action"] for r in rows if r["action"] == "rating.adjust"] == ["rating.adjust"] * 3


@pytest.mark.parametrize(
    "over",
    [
        {"reason": ""},
        {"reason": "    "},
        {"reason": "abc"},
        {"reason": None},
        {"scope": "tag"},  # tag missing
        {"scope": "global", "tag": "math"},  # tag not allowed
        {"scope": "tag", "tag": "nope"},  # unknown tag
        {"scope": "weekly"},
        {"rating": -1},
        {"rating": 99999},
        {"rating": "high"},
    ],
)
def test_rating_correction_validation(env, over):
    client, admin, user, _, uid, pid = env
    submit(client, user, pid, SUM_PY)
    b = body(**over)
    r = client.post(f"/admin/users/{uid}/rating", json=b, headers=admin)
    assert r.status_code == 422, r.text
    assert client.get("/rating/me", headers=user).json()["rating"] == pytest.approx(1220.0)  # unchanged
    assert not [a for a in audit_rows(client) if a[0] == "rating.adjust"]  # nothing logged


def test_rating_correction_requires_reason_field_and_target(env):
    client, admin, _, _, uid, _ = env
    assert client.post(f"/admin/users/{uid}/rating", json={"scope": "global", "rating": 1500}, headers=admin).status_code == 422
    assert client.post("/admin/users/999/rating", json=body(), headers=admin).status_code == 404


# ------------------------------------------- audit ------------------------------------------


def test_audit_log_covers_content_actions_and_is_newest_first(env):
    client, admin, _, aid, uid, pid = env
    client.post("/tags", json={"slug": "newtag"}, headers=admin)
    p2 = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    client.put(f"/problems/{p2}", json=problem_payload(rating=1500), headers=admin)
    client.delete(f"/problems/{p2}", headers=admin)
    c = client.post("/collections", json={"title": "Warm-up", "description": "", "problem_ids": [pid]}, headers=admin)
    cid = c.json()["id"]
    client.put(f"/collections/{cid}", json={"title": "Warm-up 2", "description": "", "problem_ids": [pid]}, headers=admin)
    client.delete(f"/collections/{cid}", headers=admin)
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    items = client.get("/admin/audit", headers=admin).json()["items"]
    actions = [i["action"] for i in items]
    assert actions[0] == "user.block"
    assert actions[::-1] == [
        "problem.create", "tag.create", "problem.create", "problem.update", "problem.delete",
        "collection.create", "collection.update", "collection.delete", "user.block",
    ]
    assert all(i["admin_id"] == aid and i["created_at"] for i in items)
    assert [i["id"] for i in items] == sorted((i["id"] for i in items), reverse=True)


def test_failed_admin_calls_are_not_audited(env):
    client, admin, user, _, uid, pid = env
    before = len(audit_rows(client))
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=user)  # forbidden
    client.post("/tags", json={"slug": "math"}, headers=admin)  # duplicate -> 409
    client.delete("/problems/999", headers=admin)  # 404
    assert len(audit_rows(client)) == before


def test_audit_log_has_no_write_endpoints(env):
    client, admin, _, _, _, _ = env
    assert client.delete("/admin/audit", headers=admin).status_code == 405
    assert client.put("/admin/audit", json={}, headers=admin).status_code == 405
    assert client.patch("/admin/audit/1", json={}, headers=admin).status_code in (404, 405)


def test_audit_record_helper_stores_json(env):
    client, _, _, aid, _, _ = env
    with client.session_factory() as db:
        from app.modules.auth.models import User

        audit.record(db, db.get(User, aid), "x.y", "user", 5, "lbl", {"a": "қазақ"})
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert json.loads(row.details) == {"a": "қазақ"}
