# Browser Isolation Implementation Plan

**Goal:** No-registration browser-private workspace with password-gated export.
**Architecture:** Hosted-only session middleware, server-derived owners and an independent export unlock. SQLite persists sessions; existing filesystem/job manager remains.
**Tech Stack:** Python/FastAPI/SQLite/hashlib PBKDF2-HMAC-SHA256 (600,000 iterations), vanilla JS, FFmpeg/Pillow.

## Global Constraints
Secure cookies in hosted HTTPS; local mode unchanged. 24-hour file expiry, single processing slot, 25 MiB/30-second/720p constraints remain. Legacy unowned data is inaccessible. No credentials or user media in Git.

- [x] Write failing `tests/test_sessions.py`: cookie issuance, two distinct owners, password unlock, CSRF, forged/expired tokens, throttling, persistence. Implement `app/sessions.py`: `SessionStore(root, password_file)`, `create(ip)`, `get(token)`, `unlock(token,password,ip)` and `BrowserSessions` middleware.
- [x] Write failing `tests/test_isolation.py`: all cross-owner routes including ranges and retry/create from another upload. Implement Request-based helpers in `app/server.py`; persist owner during `JobManager.create(...,owner_id=None)` and propagate on retry. Compare owner before returning content. Legacy owner missing always denied in hosted mode.
- [x] Verify unauthorized full output returns 403; preview remains marked and bounded. Implement `app/preview.py` with serialized FFmpeg conversion and atomic cache publication in the owning job folder, removed by existing retention. Show password form and clean-result URL only after successful unlock.
- [x] Run `pytest -q tests/test_sessions.py tests/test_isolation.py`, full backend suite and recorded browser tests. Request independent code review; fix blockers.
- [x] Stage deployment with Basic Auth still enabled, validate two HTTPS clients, then remove Basic Auth and validate anonymous homepage, session isolation, export password and mobile-sized interaction. Retain access-limited rollback. Update bilingual README/deploy documentation and publish source.
