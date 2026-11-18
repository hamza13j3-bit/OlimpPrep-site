from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.admin import audit
from app.modules.archive import package, service
from app.modules.archive.schemas import (
    ArchivePage,
    CollectionBrief,
    CollectionDetail,
    CollectionIn,
    ImportOut,
    PackageErrorOut,
)
from app.modules.auth.deps import get_optional_user, require_admin
from app.modules.auth.models import User
from app.modules.problems import service as problems_service

router = APIRouter(prefix="/archive", tags=["archive"])
collections_router = APIRouter(prefix="/collections", tags=["collections"])

Lang = Literal["kk", "ru", "en"]


def _split(values: list[str]) -> list[str]:
    """?tags=dp&tags=graphs and ?tags=dp,graphs are both accepted."""
    out: list[str] = []
    for v in values:
        out.extend(p.strip() for p in v.split(",") if p.strip())
    return list(dict.fromkeys(out))


@router.get("/problems", response_model=ArchivePage)
def archive_problems(
    tags: list[str] = Query(default_factory=list),
    rating_min: int | None = None,
    rating_max: int | None = None,
    status_: Literal["solved", "attempted", "unsolved"] | None = Query(None, alias="status"),
    source: str | None = Query(None, max_length=200),
    year: int | None = None,
    lang: Lang | None = None,
    q: str | None = Query(None, max_length=200),
    sort: Literal["number", "rating", "solved", "newest"] = "number",
    order: Literal["asc", "desc"] | None = None,
    page: int = Query(1, ge=1, le=100_000),
    ui_lang: Lang = "kk",
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    f = service.Filters(
        tags=_split(tags), rating_min=rating_min, rating_max=rating_max, status=status_,
        source=source, year=year, lang=lang, q=q,
    )
    return service.list_problems(db, user, f, sort, order, page, ui_lang)


@router.post("/import", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
def import_package(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = file.file.read(package.MAX_ZIP_BYTES + 1)
    if len(data) > package.MAX_ZIP_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ZIP is larger than 20 MB")
    problem, errors = package.parse_package(data)
    if problem is None:
        body = [PackageErrorOut(file=e.file, message=e.message).model_dump() for e in errors]
        return JSONResponse({"errors": body}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        created = problems_service.create_problem(db, problem)
    except problems_service.UnknownTags as e:
        err = [{"file": "problem.json", "message": f"Unknown tags: {', '.join(e.slugs)}"}]
        return JSONResponse({"errors": err}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    audit.record(db, admin, "problem.import", "problem", created.id)
    return {"problem_id": created.id, "number": created.id}


@router.get("/problems/{problem_id}/export")
def export_package(problem_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = problems_service.get_problem(db, problem_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
    data = package.build_package(problems_service.admin_view(p))
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="problem-{problem_id}.zip"'},
    )


# ---- collections ----------------------------------------------------------------


def _collection_or_404(db: Session, collection_id: int):
    c = service.get_collection(db, collection_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    return c


def _detail(db: Session, c, user: User | None, ui_lang: str) -> dict:
    return service.collection_detail(db, c, user, ui_lang)


@collections_router.get("", response_model=list[CollectionBrief])
def list_collections(db: Session = Depends(get_db)):
    return service.list_collections(db)


@collections_router.get("/{collection_id}", response_model=CollectionDetail)
def read_collection(
    collection_id: int,
    ui_lang: Lang = "kk",
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    return _detail(db, _collection_or_404(db, collection_id), user, ui_lang)


def _write(db: Session, fn, *args):
    try:
        return fn(db, *args)
    except service.CollectionExists:
        raise HTTPException(status.HTTP_409_CONFLICT, "A collection with this title exists") from None
    except service.UnknownProblems as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None


@collections_router.post("", response_model=CollectionDetail, status_code=status.HTTP_201_CREATED)
def create_collection(data: CollectionIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = _write(db, service.create_collection, data.title, data.description, data.problem_ids)
    audit.record(db, admin, "collection.create", "collection", c.id, data.title)
    return _detail(db, c, admin, "kk")


@collections_router.put("/{collection_id}", response_model=CollectionDetail)
def update_collection(
    collection_id: int, data: CollectionIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    c = _collection_or_404(db, collection_id)
    c = _write(db, service.update_collection, c, data.title, data.description, data.problem_ids)
    audit.record(db, admin, "collection.update", "collection", c.id, data.title)
    return _detail(db, c, admin, "kk")


@collections_router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = _collection_or_404(db, collection_id)
    title = c.title
    service.delete_collection(db, c)
    audit.record(db, admin, "collection.delete", "collection", collection_id, title)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
