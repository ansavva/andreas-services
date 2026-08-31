"""The pipeline's test suite. START HERE.

    tests/
      conftest.py        the guards. Read them before adding a test.
      support/           harnesses, not tests — fake_api.py, shell.py
      unit/              mirrors src/studio_pipeline/, one dir per subpackage
      contracts/         named for the FAILURE they catch, not for a module
      integration/       the real CLI against a real dev stack

WHERE DOES MY TEST GO?

Ask what it is about, not what it imports.

  * **One module.** `unit/<subpackage>/test_<module>.py`, mirroring the source.
    `engine/board.py` is `unit/engine/test_board.py` and there is nowhere else
    to look.
  * **A class of failure that spans modules.** `contracts/`. These are named
    after bugs that actually shipped — `test_cli_shadowing`, `test_wiring`,
    `test_cli_execution` — because naming them after modules would scatter each
    one across four directories and lose the only thing that makes them
    findable.
  * **Something that needs real AWS or the real API.** `integration/`, behind
    `STUDIO_INTEGRATION=1`, run by `scripts/dev-test-integration.sh`. Never in
    CI. Every test there shells out to the `studio` binary rather than using
    `CliRunner`, because this conftest pins the bucket and table to PRODUCTION
    names at import and starts moto — read `integration/__init__.py` first.

WHAT THE GUARDS DO, AND WHY YOU SHOULD NOT WORK AROUND THEM

`conftest.py` autouses four, and each one is a bug that already happened:

  * the **fake API** — `tests/support/fake_api.py` answers `adapters.api.request`
    in memory, including `POST /api/runs/<id>/submit`. The seam a test controls
    is `fake_api.submits_refused`, which is stronger than "nothing billed": a
    dry run must not submit AT ALL, and a fake would answer one happily.
  * `_no_outbound_sockets` — loopback only, and **the primary guard now**. There
    is no provider client left in this package to switch off, so what stops a
    paid call reached indirectly — through a module nothing knows about, or a
    subprocess — is this. `STUDIO_REPLICATE_MODE=fake` and a dud
    `REPLICATE_API_TOKEN` are still set beside it, belt-and-braces: if code that
    reaches a provider ever comes back here it costs a 401, not a bill.
  * `_registry_is_a_copy` — `studio models refresh` rewrites `models.json` in
    place and the dispatch test invokes every leaf command. It once deleted 391
    lines of committed schema.
  * `_auth.CONFIG_DIR` redirection — the full-suite walk ran `studio logout`
    against a developer's real credentials file.

If a guard is in your way, the test probably belongs in a different tier.

WHY THE TIERS ARE DIRECTORIES AND NOT MARKERS

Because **conftest inheritance is scoped by directory**, so the tier boundary
and the guard boundary are the same line. A marker would label the test and
leave the guards to be re-derived per file, which is the per-test-stubbing
problem again. This is not hypothetical: the backend's socket guard was written
at `tests/` and silently applied to `tests/integration/`, whose whole purpose is
to reach real AWS — and because that tree is skipped without a flag, it would
have stayed green in CI and broken only for whoever next ran it on purpose.
"""
