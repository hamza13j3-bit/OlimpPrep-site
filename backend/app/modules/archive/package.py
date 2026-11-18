"""Problem package (ZIP) parsing and building. Pure functions, no database.

Layout (all paths relative, UTF-8):
    problem.json              metadata, subtasks (points + test ids), examples, titles
    statements/<lang>.md      statement per language (kk | ru | en), Markdown + LaTeX
    tests/NN.in, tests/NN.out test input / expected output (NN = 2-4 digits)
    hints/<level>.<lang>.md   hint level 1..3 per language (optional)

Nothing is ever extracted to disk (files are read in memory), and any unsafe path
(zip-slip) rejects the whole package. All problems found are reported at once.
"""

import io
import json
import re
import zipfile
import zlib
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.problems.schemas import (
    HintIn,
    ProblemIn,
    SubtaskIn,
    TestIn,
    TranslationIn,
)

MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_TEST_BYTES = 5 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_TEXT_BYTES = 400 * 1024  # statements; hints are far smaller
MAX_ENTRIES = 2000
MAX_TOTAL_BYTES = 100 * 1024 * 1024

Lang = Literal["kk", "ru", "en"]

_STATEMENT = re.compile(r"^statements/(kk|ru|en)\.md$")
_TEST = re.compile(r"^tests/([0-9]{2,4})\.(in|out)$")
_HINT = re.compile(r"^hints/([123])\.(kk|ru|en)\.md$")
_DIRS = {"tests", "statements", "hints"}
_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class PackageError:
    file: str
    message: str


class PackageTitle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class PackageSubtask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: int = Field(ge=1, le=1000)
    tests: list[str] = Field(min_length=1, max_length=200)


class PackageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal[1] = 1
    rating: int = Field(default=1200, ge=100, le=4000)
    time_limit_ms: int = Field(default=1000, ge=100, le=10_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=1024)
    source: str = Field(default="", max_length=200)
    year: int | None = Field(default=None, ge=1990, le=2100)
    author: str = Field(default="", max_length=200)
    hide_tags_until_solved: bool = False
    tags: list[str] = Field(default_factory=list, max_length=20)
    translations: dict[Lang, PackageTitle] = Field(min_length=1)
    subtasks: list[PackageSubtask] = Field(min_length=1, max_length=50)
    examples: list[str] = Field(default_factory=list)


def is_unsafe_name(name: str) -> bool:
    """Absolute paths, drive letters, backslashes, NULs and '..' / empty / '.' components."""
    if not name or "\\" in name or "\x00" in name or name.startswith("/") or _DRIVE.match(name):
        return True
    return any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def _read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int, errors: list[PackageError]) -> bytes | None:
    try:
        with zf.open(info) as f:
            data = f.read(limit + 1)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError):
        errors.append(PackageError(info.filename, "Cannot read file (corrupt or unsupported compression)"))
        return None
    if len(data) > limit:
        errors.append(PackageError(info.filename, f"File is larger than {limit // 1024} KB"))
        return None
    return data


def _text(data: bytes, name: str, errors: list[PackageError], *, bom_ok: bool) -> str | None:
    try:
        return data.decode("utf-8-sig" if bom_ok else "utf-8")
    except UnicodeDecodeError:
        errors.append(PackageError(name, "File is not valid UTF-8"))
        return None


def parse_package(data: bytes) -> tuple[ProblemIn | None, list[PackageError]]:
    """Returns (problem, []) on success or (None, errors) listing every problem found."""
    errors: list[PackageError] = []
    if len(data) > MAX_ZIP_BYTES:
        return None, [PackageError("(archive)", "ZIP is larger than 20 MB")]
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None, [PackageError("(archive)", "Not a valid ZIP file")]

    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        return None, [PackageError("(archive)", f"Too many entries (max {MAX_ENTRIES})")]
    if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
        return None, [PackageError("(archive)", "Unpacked size is larger than 100 MB")]

    seen: set[str] = set()
    problem_json: bytes | None = None
    statements: dict[str, str] = {}
    tests: dict[str, dict[str, str]] = {}
    hints: dict[tuple[int, str], str] = {}

    for info in infos:
        name = info.filename
        if is_unsafe_name(name):
            errors.append(PackageError(name, "Unsafe path (absolute or contains '..'): package rejected"))
            continue
        if name in seen:
            errors.append(PackageError(name, "Duplicate entry in ZIP"))
            continue
        seen.add(name)
        if name.endswith("/"):
            if name.rstrip("/") not in _DIRS:
                errors.append(PackageError(name, "Unexpected directory"))
            continue
        if _is_symlink(info):
            errors.append(PackageError(name, "Symbolic links are not allowed"))
            continue
        if info.flag_bits & 0x1:
            errors.append(PackageError(name, "Encrypted files are not allowed"))
            continue

        if name == "problem.json":
            problem_json = _read(zf, info, MAX_JSON_BYTES, errors)
        elif m := _STATEMENT.match(name):
            raw = _read(zf, info, MAX_TEXT_BYTES, errors)
            if raw is not None and (txt := _text(raw, name, errors, bom_ok=True)) is not None:
                statements[m.group(1)] = txt
        elif m := _TEST.match(name):
            raw = _read(zf, info, MAX_TEST_BYTES, errors)
            if raw is not None and (txt := _text(raw, name, errors, bom_ok=False)) is not None:
                tests.setdefault(m.group(1), {})[m.group(2)] = txt
        elif m := _HINT.match(name):
            raw = _read(zf, info, 16 * 1024, errors)
            if raw is not None and (txt := _text(raw, name, errors, bom_ok=True)) is not None:
                hints[(int(m.group(1)), m.group(2))] = txt.strip()
        else:
            errors.append(PackageError(name, "Unexpected file"))

    # Files that exist but could not be used already have their own error; do not also
    # report them as "missing".
    broken = {e.file for e in errors}
    meta = _parse_meta(problem_json, errors)
    if meta is not None:
        _cross_check(meta, statements, tests, errors, broken)
    if errors or meta is None:
        return None, errors

    examples = set(meta.examples)
    try:
        problem = ProblemIn(
            rating=meta.rating,
            time_limit_ms=meta.time_limit_ms,
            memory_limit_mb=meta.memory_limit_mb,
            source=meta.source,
            year=meta.year,
            author=meta.author,
            hide_tags_until_solved=meta.hide_tags_until_solved,
            tags=meta.tags,
            translations={
                lang: TranslationIn(title=t.title, statement=statements[lang])
                for lang, t in meta.translations.items()
            },
            subtasks=[
                SubtaskIn(
                    points=st.points,
                    tests=[
                        TestIn(input=tests[s]["in"], output=tests[s]["out"], is_example=s in examples)
                        for s in st.tests
                    ],
                )
                for st in meta.subtasks
            ],
            hints=[HintIn(level=lv, lang=lang, text=txt) for (lv, lang), txt in sorted(hints.items()) if txt],
        )
    except ValidationError as e:
        return None, [PackageError("problem.json", _fmt(err)) for err in e.errors()]
    return problem, []


def _fmt(err: dict) -> str:
    loc = ".".join(str(x) for x in err["loc"])
    return f"{loc}: {err['msg']}" if loc else err["msg"]


def _parse_meta(raw: bytes | None, errors: list[PackageError]) -> PackageMeta | None:
    if raw is None:
        if not any(e.file == "problem.json" for e in errors):
            errors.append(PackageError("problem.json", "Missing required file"))
        return None
    text = _text(raw, "problem.json", errors, bom_ok=True)
    if text is None:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append(PackageError("problem.json", f"Invalid JSON: {e.msg} (line {e.lineno})"))
        return None
    if not isinstance(obj, dict):
        errors.append(PackageError("problem.json", "Must be a JSON object"))
        return None
    try:
        return PackageMeta.model_validate(obj)
    except ValidationError as e:
        errors.extend(PackageError("problem.json", _fmt(err)) for err in e.errors())
        return None


def _cross_check(
    meta: PackageMeta,
    statements: dict[str, str],
    tests: dict[str, dict[str, str]],
    errors: list[PackageError],
    broken: set[str],
) -> None:
    for lang in meta.translations:
        if lang not in statements and f"statements/{lang}.md" not in broken:
            errors.append(PackageError(f"statements/{lang}.md", "Missing (declared in problem.json translations)"))
    for lang in statements:
        if lang not in meta.translations:
            errors.append(PackageError(f"statements/{lang}.md", "Not declared in problem.json translations"))
        elif not statements[lang].strip():
            errors.append(PackageError(f"statements/{lang}.md", "Statement is empty"))

    referenced: dict[str, int] = {}
    for st in meta.subtasks:
        for stem in st.tests:
            referenced[stem] = referenced.get(stem, 0) + 1
    for stem, n in sorted(referenced.items()):
        if n > 1:
            errors.append(PackageError("problem.json", f"Test '{stem}' is listed more than once"))
        parts = tests.get(stem, {})
        for ext in ("in", "out"):
            if ext not in parts and f"tests/{stem}.{ext}" not in broken:
                errors.append(PackageError(f"tests/{stem}.{ext}", "Missing (listed in problem.json subtasks)"))
    for stem, parts in sorted(tests.items()):
        if stem not in referenced:
            for ext in sorted(parts):
                errors.append(PackageError(f"tests/{stem}.{ext}", "Not used by any subtask"))
        elif len(parts) == 1:
            pass  # the missing half was reported above
    for stem in meta.examples:
        if stem not in referenced:
            errors.append(PackageError("problem.json", f"Example '{stem}' is not a test of any subtask"))


# ---- export -------------------------------------------------------------------


def build_package(view: dict) -> bytes:
    """`view` is problems.service.admin_view(problem). Returns ZIP bytes."""
    buf = io.BytesIO()
    n_tests = sum(len(st["tests"]) for st in view["subtasks"])
    width = max(2, len(str(n_tests)))
    counter = 0
    subtasks_meta, examples = [], []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for st in view["subtasks"]:
            stems = []
            for t in st["tests"]:
                counter += 1
                stem = str(counter).zfill(width)
                stems.append(stem)
                zf.writestr(f"tests/{stem}.in", t["input"].encode("utf-8"))
                zf.writestr(f"tests/{stem}.out", t["output"].encode("utf-8"))
                if t["is_example"]:
                    examples.append(stem)
            subtasks_meta.append({"points": st["points"], "tests": stems})
        for lang, tr in view["translations"].items():
            zf.writestr(f"statements/{lang}.md", tr["statement"].encode("utf-8"))
        for h in view["hints"]:
            zf.writestr(f"hints/{h['level']}.{h['lang']}.md", h["text"].encode("utf-8"))
        meta = {
            "format_version": 1,
            "rating": view["rating"],
            "time_limit_ms": view["time_limit_ms"],
            "memory_limit_mb": view["memory_limit_mb"],
            "source": view["source"],
            "year": view["year"],
            "author": view["author"],
            "hide_tags_until_solved": view["hide_tags_until_solved"],
            "tags": view["tags"],
            "translations": {lang: {"title": tr["title"]} for lang, tr in view["translations"].items()},
            "subtasks": subtasks_meta,
            "examples": examples,
        }
        zf.writestr("problem.json", json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))
    return buf.getvalue()
