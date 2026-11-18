# OlimpPrep (university project)

Olympiad-informatics training platform (Kazakh/Russian/English) with a Codeforces-style
problem archive, Elo ratings and 1v1 duels.

## Hard constraints
- NO Docker. NO git usage. NO AI/LLM/ML. Plain algorithms only. SQLite, no Redis.
- NO verdict labels (AC/WA/TLE/MLE/RE/CE) in UI or API. The server checks code and returns
  only: tests_passed, tests_total, score in [0,1], solved (bool). Internally the runner enforces
  timeouts and limits; any failure simply means "test not passed".
- NO thinking-trace/event recording, NO teacher role, NO break-the-code game.
- Only TWO roles: `user` and `admin`. The first registered account (or ADMIN_EMAIL from env)
  becomes admin.

## Features
- Problem archive (Codeforces problemset style): collections, filters, search, status.
- Problem page: Monaco editor (Python, C++), result bar "12/20 тест өтті", 3-level hints.
- Idea note before coding (min 30 words + checklist), private to the user.
- Elo rating: players AND problems; S = score in [0,1]; per-tag ratings; hints reduce S.
- 1v1 Duel: matchmaking, server-side timer, WebSocket.
- Progress stats: average score per tag, spaced "retry later" list (1/3/7/14 days).
- Leaderboards (global, per tag, duel) and admin dashboard.

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, SQLite, Pydantic v2, pytest
- Checker: subprocess with timeout + resource limits (Python, C++ via g++), temp dirs
- Frontend: React + Vite + TypeScript, Tailwind, Monaco Editor, react-i18next (kk default, ru, en),
  Recharts, KaTeX

## Rules
- Modular monolith: app/modules/{auth,problems,archive,checker,rating,duel,stats,admin}
  with router.py, service.py, models.py, schemas.py. Modules call each other's services only.
- Checking, scoring and timers are always server-side; never trust the client.
- Document the checker's isolation limits (no Docker) in README.
- Run `pytest` and `npm run lint` before declaring a task done. Ask before adding a dependency.
- After each module, append a short note to docs/PROGRESS.md: what was done, which files, what is left.