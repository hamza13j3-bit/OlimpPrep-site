"""Server-side timers: one background task, one step per second.

Each step runs matchmaking and the deadline / reconnect-grace checks. Clients only display
the countdown; nothing a client sends can start, extend or end a match.
"""

import asyncio
import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.modules.duel import service

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 1.0


def step(factory: Callable[[], Session]) -> service.TickResult:
    with factory() as db:
        return service.tick(db, service.now())


def recover(factory: Callable[[], Session]) -> None:
    with factory() as db:
        service.recover(db, service.now())


async def run(factory: Callable[[], Session], stop: asyncio.Event) -> None:
    await asyncio.to_thread(recover, factory)
    while not stop.is_set():
        try:
            await asyncio.to_thread(step, factory)
        except Exception:
            log.exception("duel supervisor step failed")
        try:
            await asyncio.wait_for(stop.wait(), INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
