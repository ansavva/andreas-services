---
phase: 01-foundation-scanners
plan: "1.1"
subsystem: cli
tags: [typer, python, cli, qrcode, pymupdf, osxphotos, rich]

# Dependency graph
requires: []
provides:
  - "Installable my-tools Python package at python/my_tools/"
  - "Unified Typer CLI with photos/media/qr groups registered via add_typer()"
  - "my-tools media kindle command wrapping kindle_formatter.py logic"
  - "my-tools qr generate command wrapping url_to_qr.py logic"
  - "my-tools photos group with scan-takeout, scan-icloud, setup stubs"
  - "Python 3.13 venv at python/venv/ with all dependencies installed"
  - "pyproject.toml with my-tools entry point and setuptools build"
  - "4 passing smoke tests confirming all groups respond to --help"
affects: [01-2, 01-3]

# Tech tracking
tech-stack:
  added:
    - "typer==0.24.1 — CLI framework with add_typer() group pattern"
    - "rich>=13.5.2,<14.0.0 — terminal output (constrained by osxphotos)"
    - "osxphotos==0.75.6 — iCloud Photos library access (Plans 1.3)"
    - "qrcode[pil]==8.0 — QR code generation"
    - "pymupdf>=1.24,<2 — PDF manipulation for kindle formatter"
    - "Pillow>=10.0,<12 — image processing"
    - "pytest>=8.0 — test framework"
  patterns:
    - "Typer multi-group app: each group is a separate module with its own app = typer.Typer(); registered in cli.py via app.add_typer(group_app, name='group')"
    - "Adding a new group: create my_tools/<group>/commands.py + one add_typer() line in cli.py"
    - "Test subprocess via venv binary path: Path(sys.executable).parent / 'my-tools'"

key-files:
  created:
    - "my-tools/python/my_tools/cli.py — main Typer app registering all groups"
    - "my-tools/python/my_tools/photos/commands.py — photos group with scan-takeout, scan-icloud, setup stubs"
    - "my-tools/python/my_tools/media/commands.py — media group with kindle command"
    - "my-tools/python/my_tools/qr/commands.py — qr group with generate command"
    - "my-tools/python/my_tools/tests/conftest.py — test helper with run_cli()"
    - "my-tools/python/my_tools/tests/test_cli_smoke.py — 4 smoke tests"
    - "my-tools/python/requirements.txt — pinned deps for Python 3.13 venv"
    - "my-tools/pyproject.toml — package definition with my-tools entry point"
  modified: []

key-decisions:
  - "Used rich>=13.5.2,<14.0.0 (not 14.3.3 as planned) because osxphotos==0.75.6 requires rich<14.0.0"
  - "Used setuptools.build_meta (not setuptools.backends.legacy:build) because legacy backend does not support editable installs"
  - "conftest.py resolves my-tools binary via sys.executable parent dir (not PATH lookup) for subprocess subprocess reliability"

patterns-established:
  - "CLI group pattern: my_tools/<group>/commands.py with app = typer.Typer(); registered in cli.py via app.add_typer()"
  - "Venv binary resolution for tests: Path(sys.executable).parent / 'binary-name'"

requirements-completed: [CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, SETUP-01]

# Metrics
duration: 4min
completed: "2026-03-29"
---

# Phase 1 Plan 1: CLI Framework Summary

**Typer multi-group CLI (my-tools) with photos/media/qr groups, kindle formatter and QR generator migrated from standalone scripts, Python 3.13 venv, 4 passing smoke tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T15:12:11Z
- **Completed:** 2026-03-29T15:16:32Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 9 created

## Accomplishments
- Created `my-tools` installable Python package with Typer multi-group app
- Migrated `kindle_formatter.py` and `url_to_qr.py` from savva-tools into CLI subcommands
- All 4 smoke tests pass: `my-tools --help`, `photos --help`, `media --help`, `qr --help`
- Python 3.13 venv at `python/venv/` with all dependencies installed

## How to activate

```bash
cd /Users/andreassavva/Repos/andreas-services/my-tools/python
source venv/bin/activate
my-tools --help
```

## How to add a new group

Create `python/my_tools/<groupname>/commands.py` with:
```python
app = typer.Typer(help="...")
@app.command("mycommand")
def mycommand(...): ...
```
Then add one line to `python/my_tools/cli.py`:
```python
app.add_typer(newgroup_commands.app, name="groupname")
```

## Task Commits

Each task was committed atomically:

1. **Task 1: Bootstrap package structure, venv, test scaffold (RED)** - `813ac00` (test)
2. **Task 2: Implement CLI groups (GREEN)** - `8f3fa12` (feat)

## Files Created/Modified
- `my-tools/python/my_tools/cli.py` — Typer app registering photos/media/qr groups
- `my-tools/python/my_tools/photos/commands.py` — scan-takeout, scan-icloud, setup stubs
- `my-tools/python/my_tools/media/commands.py` — kindle command (migrated from kindle_formatter.py)
- `my-tools/python/my_tools/qr/commands.py` — generate command (migrated from url_to_qr.py)
- `my-tools/python/my_tools/tests/conftest.py` — run_cli() subprocess helper
- `my-tools/python/my_tools/tests/test_cli_smoke.py` — 4 smoke tests
- `my-tools/python/requirements.txt` — pinned deps (rich version adjusted)
- `my-tools/pyproject.toml` — entry point, setuptools build config

## Decisions Made
- Used `rich>=13.5.2,<14.0.0` instead of `rich==14.3.3` (osxphotos 0.75.6 requires `rich<14.0.0`)
- Used `setuptools.build_meta` build backend (plan specified `setuptools.backends.legacy:build` which does not support editable installs)
- `conftest.py` resolves `my-tools` binary via `Path(sys.executable).parent` for subprocess reliability regardless of shell PATH

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Downgraded rich from 14.3.3 to >=13.5.2,<14.0.0**
- **Found during:** Task 1 (venv dependency install)
- **Issue:** `osxphotos==0.75.6` requires `rich<14.0.0` and `>=13.5.2`; `rich==14.3.3` causes an unresolvable conflict
- **Fix:** Changed `rich==14.3.3` to `rich>=13.5.2,<14.0.0` in both `requirements.txt` and `pyproject.toml`; installed rich 13.9.4
- **Files modified:** `python/requirements.txt`, `pyproject.toml`
- **Verification:** `pip install -r requirements.txt` succeeded; all tests pass
- **Committed in:** `813ac00` (Task 1 RED commit)

**2. [Rule 1 - Bug] Switched pyproject.toml build backend to setuptools.build_meta**
- **Found during:** Task 1 (editable install)
- **Issue:** `setuptools.backends.legacy:build` does not support `pip install -e .` (editable installs); raises `BackendUnavailable`
- **Fix:** Changed `build-backend = "setuptools.backends.legacy:build"` to `build-backend = "setuptools.build_meta"`
- **Files modified:** `pyproject.toml`
- **Verification:** `pip install -e .` succeeded, `my-tools --help` works
- **Committed in:** `813ac00` (Task 1 RED commit)

**3. [Rule 1 - Bug] Fixed conftest.py to resolve my-tools via venv bin path**
- **Found during:** Task 2 (GREEN test run)
- **Issue:** `subprocess.run(["my-tools", ...])` raised `FileNotFoundError` because `my-tools` wasn't on the subprocess PATH; the plan's conftest called `["my-tools", ...]` directly
- **Fix:** Changed conftest to use `MY_TOOLS = str(Path(sys.executable).parent / "my-tools")` so the binary is always resolved from the active venv
- **Files modified:** `python/my_tools/tests/conftest.py`
- **Verification:** All 4 smoke tests pass (GREEN)
- **Committed in:** `8f3fa12` (Task 2 feat commit)

---

**Total deviations:** 3 auto-fixed (3 × Rule 1 - bugs preventing correct operation)
**Impact on plan:** All fixes necessary for correct installation and test execution. No scope creep.

## Issues Encountered

- None beyond the auto-fixed deviations above.

## Known Stubs

| File | Stub | Reason |
|------|------|--------|
| `python/my_tools/photos/commands.py` | `scan-takeout` always exits 1 with "[Plan 1.2] not yet implemented" | Intentional — implemented in Plan 1.2 |
| `python/my_tools/photos/commands.py` | `scan-icloud` always exits 1 with "[Plan 1.3] not yet implemented" | Intentional — implemented in Plan 1.3 |
| `python/my_tools/photos/commands.py` | `setup` always exits 1 with "[Plan 1.3] not yet implemented" | Intentional — implemented in Plan 1.3 |

These stubs are intentional per the plan design. The photos subcommands are stubs because scan/import logic is Plan 1.2/1.3 scope. The `--help` outputs are complete and tested.

## User Setup Required

None — no external service configuration required beyond ensuring the venv is activated.

## Next Phase Readiness
- CLI framework complete; Plans 1.2 and 1.3 can implement their commands by adding code to `photos/commands.py`
- The `app.add_typer()` pattern is established; new groups only need a module + one line
- `python/venv/bin/my-tools` is the installed entry point for all CLI work

---
*Phase: 01-foundation-scanners*
*Completed: 2026-03-29*

## Self-Check: PASSED

All created files verified present. All task commits verified in git log.

- FOUND: my-tools/python/my_tools/cli.py
- FOUND: my-tools/python/my_tools/photos/commands.py
- FOUND: my-tools/python/my_tools/media/commands.py
- FOUND: my-tools/python/my_tools/qr/commands.py
- FOUND: my-tools/python/my_tools/tests/conftest.py
- FOUND: my-tools/python/my_tools/tests/test_cli_smoke.py
- FOUND: my-tools/python/requirements.txt
- FOUND: my-tools/pyproject.toml
- FOUND: 813ac00 (test RED commit)
- FOUND: 8f3fa12 (feat GREEN commit)
