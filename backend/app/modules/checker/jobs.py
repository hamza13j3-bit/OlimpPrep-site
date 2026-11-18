"""In-process background queue (no Redis): a few worker threads draining a queue.Queue.

Jobs are persisted as `queued` submissions, so after a restart `recover()` re-enqueues them.
"""

import logging
import queue
import threading
from typing import Callable

from sqlalchemy.orm import Session

from app.modules.checker import service

log = logging.getLogger(__name__)

_STOP = object()


class CheckQueue:
    def __init__(self, session_factory: Callable[[], Session], workers: int = 2):
        self._factory = session_factory
        self._n = workers
        self._q: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for i in range(self._n):
            t = threading.Thread(target=self._work, name=f"checker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        for _ in self._threads:
            self._q.put(_STOP)
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()

    def submit(self, submission_id: int) -> None:
        self._q.put(submission_id)

    def join(self) -> None:
        """Block until every queued job has been processed (used by tests)."""
        self._q.join()

    def recover(self) -> None:
        with self._factory() as db:
            service.reset_interrupted(db)
            for sid in service.unfinished_ids(db):
                self.submit(sid)

    def _work(self) -> None:
        while True:
            item = self._q.get()
            try:
                if item is _STOP:
                    return
                with self._factory() as db:
                    service.process_submission(db, item)
            except Exception:
                log.exception("worker failed on %r", item)
            finally:
                self._q.task_done()
