"""Tests named for the failure they catch, not for a module.

**Deliberately NOT mirrored onto the source tree**, because none of these is
about one module. Each is named for a class of bug that actually shipped:

    test_wiring          the imports, constants and dispatch a MOVE breaks
    test_cross_module    calls that cross a module boundary
    test_cli_shadowing   a Click parameter shadowing a function in its own body
    test_cli_execution   commands that dispatch, not just parse
    test_cli_surface     the frozen argparse-era CLI contract
    test_dev_scripts     the two-sided contract with the shell scripts

Naming these after modules would scatter each one across four directories and
lose the only thing that makes them findable. See `docs/PIPELINE.md`.

`cli_surface.py`, `cli_surface_reference.json` and `update_cli_reference.py`
live here rather than in `support/` because they are one unit with
`test_cli_surface.py` — the capture, the contract and the tool that rewrites it.
"""
