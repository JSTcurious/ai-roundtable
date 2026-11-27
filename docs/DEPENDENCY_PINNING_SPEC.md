# Dependency Pinning — Reproducible Backend Builds
## ai-roundtable · JSTcurious · November 2026

**Status:** Approved 2026-11-27 with the proposed answers to all open questions (see Decisions).

---

## Problem Statement

`backend/requirements.txt` is what Railway installs on every deploy. Six of
its eight lines are unpinned, so each deploy installs whatever is newest that
day. Nothing records which versions production runs, and no CI installs the
dependencies or runs the tests.

| Package | Pinned? | Local `.venv` (what was tested) | Fresh install today (what Railway gets) |
|---|---|---|---|
| fastapi | no | 0.136.0 | 0.163.2 |
| starlette | `==0.46.2` | 0.46.2 | 0.46.2 |
| uvicorn[standard] | `==0.32.1` | 0.32.1 | 0.32.1 |
| websockets | no | 16.0 | 17.4 |
| anthropic | no | 0.96.0 | **2.14.0** |
| openai | no | 2.32.0 | **3.60.0** |
| google-genai | no | 1.73.1 | **3.6.1** |
| python-dotenv | no | 1.2.2 | 1.2.4 |

Three major-version jumps between what is tested and what ships. Failures
already traced to this:

- **Gemini seat down on Railway.** `google-genai` 3.x defaults to the `v1`
  API, where the seat's preview models 404 (fixed in #52 by pinning the API
  version — the package version is still floating).
- **Startup crash avoided only by testing in a clean venv.** `openai` 3.x and
  `anthropic` 2.x no longer install `httpx`; an `import httpx` added in #51
  would have crashed the app on the next Railway build (caught and replaced
  with `urllib` before merge).
- **The April WebSocket crash recurred locally.** `AttributeError:
  'WebSocketProtocol' object has no attribute 'transfer_data_task'` killed
  every session in April; the fix pinned `starlette` and `uvicorn`, but the
  attribute belongs to the `websockets` library's legacy protocol (which
  `uvicorn` 0.32.1 uses), and `websockets` was left unpinned. The same error
  appeared again on 2026-11-27 with `websockets` 16.0.
- **The pins that remain are now the liability.** With today's fresh SDKs,
  `starlette` 0.46.2's test client requires `httpx`, which is no longer
  installed: 13 tests fail in a clean install (test-only; the app runs).

## Goals

1. Every backend dependency — direct and transitive — pinned to an exact
   version, so a Railway build is reproducible.
2. One documented way to install the same set locally.
3. CI that installs the pinned set in a clean environment and runs the test
   suite on every PR and push to `main`.
4. A deliberate, tested way to upgrade.
5. Leave the `transfer_data_task` failure mode behind for good.

## Non-Goals

- Frontend dependencies (already locked by `package-lock.json`).
- The archived `v1/` app.
- Changing the Python version (3.13, per `.python-version`).

---

## Evidence: Candidate Version Sets (2026-11-27)

Each set was installed into a clean Python 3.13 venv from
`backend/requirements.txt` and run against six WebSocket close paths on a
real uvicorn server, plus the full test suite.

Close paths: (1) client leaves at prompt review, (2) server closes after a
bad handshake, (3) server closes after a completed session, (4) client
closes before sending the handshake, (5) client drops the TCP connection,
(6) server shuts down with a session open (what a redeploy does).

| Set | uvicorn / websockets / starlette | SDKs | Close-path tracebacks | Tests |
|---|---|---|---|---|
| **A** — today's pins, fresh install | 0.32.1 / 17.4 / 0.46.2 | latest | 0 | 13 fail (test client needs `httpx`) |
| **B** — today's pins, `websockets` 13.1 | 0.32.1 / 13.1 / 0.46.2 | latest | 0 | — |
| Local `.venv` | 0.32.1 / 16.0 / 0.46.2 | old (0.96 / 2.32 / 1.73) | 0 | 332 pass |
| **C** — all latest | 0.54.0 / 17.4 / 1.10.0 | latest | **11** | 332 pass |
| **C + `safe_close` fix** | 0.54.0 / 17.4 / 1.10.0 | latest | **0** | 332 pass |

The C tracebacks are in our code, not the libraries: newer uvicorn reports
"client already gone" as `WebSocketDisconnect`, and `safe_close()` only
catches `RuntimeError`. Catching both fixes all 11.

The 2026-11-27 `transfer_data_task` traceback did not reproduce on any set or
path. It lives in uvicorn 0.32.1's legacy `websockets` implementation; uvicorn
0.54 uses the sans-I/O implementation instead, so set C removes that code
path rather than pinning around it.

## Proposed Target: Set C + `safe_close` fix

- Matches what Railway most likely already runs for the SDKs (unpinned builds
  pick up the newest), so pinning does not downgrade production.
- Full test suite passes; all six close paths clean.
- Already verified live on these SDKs: discovery against all five providers
  (#51) and the Gemini seat with `v1beta` (#52). **Not yet verified live:**
  Claude, GPT, Grok, Perplexity and OpenRouter calls on `anthropic` 2.x /
  `openai` 3.x — AC7 covers this before merge.
- Drops the April pins on `starlette` and `uvicorn`, whose stated reason no
  longer applies.

The alternative — pin to the local `.venv` set — keeps old SDKs, downgrades
whatever production runs now, and keeps the legacy WebSocket code path.

---

## Design

### Files

```
backend/requirements.in        direct dependencies, lower bounds only (hand-edited)
backend/requirements.txt       every package ==pinned, generated (Railway installs this)
backend/requirements-dev.in    test-only: pytest, httpx (starlette's TestClient)
backend/requirements-dev.txt   generated, constrained by requirements.txt
```

Generated with uv, which the project already uses:

```
uv pip compile backend/requirements.in -o backend/requirements.txt --python-version 3.13
uv pip compile backend/requirements-dev.in -c backend/requirements.txt -o backend/requirements-dev.txt --python-version 3.13
```

The generated files carry uv's header with the exact command, and each pin
notes which direct dependency pulled it in.

- **Railway:** unchanged — `pip install -r backend/requirements.txt` now
  installs an exact set.
- **Local:** `uv pip sync backend/requirements.txt backend/requirements-dev.txt`
  makes `.venv` match exactly (removes anything extra).
- **Root `requirements.txt`:** empty since April and unused; removed.

### WebSocket close handling

`safe_close()` treats `RuntimeError` and `WebSocketDisconnect` as "already
closed". No other code change is required by set C.

### CI — `.github/workflows/tests.yml`

On every pull request and push to `main`:

1. Python 3.13, `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`
   in a clean runner (no cache), exactly as Railway installs.
2. **Lock check:** re-run both `uv pip compile` commands and fail if the
   output differs from the committed files (someone edited a `.in` without
   regenerating, or vice versa).
3. `pytest` (offline; `MODEL_DISCOVERY=0` via `conftest.py`; the live check
   stays skipped).
4. **WebSocket close-path test:** starts a real uvicorn server on a free port
   and runs the six close paths, failing on any server traceback.

No API keys are needed.

### Observability

Startup logs one line with the running versions — Python, fastapi,
starlette, uvicorn, websockets, anthropic, openai, google-genai — so a
Railway deploy log shows exactly what production runs.

### Upgrade process

Upgrades are deliberate PRs:

1. `uv pip compile --upgrade-package <name> …` (or `--upgrade` for all).
2. CI must pass (clean install + tests + close paths).
3. For SDK or server-stack changes: run the live check
   (`RUN_LIVE_EVALS=1 uv run pytest tests/test_live_synthesis_post_cutoff.py`)
   and one live session before merging.
4. After deploy, confirm the startup version line on Railway.

---

## Acceptance Criteria

| ID | Criterion |
|---|---|
| AC1 | `backend/requirements.txt` pins every installed package with `==`, is generated from `requirements.in`, and records the command. |
| AC2 | A clean Python 3.13 install of `requirements.txt` + `requirements-dev.txt` passes the full test suite. |
| AC3 | `safe_close()` swallows `RuntimeError` and `WebSocketDisconnect`; the six close paths produce no server traceback (automated, real server). |
| AC4 | CI runs on every PR and push to `main`: clean install, lock-in-sync check, tests, close paths. A PR that edits `requirements.in` without regenerating fails. *(manual: one PR run)* |
| AC5 | Startup logs the Python and key package versions. |
| AC6 | Local setup is one documented command; CLAUDE.md updated. |
| AC7 | **Live, before merge:** one full session on the pinned set — all four panelists `primary`, fact-check `primary`, synthesis `primary` — and intake primary + fallback return valid decisions. *(manual)* |
| AC8 | After deploy, Railway's startup log shows the pinned versions on Python 3.13. *(manual)* |

## Implementation Tasks

1. `requirements.in` / `requirements-dev.in`; generate both `.txt` files at set C. — AC1
2. `safe_close()` fix plus the real-server close-path test. — AC3
3. Clean-venv install + full suite. — AC2
4. `tests.yml` workflow with the lock check. — AC4
5. Startup version log line. — AC5
6. Docs: CLAUDE.md (setup, upgrade process), remove root `requirements.txt`. — AC6
7. Live session on the pinned set. — AC7

## Estimated Effort

About 1 day, most of it verification (tasks 3, 4, 7).

---

## Decisions (2026-11-27)

All four proposals accepted:

1. Target **set C + `safe_close` fix** (latest stack).
2. Tooling: **`requirements.in` + `uv pip compile`**; Railway's build command unchanged.
3. **Hashes on** (`--generate-hashes`).
4. **Manual upgrade PRs** when needed.

## Implementation Notes (2026-11-27)

Where the implementation differs from or adds to the design above:

1. **`--generate-hashes` is in both compile commands.** The Design section's
   commands predate decision 3. The commands as run (and recorded in each
   lockfile header, CI and CLAUDE.md) are:
   ```
   uv pip compile backend/requirements.in -o backend/requirements.txt --python-version 3.13 --generate-hashes
   uv pip compile backend/requirements-dev.in -c backend/requirements.txt -o backend/requirements-dev.txt --python-version 3.13 --generate-hashes
   ```
2. **No `--universal` needed.** Compiling on macOS (arm64) and for
   x86_64 manylinux gave identical pins and hashes, so the CI lock check on
   ubuntu doesn't fail spuriously on a lock made on a Mac. CI pins
   `uv==0.12.5` so a new uv release can't change the output format.
3. **The SDKs now use `httpx2`/`httpcore2`**, not httpx. httpx 0.29.0 is
   only in the dev lock (for starlette's TestClient). A new test
   (`test_backend_never_imports_httpx`) fails if backend code imports httpx,
   which would crash a Railway build.
4. **The lock-in-sync half of AC1/AC4 lives in CI**, not pytest, because
   re-resolving needs network access and the suite stays offline. Locally
   verified: the check passes on the committed files and fails after
   adding a package to `requirements.in` without regenerating.
5. **Close-path tracebacks.** Before the fix, on set C, paths 1 (client
   leaves at prompt review), 5 (TCP abort) and 6 (server shutdown) each
   logged one `WebSocketDisconnect` traceback from `websocket.close()`
   inside `safe_close()`; paths 2–4 were clean. The earlier evidence run
   counted 11 tracebacks, presumably across repeated runs; the fix and the
   test are unaffected. The test (`tests/test_ws_close_paths.py`) also
   passes on the old uvicorn 0.32.1 stack.
6. **Startup line format:** `[STARTUP] Python 3.13.12 · fastapi 0.165.0 ·
   starlette 1.10.0 · uvicorn 0.54.0 · websockets 17.4 · anthropic 2.14.0 ·
   openai 3.60.0 · google-genai 3.6.1`, printed before the role → model
   table. A package that is not installed shows as `missing`.
7. **Out of scope, noted:** FastAPI 0.165 warns that `@app.on_event` is
   deprecated in favour of lifespan handlers. It still works; migrating is a
   separate change.

### Verification

- AC2: clean Python 3.13.12 venv, `pip install -r` both lockfiles,
  `pip check` clean → 345 passed, 1 skipped (also 345/1 in the existing
  local `.venv`).
- AC7 (live, 2026-11-27, worktree backend on port 8001, pinned venv):
  Gemini, GPT, Grok and Claude `model_complete` all `primary`;
  `factcheck_availability` `primary`; `synthesis_model_used`
  `claude-opus-4-6`; server log `Pipeline healthy: synthesis=primary`;
  server closed the socket with 1000 after `session_complete`, no
  tracebacks. Intake primary (claude-sonnet-4-6) and fallback
  (`call_gpt4o_mini_intake`, gpt-5.4-mini) both returned a valid
  `IntakeDecision`.

## Open Questions (resolved — kept for the record)

1. **Target set.** Set C + `safe_close` fix (proposed), or pin the local
   `.venv` versions (older SDKs, keeps uvicorn 0.32.1)?
2. **Tooling.** `requirements.in` + `uv pip compile` (proposed — no Railway
   change), or a `pyproject.toml` + `uv.lock` (uv-native, but Railway's build
   command must change to `uv sync --frozen`)?
3. **Hashes.** Generate with `--generate-hashes` so pip verifies every
   download? Proposed: yes — it blocks a tampered or substituted package at
   install time, at the cost of larger lock files.
4. **Upgrade cadence.** Manual upgrade PRs when needed (proposed), a monthly
   scheduled workflow that opens an upgrade PR, or Dependabot?
