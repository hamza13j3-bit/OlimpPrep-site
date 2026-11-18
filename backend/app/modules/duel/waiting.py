"""In-memory waiting list (no Redis). Lost on restart: players simply join again."""

import threading
from dataclasses import dataclass
from typing import Callable, TypeVar

BASE_WINDOW = 100  # initial +-100 rating points
WIDEN_STEP = 50  # ... widening by 50
WIDEN_EVERY = 15  # ... every 15 seconds

T = TypeVar("T")


@dataclass(frozen=True)
class Waiting:
    user_id: int
    rating: float
    joined_at: float  # seconds (epoch)


def window(entry: Waiting, now: float) -> int:
    return BASE_WINDOW + WIDEN_STEP * int(max(0.0, now - entry.joined_at) // WIDEN_EVERY)


class WaitingList:
    def __init__(self) -> None:
        self._items: dict[int, Waiting] = {}
        self._lock = threading.Lock()

    def join(self, user_id: int, rating: float, now: float) -> bool:
        with self._lock:
            if user_id in self._items:
                return False
            self._items[user_id] = Waiting(user_id, rating, now)
            return True

    def leave(self, user_id: int) -> bool:
        with self._lock:
            return self._items.pop(user_id, None) is not None

    def get(self, user_id: int) -> Waiting | None:
        with self._lock:
            return self._items.get(user_id)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def find_matches(
        self, now: float, try_pair: Callable[[Waiting, Waiting], T | None]
    ) -> list[tuple[Waiting, Waiting, T]]:
        """Pair up compatible players and remove them from the list.

        Two players are compatible when their rating difference fits inside BOTH windows
        (the narrower one decides). The longest-waiting player is served first and gets the
        closest compatible opponent for whom `try_pair` returns something (e.g. enough
        unsolved problems); players without a partner keep waiting.
        """
        with self._lock:
            entries = sorted(self._items.values(), key=lambda e: (e.joined_at, e.user_id))
            used: set[int] = set()
            pairs: list[tuple[Waiting, Waiting, T]] = []
            for e in entries:
                if e.user_id in used:
                    continue
                candidates = [
                    o
                    for o in entries
                    if o.user_id != e.user_id
                    and o.user_id not in used
                    and abs(o.rating - e.rating) <= min(window(e, now), window(o, now))
                ]
                candidates.sort(key=lambda o: (abs(o.rating - e.rating), o.joined_at))
                for o in candidates:
                    payload = try_pair(e, o)
                    if payload is not None:
                        used.update((e.user_id, o.user_id))
                        pairs.append((e, o, payload))
                        break
            for e, o, _ in pairs:
                self._items.pop(e.user_id, None)
                self._items.pop(o.user_id, None)
            return pairs


waiting = WaitingList()
