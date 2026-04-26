# LESSONS.md — Failure Log

## 2026-04-26 — Railway frontend serving stale build

### What happened
Merged 5 PRs with frontend JSX changes (PRs #30–#35).
Production UI was stuck on old behavior despite Railway
showing "Active" deployment. Local testing worked correctly.

### Root cause
Railway's frontend service serves frontend/build/ as a
static site. It does NOT recompile JSX on deploy. The
build/ directory in the repo was stale — predating all
five PRs.

### Why it wasn't caught sooner
Local dev uses npm start which compiles on the fly.
No CI step enforced a fresh build before merge.
Railway's "successful" deploy was misleading — it deployed
the stale build/ without error or warning.

### Fix
Run npm run build locally after any frontend changes.
Commit and push frontend/build/ alongside the source changes.
Both must travel in the same commit.

### Prevention
- Added build instructions to CLAUDE.md deployment section
- Future: add a CI check that fails if build/ is stale
  relative to src/ changes

## 2026-04-26 — Grok API key not loading

### What happened
GROK_API_KEY was set in backend/.env but Grok calls failed
on startup with "Bearer " warning. Key appeared empty despite
being present in the file.

### Root cause
Two files read GROK_API_KEY without calling load_dotenv():
- backend/models/grok_client.py
- backend/models/model_validator.py (also reading wrong var
  name: XAI_API_KEY instead of GROK_API_KEY)

### Fix
Added load_dotenv() to both files. Fixed env var name in
model_validator.py. Fixed in PR #35.

### Verified
Bearer warning gone from startup logs after fix.
Grok API key confirmed loading correctly in local test
session (immigration prompt, April 26 2026).

### Prevention
Every client module must call load_dotenv() before any
os.getenv() call. This pattern is now enforced in CLAUDE.md.
