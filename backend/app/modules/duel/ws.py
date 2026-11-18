"""Duel WebSocket: live state pushed to one player.

Protocol (JSON text frames):
    client -> {"type": "auth", "token": "<JWT>"}   must be the first frame (10 s)
    server -> {"type": "auth_ok"}
    server -> {"type": "state", ...}                see service.state_for_user
    client -> {"type": "ping"}  server -> {"type": "pong"}

What the socket carries about the opponent is ONLY their solved count (and whether they are
connected). Code is never sent over the socket - submissions go through REST - and nothing
the client sends over it can change a match. An open socket is a player's "presence": when
the last one closes, the 60 s reconnect grace starts.
"""

import asyncio
import json
import logging
from typing import Callable

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.modules.auth import service as auth_service
from app.modules.duel import presence, service

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0  # how often the server re-reads the match for this player
HEARTBEAT_SECONDS = 5.0  # resend the state at least this often (clock resync)
AUTH_TIMEOUT_SECONDS = 10.0

CLOSE_UNAUTHORIZED = 4401
CLOSE_BLOCKED = 4403

Factory = Callable[[], Session]


def _comparable(msg: dict) -> dict:
    """The state without the values that tick every second."""
    out = json.loads(json.dumps(msg))
    if isinstance(out.get("match"), dict):
        out["match"].pop("remaining_seconds", None)
    if isinstance(out.get("waiting"), dict):
        out["waiting"].pop("seconds", None)
    return out


def _snapshot(factory: Factory, user_id: int) -> dict:
    with factory() as db:
        return {"type": "state", **service.state_for_user(db, user_id, service.now())}


def _authenticate(factory: Factory, token: str) -> tuple[int | None, bool]:
    user_id = decode_access_token(token)
    if user_id is None:
        return None, False
    with factory() as db:
        user = auth_service.get_user(db, user_id)
        return (user.id, user.is_blocked) if user else (None, False)


def _connected(factory: Factory, user_id: int) -> None:
    with factory() as db:
        service.on_connected(db, user_id, service.now())


def _disconnected(factory: Factory, user_id: int) -> None:
    with factory() as db:
        service.on_disconnected(db, user_id, service.now())


async def serve(ws: WebSocket, factory: Factory) -> None:
    await ws.accept()
    try:
        data = json.loads(await asyncio.wait_for(ws.receive_text(), AUTH_TIMEOUT_SECONDS))
        token = data["token"] if isinstance(data, dict) and data.get("type") == "auth" else None
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, KeyError, TypeError):
        token = None
    if not isinstance(token, str):
        await _close(ws, CLOSE_UNAUTHORIZED)
        return
    user_id, blocked = await asyncio.to_thread(_authenticate, factory, token)
    if user_id is None:
        await _close(ws, CLOSE_UNAUTHORIZED)
        return
    if blocked:
        await _close(ws, CLOSE_BLOCKED)
        return

    presence.connect(user_id)
    recv: asyncio.Task | None = None
    try:
        await ws.send_json({"type": "auth_ok"})
        await asyncio.to_thread(_connected, factory, user_id)
        loop = asyncio.get_running_loop()
        recv = asyncio.create_task(ws.receive_text())
        last: dict | None = None
        last_sent = 0.0
        while True:
            msg = await asyncio.to_thread(_snapshot, factory, user_id)
            changed = last is None or _comparable(msg) != last
            if changed or loop.time() - last_sent >= HEARTBEAT_SECONDS:
                await ws.send_json(msg)
                last, last_sent = _comparable(msg), loop.time()
            done, _ = await asyncio.wait({recv}, timeout=POLL_SECONDS)
            if recv in done:
                text = recv.result()  # raises WebSocketDisconnect when the client left
                recv = asyncio.create_task(ws.receive_text())
                try:
                    if json.loads(text).get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except (ValueError, AttributeError):
                    pass  # anything else the client sends is ignored
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if recv is not None and not recv.done():
            recv.cancel()
        # No `await` here on purpose: cleanup must not be cancellable half-way, otherwise a
        # lost write would leave the match thinking this player is still connected. (The
        # supervisor also reconciles presence on every tick, as a safety net.)
        if presence.disconnect(user_id):
            try:
                _disconnected(factory, user_id)
            except Exception:  # noqa: BLE001 - never let cleanup raise
                log.exception("could not record disconnect of user %s", user_id)


async def _close(ws: WebSocket, code: int) -> None:
    try:
        await ws.close(code=code)
    except RuntimeError:
        pass
