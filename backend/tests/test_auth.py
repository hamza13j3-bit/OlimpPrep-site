from app.core.config import settings
from tests.conftest import auth, register


def test_first_user_is_admin_second_is_user(client):
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    assert a["user"]["role"] == "admin"
    assert b["user"]["role"] == "user"


def test_admin_email_from_env(client, monkeypatch):
    register(client, "first@example.com")  # first user is admin anyway
    monkeypatch.setattr(settings, "admin_email", "Boss@Example.com")
    boss = register(client, "boss@example.com")
    assert boss["user"]["role"] == "admin"
    assert register(client, "x@example.com")["user"]["role"] == "user"


def test_duplicate_email_case_insensitive(client):
    register(client, "a@example.com")
    r = client.post(
        "/auth/register", json={"email": "A@Example.com", "password": "password1", "name": "x"}
    )
    assert r.status_code == 409


def test_register_validation(client):
    bad = [
        {"email": "nope", "password": "password1", "name": "x"},
        {"email": "a@b.co", "password": "short", "name": "x"},
        {"email": "a@b.co", "password": "password1", "name": ""},
        {"email": "a@b.co", "password": "password1", "name": "x", "language": "fr"},
        {"email": "a@b.co", "password": "p" * 73, "name": "x"},
    ]
    for body in bad:
        assert client.post("/auth/register", json=body).status_code == 422, body


def test_password_is_hashed(client):
    from app.core.security import verify_password

    out = register(client)
    assert "password" not in out["user"]
    assert not verify_password("wrong-password", "not-a-hash")
    from app.core.security import hash_password

    h = hash_password("password1")
    assert h != "password1" and verify_password("password1", h)

def test_login_ok_and_wrong_password(client):
    register(client)
    ok = client.post("/auth/login", json={"email": "A@example.com", "password": "password1"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/auth/login", json={"email": "a@example.com", "password": "wrongpass1"})
    unknown = client.post("/auth/login", json={"email": "z@example.com", "password": "password1"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=auth("garbage")).status_code == 401
    t = register(client)["access_token"]
    assert client.get("/auth/me", headers=auth(t)).json()["email"] == "a@example.com"


def test_profile_update(client):
    t = register(client)["access_token"]
    r = client.patch(
        "/auth/me",
        json={"name": "Aigerim", "school_group": "10-B", "language": "ru"},
        headers=auth(t),
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["school_group"], r.json()["language"]) == (
        "Aigerim",
        "10-B",
        "ru",
    )
    assert client.patch("/auth/me", json={"language": "xx"}, headers=auth(t)).status_code == 422


def test_profile_cannot_change_role(client):
    register(client)
    t = register(client, "b@example.com")["access_token"]
    r = client.patch("/auth/me", json={"role": "admin", "is_blocked": False}, headers=auth(t))
    assert r.status_code == 200 and r.json()["role"] == "user"


def test_role_guard_admin_endpoints(client):
    admin = register(client, "a@example.com")["access_token"]
    user = register(client, "b@example.com")["access_token"]
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/users", headers=auth(user)).status_code == 403
    assert client.get("/admin/users", headers=auth(admin)).json()["total"] == 2
    # the old unaudited routes are gone
    assert client.get("/auth/users", headers=auth(admin)).status_code in (404, 405)


def test_blocked_user_cannot_login_or_act(client):
    admin = register(client, "a@example.com")["access_token"]
    b = register(client, "b@example.com")
    uid, tok = b["user"]["id"], b["access_token"]

    r = client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["is_blocked"] is True

    login = client.post("/auth/login", json={"email": "b@example.com", "password": "password1"})
    assert login.status_code == 403
    # existing token: can read /me, cannot write (get_active_user is the submit guard)
    assert client.get("/auth/me", headers=auth(tok)).json()["is_blocked"] is True
    assert client.patch("/auth/me", json={"name": "x"}, headers=auth(tok)).status_code == 403

    client.patch(f"/admin/users/{uid}/block", json={"blocked": False}, headers=auth(admin))
    assert (
        client.post("/auth/login", json={"email": "b@example.com", "password": "password1"})
    ).status_code == 200


def test_admin_cannot_block_self_or_missing(client):
    a = register(client)
    h = auth(a["access_token"])
    assert client.patch(f"/admin/users/{a['user']['id']}/block", json={"blocked": True}, headers=h).status_code == 400
    assert client.patch("/admin/users/999/block", json={"blocked": True}, headers=h).status_code == 404
