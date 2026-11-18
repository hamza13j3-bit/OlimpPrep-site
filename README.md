# OlimpPrep

Olympiad-informatics training platform (kk/ru/en). Stage 1 in progress.

## Run

Backend (Python 3.12+):
```
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # set SECRET_KEY, optionally ADMIN_EMAIL
python -m app.seed.run          # load 36 sample problems (optional, idempotent)
uvicorn app.main:app --reload   # http://localhost:8000/health
pytest
```

Frontend (Node 18+):
```
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api -> :8000)
npm run lint
```

The frontend loads the Monaco editor files from the jsDelivr CDN, so the problem page needs internet access.

No Docker, no Redis; SQLite file `backend/olimpprep.db`.

## Duels

One-versus-one matches: join with POST /duel/queue, follow the match over the WebSocket /duel/ws (or GET /duel/me), submit with POST /duel/matches/{id}/submit. All timers (60 min deadline, 60 s reconnect grace, matchmaking window) run on the server in a background task; the waiting list and socket presence live in memory, so run a single server process. Duel Elo (K=32) is separate from the training rating.

## Problem packages

Admins can import/export problems as ZIP packages (POST /archive/import, GET /archive/problems/{id}/export). Format, limits and a sample: docs/sample-package/.

## Checker isolation limits

The checker runs untrusted Python/C++ **without Docker**, so isolation is best effort. Each test runs
in a fresh temporary directory (deleted afterwards) with a minimal environment (no server secrets such
as `SECRET_KEY`). Inside the checker a test either passes or not; the reason is never exposed.

| Limit | Windows | Linux/macOS |
|---|---|---|
| Wall-clock time limit (per test, killed on expiry) | yes | yes |
| Output cap (about 4x expected output, max 16 MB; process killed beyond it) | yes | yes |
| Memory limit | Job Object `ProcessMemoryLimit` | `RLIMIT_AS` |
| CPU time | wall-clock only | `RLIMIT_CPU` |
| Process count | Job Object limit (4) | not limited (killed with its process group) |
| Whole process tree killed on timeout | Job Object kill-on-close | `killpg` |
| Core dumps / file size | n/a | `RLIMIT_CORE=0`, `RLIMIT_FSIZE` |

**Not isolated (known gaps):** no filesystem restrictions (a solution can read files the server user can
read, including `.env`, and write outside its temp dir), no network restrictions, no syscall filtering,
C++ compilation is not sandboxed beyond a time/memory limit (`#include` can read files; compiler output
is discarded). Python start-up gets a 0.3 s allowance on top of the time limit. Run the server as an
unprivileged OS user in a dedicated account/VM and treat this as suitable for a university
project/trusted users, not for the open internet. C++ needs `g++` on `PATH` (MinGW-w64 on Windows);
without it C++ submissions simply pass no tests.

Submissions are checked by an in-process queue (2 worker threads). Responses contain only
`tests_passed`, `tests_total`, `score` and `solved`; `GET /submissions/{id}` returns HTTP 202 while the
check is still running.