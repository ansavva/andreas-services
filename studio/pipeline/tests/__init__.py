"""The pipeline's test suite. START HERE.

    tests/
      conftest.py        the guards. Read them before adding a test.
      support/           harnesses, not tests — fake_api.py, shell.py
      unit/              mirrors src/studio_pipeline/, one dir per subpackage
      contracts/         named for the FAILURE they catch, not for a module
      integration/       the real CLI against a real dev stack (not yet built)

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
    `STUDIO_INTEGRATION=1`. Never in CI.

WHAT THE GUARDS DO, AND WHY YOU SHOULD NOT WORK AROUND THEM

`conftest.py` autouses four, and each one is a bug that already happened:

  * `STUDIO_REPLICATE_MODE=fake` — **do not stub the provider yourself.** Every
    test that reached the engine used to monkeypatch the adapter by hand, and a
    new file that forgot called Replicate for real.
  * `_no_outbound_sockets` — loopback only. Catches a paid call reached
    INDIRECTLY, which the mode switch cannot see.
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
