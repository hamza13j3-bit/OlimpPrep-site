import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from app.modules.archive import package
from app.modules.problems import service as ps
from tests.conftest import auth, register

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "docs" / "sample-package"

META = {
    "format_version": 1,
    "rating": 1000,
    "tags": ["math"],
    "translations": {"kk": {"title": "Қосынды"}},
    "subtasks": [{"points": 40, "tests": ["01", "02"]}, {"points": 60, "tests": ["03"]}],
    "examples": ["01"],
}
FILES = {
    "problem.json": json.dumps(META),
    "statements/kk.md": "$a+b$ табыңыз",
    "tests/01.in": "1 2\n", "tests/01.out": "3\n",
    "tests/02.in": "2 2\n", "tests/02.out": "4\n",
    "tests/03.in": "5 5\n", "tests/03.out": "10\n",
    "hints/1.kk.md": "бағыт",
}


def make_zip(files=None, *, meta=None, drop=(), extra=None) -> bytes:
    files = dict(FILES if files is None else files)
    if meta is not None:
        files["problem.json"] = json.dumps(meta)
    for name in drop:
        files.pop(name)
    files.update(extra or {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content if isinstance(content, bytes) else content.encode("utf-8"))
    return buf.getvalue()


def errs(data: bytes) -> dict[str, str]:
    problem, errors = package.parse_package(data)
    assert problem is None and errors, "expected the package to be rejected"
    return {e.file: e.message for e in errors}


# ---------------------------------- pure parsing ----------------------------------


def test_valid_package_parses():
    problem, errors = package.parse_package(make_zip())
    assert errors == [] and problem is not None
    assert problem.rating == 1000 and problem.tags == ["math"]
    assert [s.points for s in problem.subtasks] == [40, 60]
    assert [t.input for t in problem.subtasks[0].tests] == ["1 2\n", "2 2\n"]
    assert [t.is_example for st in problem.subtasks for t in st.tests] == [True, False, False]
    assert problem.translations["kk"].statement == "$a+b$ табыңыз"
    assert [(h.level, h.lang, h.text) for h in problem.hints] == [(1, "kk", "бағыт")]


def test_sample_package_in_docs_is_valid():
    zipped = SAMPLE_DIR / "sample-package.zip"
    problem, errors = package.parse_package(zipped.read_bytes())
    assert errors == [] and problem is not None
    assert set(problem.translations) == {"kk", "en"} and len(problem.hints) == 3
    assert sum(s.points for s in problem.subtasks) == 100


def test_sample_folder_matches_zip():
    # the committed zip must contain exactly the folder's package files
    on_disk = {
        p.relative_to(SAMPLE_DIR).as_posix()
        for p in SAMPLE_DIR.rglob("*")
        if p.is_file() and p.suffix != ".zip" and p.name not in ("make_zip.py", "README.md")
    }
    assert on_disk == set(zipfile.ZipFile(SAMPLE_DIR / "sample-package.zip").namelist())


def test_not_a_zip_and_empty():
    assert "Not a valid ZIP" in errs(b"this is not a zip")["(archive)"]
    assert "Not a valid ZIP" in errs(b"")["(archive)"]


def test_missing_problem_json():
    assert "Missing" in errs(make_zip(drop=["problem.json"]))["problem.json"]


def test_malformed_json():
    e = errs(make_zip(extra={"problem.json": "{not json"}))
    assert "Invalid JSON" in e["problem.json"]
    assert "JSON object" in errs(make_zip(extra={"problem.json": "[1]"}))["problem.json"]


def test_metadata_validation_errors_are_per_field():
    bad = {**META, "rating": 5, "bogus": 1, "subtasks": []}
    messages = [e.message for e in package.parse_package(make_zip(meta=bad))[1]]
    assert any(m.startswith("rating") for m in messages)
    assert any(m.startswith("bogus") for m in messages)  # unknown keys are rejected
    assert any(m.startswith("subtasks") for m in messages)


def test_missing_test_files_and_unused_ones():
    e = errs(make_zip(drop=["tests/02.out"]))
    assert "Missing" in e["tests/02.out"]
    e = errs(make_zip(extra={"tests/09.in": "x", "tests/09.out": "y"}))
    assert "Not used" in e["tests/09.in"] and "Not used" in e["tests/09.out"]


def test_statement_problems():
    assert "Missing" in errs(make_zip(drop=["statements/kk.md"]))["statements/kk.md"]
    assert "Not declared" in errs(make_zip(extra={"statements/ru.md": "x"}))["statements/ru.md"]
    assert "empty" in errs(make_zip(extra={"statements/kk.md": "  \n"}))["statements/kk.md"]


def test_unexpected_files_and_dirs():
    e = errs(make_zip(extra={"notes.txt": "hi", "tests/readme.md": "x", "hints/4.kk.md": "x", "tests/1.in": "x"}))
    for name in ("notes.txt", "tests/readme.md", "hints/4.kk.md", "tests/1.in"):
        assert "Unexpected" in e[name], name


def test_reports_every_problem_at_once():
    data = make_zip(drop=["tests/02.out", "statements/kk.md"], extra={"junk.bin": "x", "tests/03.in": b"\xff\xfe"})
    e = errs(data)
    assert {"tests/02.out", "statements/kk.md", "junk.bin", "tests/03.in"} <= set(e)
    assert "UTF-8" in e["tests/03.in"]


def test_unknown_example_and_duplicate_test_reference():
    meta = {**META, "examples": ["77"]}
    assert "Example '77'" in errs(make_zip(meta=meta))["problem.json"]
    meta = {**META, "subtasks": [{"points": 50, "tests": ["01", "02"]}, {"points": 50, "tests": ["02", "03"]}]}
    assert "more than once" in errs(make_zip(meta=meta))["problem.json"]


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "tests/../../evil.txt", "/etc/passwd", "C:/Windows/x.txt", "tests/../problem.json",
     "./problem.json", "tests//01.in"],
)
def test_zip_slip_names_are_rejected(name):
    data = make_zip(extra={name: "pwned"})
    problem, errors = package.parse_package(data)
    assert problem is None
    assert any("Unsafe path" in e.message for e in errors), errors


def test_nul_in_name_is_rejected():
    # zipfile cuts names at NUL, so this arrives as an unexpected file; either way it fails
    problem, errors = package.parse_package(make_zip(extra={"tests/01.in\x00../../x": "pwned"}))
    assert problem is None and errors
    assert package.is_unsafe_name("a\x00b")


def test_backslash_names_are_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in FILES.items():
            zf.writestr(name, content)
        info = zipfile.ZipInfo("x")
        info.filename = "..\\..\\evil.txt"  # bypass the constructor's separator normalisation
        zf.writestr(info, "pwned")
    problem, errors = package.parse_package(buf.getvalue())
    assert problem is None and any("Unsafe path" in e.message or "Unexpected" in e.message for e in errors)


def test_zip_slip_never_writes_anything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    package.parse_package(make_zip(extra={"../escape.txt": "x", "tests/../../escape2.txt": "x"}))
    assert not list(tmp_path.rglob("*")) and not (tmp_path.parent / "escape.txt").exists()


def test_symlink_and_duplicate_and_encrypted_entries():
    buf = io.BytesIO()
    with pytest.warns(UserWarning):  # zipfile itself warns about the duplicate name
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in FILES.items():
                zf.writestr(name, content)
            link = zipfile.ZipInfo("tests/05.in")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(link, "/etc/passwd")
            zf.writestr("tests/01.in", "dup")  # duplicate entry: we must reject it
    e = errs(buf.getvalue())
    assert "Symbolic" in e["tests/05.in"] and "Duplicate" in e["tests/01.in"]

    enc = io.BytesIO()
    with zipfile.ZipFile(enc, "w") as zf:
        zf.writestr("problem.json", json.dumps(META))
    raw = bytearray(enc.getvalue())
    # set the "encrypted" general-purpose bit in both headers
    raw[6] |= 1
    cd = raw.find(b"PK\x01\x02")
    raw[cd + 8] |= 1
    assert "Encrypted" in errs(bytes(raw))["problem.json"]


def test_size_limits():
    big = "1" * (package.MAX_TEST_BYTES + 1)
    e = errs(make_zip(extra={"tests/01.in": big}))
    assert "larger than" in e["tests/01.in"]
    ok = "1" * package.MAX_TEST_BYTES  # exactly 5 MB is fine
    problem, errors = package.parse_package(make_zip(extra={"tests/01.in": ok}))
    assert errors == [] and len(problem.subtasks[0].tests[0].input) == package.MAX_TEST_BYTES
    assert "20 MB" in errs(b"0" * (package.MAX_ZIP_BYTES + 1))["(archive)"]


def test_total_unpacked_limit_and_entry_limit():
    files = {f"tests/{i:04d}.in": "x" for i in range(package.MAX_ENTRIES + 1)}
    assert "Too many entries" in errs(make_zip(files))["(archive)"]


# --------------------------------------- API ---------------------------------------


@pytest.fixture()
def env(client):
    with client.session_factory() as db:
        ps.ensure_default_tags(db)
    admin = auth(register(client, "admin@example.com")["access_token"])
    user = auth(register(client, "user@example.com")["access_token"])
    return client, admin, user


def upload(client, data, headers=None, name="p.zip"):
    return client.post("/archive/import", files={"file": (name, data, "application/zip")}, headers=headers or {})


def test_import_roles(env):
    client, admin, user = env
    assert upload(client, make_zip()).status_code == 401
    assert upload(client, make_zip(), user).status_code == 403
    assert client.get("/archive/problems/1/export", headers=user).status_code == 403
    assert client.get("/archive/problems/1/export").status_code == 401


def test_import_valid_creates_problem(env):
    client, admin, _ = env
    r = upload(client, make_zip(), admin)
    assert r.status_code == 201, r.text
    pid = r.json()["problem_id"]
    view = client.get(f"/problems/{pid}/admin", headers=admin).json()
    assert view["rating"] == 1000 and view["tags"] == ["math"]
    assert [s["points"] for s in view["subtasks"]] == [40, 60]
    assert client.get(f"/problems/{pid}").json()["examples"] == [{"input": "1 2\n", "output": "3\n"}]


def test_import_malformed_creates_nothing_and_reports_files(env):
    client, admin, _ = env
    r = upload(client, make_zip(drop=["tests/02.out", "statements/kk.md"]), admin)
    assert r.status_code == 422
    errors = r.json()["errors"]
    assert {e["file"] for e in errors} >= {"tests/02.out", "statements/kk.md"}
    assert all(set(e) == {"file", "message"} for e in errors)
    assert client.get("/archive/problems").json()["total"] == 0


def test_import_zip_slip_via_api(env):
    client, admin, _ = env
    r = upload(client, make_zip(extra={"../../evil.py": "import os"}), admin)
    assert r.status_code == 422
    assert any("Unsafe path" in e["message"] for e in r.json()["errors"])
    assert client.get("/archive/problems").json()["total"] == 0


def test_import_unknown_tag_and_not_a_zip(env):
    client, admin, _ = env
    r = upload(client, make_zip(meta={**META, "tags": ["nope"]}), admin)
    assert r.status_code == 422 and "nope" in r.json()["errors"][0]["message"]
    r = upload(client, b"garbage", admin)
    assert r.status_code == 422 and r.json()["errors"][0]["file"] == "(archive)"
    assert client.get("/archive/problems").json()["total"] == 0


def test_import_too_large_is_413(env, monkeypatch):
    client, admin, _ = env
    monkeypatch.setattr(package, "MAX_ZIP_BYTES", 1000)
    r = upload(client, b"0" * 1001, admin)
    assert r.status_code == 413


def test_export_import_round_trip(env):
    client, admin, _ = env
    body = {
        "rating": 1700, "time_limit_ms": 2000, "memory_limit_mb": 128, "source": "Src", "year": 2025,
        "author": "Автор", "hide_tags_until_solved": True, "tags": ["dp", "strings"],
        "translations": {"kk": {"title": "Қазақша", "statement": "$x$ \n\n**Кіріс.**"},
                         "en": {"title": "English", "statement": "text"}},
        "subtasks": [{"points": 30, "tests": [{"input": "a\n", "output": "1\n", "is_example": True},
                                               {"input": "b\r\n", "output": "2\n"}]},
                     {"points": 70, "tests": [{"input": "ж\n", "output": "3\n"}]}],
        "hints": [{"level": 1, "lang": "kk", "text": "h1"}, {"level": 3, "lang": "en", "text": "h3"}],
    }
    pid = client.post("/problems", json=body, headers=admin).json()["id"]
    r = client.get(f"/archive/problems/{pid}/export", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f"problem-{pid}.zip" in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "problem.json" in names and "tests/01.in" in names and "tests/03.out" in names
    assert all(not package.is_unsafe_name(n) for n in names)

    imported = upload(client, r.content, admin)
    assert imported.status_code == 201, imported.text
    a = client.get(f"/problems/{pid}/admin", headers=admin).json()
    b = client.get(f"/problems/{imported.json()['problem_id']}/admin", headers=admin).json()
    for view in (a, b):
        view.pop("id"), view.pop("number")
        for st in view["subtasks"]:
            st.pop("id")
    assert a == b  # lossless, incl. CRLF in a test, Cyrillic, hints, examples
    assert client.get("/archive/problems/999/export", headers=admin).status_code == 404


def test_import_sample_package_via_api(env):
    client, admin, _ = env
    data = (SAMPLE_DIR / "sample-package.zip").read_bytes()
    r = upload(client, data, admin)
    assert r.status_code == 201, r.text
    page = client.get("/archive/problems?q=sum").json()  # English title is searchable too
    assert page["total"] == 1
