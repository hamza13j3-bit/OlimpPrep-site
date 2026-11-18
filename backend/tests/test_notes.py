import pytest

from app.main import app
from app.modules.checker.router import get_queue
from tests.conftest import NOTE_TEXT, auth, note_body, register, write_note
from tests.test_rating import SUM_PY, SyncQueue, problem_payload


@pytest.fixture()
def env(client):
    from app.modules.problems import service as ps

    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    app.dependency_overrides[get_queue] = lambda: SyncQueue(client.session_factory)
    admin = auth(register(client, "admin@example.com")["access_token"])
    user = register(client, "user@example.com")
    pid = client.post("/problems", json=problem_payload(), headers=admin).json()["id"]
    return client, admin, auth(user["access_token"]), user["user"]["id"], pid


def put(client, headers, pid, **over):
    return client.put(f"/problems/{pid}/note", json=note_body(**over), headers=headers)


def raw_submit(client, headers, pid):
    return client.post(
        "/submissions", json={"problem_id": pid, "language": "python", "code": SUM_PY}, headers=headers
    )


def test_no_note_yet(env):
    client, _, user, _, pid = env
    r = client.get(f"/problems/{pid}/note", headers=user)
    assert r.status_code == 200 and r.json() is None


def test_note_needs_30_words(env):
    client, _, user, _, pid = env
    assert put(client, user, pid, text=" ".join(["w"] * 29)).status_code == 422
    assert put(client, user, pid, text=("w \n\t " * 29) + "   ").status_code == 422  # whitespace is not a word
    assert put(client, user, pid, text="").status_code == 422
    assert client.get(f"/problems/{pid}/note", headers=user).json() is None  # nothing stored
    assert put(client, user, pid, text=" ".join(["w"] * 30)).status_code == 200


@pytest.mark.parametrize(
    "item", ["read_constraints", "named_algorithm", "estimated_complexity", "listed_edge_cases"]
)
def test_every_checklist_item_is_required(env, item):
    client, _, user, _, pid = env
    assert put(client, user, pid, **{item: False}).status_code == 422
    body = note_body()
    del body[item]
    assert client.put(f"/problems/{pid}/note", json=body, headers=user).status_code == 422
    assert client.get(f"/problems/{pid}/note", headers=user).json() is None


def test_note_roundtrip_and_update(env):
    client, _, user, _, pid = env
    r = put(client, user, pid)
    assert r.status_code == 200
    got = client.get(f"/problems/{pid}/note", headers=user).json()
    assert got["text"] == NOTE_TEXT and got["listed_edge_cases"] is True
    put(client, user, pid, text="new " * 30)
    assert client.get(f"/problems/{pid}/note", headers=user).json()["text"] == ("new " * 30).strip()
    from app.modules.problems.models import IdeaNote

    with client.session_factory() as db:
        assert db.query(IdeaNote).count() == 1  # one per user and problem


def test_note_endpoint_errors(env):
    client, admin, user, uid, pid = env
    assert client.get(f"/problems/{pid}/note").status_code == 401
    assert client.put(f"/problems/{pid}/note", json=note_body()).status_code == 401
    assert put(client, user, 999).status_code == 404
    assert client.get("/problems/999/note", headers=user).status_code == 404
    client.patch(f"/admin/users/{uid}/block", json={"blocked": True}, headers=admin)
    assert put(client, user, pid).status_code == 403


def test_submitting_does_not_need_an_idea_note(env):
    # the note is optional now: the editor is open at once and POST /submissions never asks for it
    client, admin, user, _, pid = env
    r = raw_submit(client, user, pid)
    assert r.status_code == 202
    assert client.get(f"/submissions/{r.json()['id']}", headers=user).json()["solved"] is True
    assert client.get(f"/problems/{pid}/note", headers=user).json() is None

def test_notes_are_private_but_admin_can_read_them(env):
    client, admin, user, uid, pid = env
    stranger = auth(register(client, "s@example.com")["access_token"])
    write_note(client, user, pid)
    # nobody can read another user's note through the personal endpoint
    assert client.get(f"/problems/{pid}/note", headers=stranger).json() is None
    assert client.get(f"/problems/{pid}/note", headers=admin).json() is None
    # moderation list: admins only
    assert client.get(f"/problems/{pid}/notes").status_code == 401
    assert client.get(f"/problems/{pid}/notes", headers=stranger).status_code == 403
    rows = client.get(f"/problems/{pid}/notes", headers=admin).json()
    assert [(r["user_id"], r["text"]) for r in rows] == [(uid, NOTE_TEXT)]
    # read-only: the admin cannot overwrite the user's note (the PUT only touches the caller's own)
    put(client, admin, pid, text="admin " * 30)
    assert client.get(f"/problems/{pid}/note", headers=user).json()["text"] == NOTE_TEXT


def test_public_problem_never_contains_notes(env):
    client, _, user, _, pid = env
    write_note(client, user, pid)
    assert NOTE_TEXT not in client.get(f"/problems/{pid}", headers=user).text
    assert NOTE_TEXT not in client.get(f"/archive/problems", headers=user).text
