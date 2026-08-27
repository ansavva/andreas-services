"""Unit tests, mirroring `src/studio_pipeline/`.

One directory per subpackage, and a test module named for the module it
covers — so `unit/engine/test_board.py` is `engine/board.py` and there is
nowhere else to look. The `_adapter` / `_client` suffixes that used to
disambiguate these in a flat directory are gone with the flatness.

Nothing here touches the network, AWS, or a model provider; `conftest.py` one
level up enforces all three. Tests that are about a RISK rather than a module
live in `contracts/`.
"""
