import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import Base, SessionLocal, engine
from app.modules.admin import models as _admin_models  # noqa: F401
from app.modules.admin.router import router as admin_router
from app.modules.archive import models as _archive_models  # noqa: F401
from app.modules.archive.router import collections_router
from app.modules.archive.router import router as archive_router
from app.modules.auth import models as _auth_models  # noqa: F401  (register tables)
from app.modules.auth.router import router as auth_router
from app.modules.checker import models as _checker_models  # noqa: F401
from app.modules.checker.jobs import CheckQueue
from app.modules.checker.router import router as checker_router
from app.modules.duel import models as _duel_models  # noqa: F401
from app.modules.duel import service as duel_service
from app.modules.duel import supervisor as duel_supervisor
from app.modules.duel.router import router as duel_router
from app.modules.problems import models as _problem_models  # noqa: F401
from app.modules.problems import service as problems_service
from app.modules.problems.router import router as problems_router
from app.modules.rating import models as _rating_models  # noqa: F401
from app.modules.rating.router import router as rating_router
from app.modules.stats import models as _stats_models  # noqa: F401
from app.modules.stats import service as stats_service
from app.modules.stats.leaderboard_router import router as leaderboard_router
from app.modules.stats.router import router as stats_router

duel_service.register()  # the checker tells the duel module about finished duel submissions
stats_service.register()  # ... and the stats module (retry-later schedule)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        problems_service.ensure_default_tags(db)
    queue = CheckQueue(SessionLocal, workers=2)
    queue.start()
    queue.recover()  # re-enqueue submissions interrupted by a restart
    app.state.check_queue = queue

    stop = asyncio.Event()  # server-side duel timers: matchmaking, deadlines, reconnect grace
    supervisor = asyncio.create_task(duel_supervisor.run(SessionLocal, stop))
    yield
    stop.set()
    await supervisor
    queue.stop()


app = FastAPI(title="OlimpPrep", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(problems_router)
app.include_router(checker_router)
app.include_router(rating_router)
app.include_router(archive_router)
app.include_router(collections_router)
app.include_router(duel_router)
app.include_router(stats_router)
app.include_router(leaderboard_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok"}
