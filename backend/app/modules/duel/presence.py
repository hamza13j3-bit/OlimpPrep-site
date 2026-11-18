"""Who currently has an open duel WebSocket (a user may have several tabs)."""

import threading

_lock = threading.Lock()
_counts: dict[int, int] = {}


def connect(user_id: int) -> bool:
    """Register a socket. Returns True if it is the user's first one."""
    with _lock:
        _counts[user_id] = _counts.get(user_id, 0) + 1
        return _counts[user_id] == 1


def disconnect(user_id: int) -> bool:
    """Unregister a socket. Returns True if it was the user's last one."""
    with _lock:
        n = _counts.get(user_id, 0) - 1
        if n <= 0:
            _counts.pop(user_id, None)
            return True
        _counts[user_id] = n
        return False


def is_connected(user_id: int) -> bool:
    with _lock:
        return _counts.get(user_id, 0) > 0


def clear() -> None:
    with _lock:
        _counts.clear()
