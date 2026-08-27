"""Where `studio/` is, counted once.

The pipeline half has `studio_pipeline.STUDIO_DIR` and its `CLAUDE.md` says
why: *"Use it rather than counting `..` segments — that is what broke every time
a file moved."* The backend had no equivalent, so three test modules each
counted their own way to `infra/` and `seeds/`, and all three broke the moment
the unit tests moved one directory deeper. This is that constant.

Deliberately NOT in `conftest.py`: a conftest is fixtures, and importing a
constant out of one reads like a mistake even when it works.
"""
from pathlib import Path

#: The `studio/` service directory — `tests/paths.py` -> `tests/` -> `backend/`
#: -> `studio/`. The one place in this suite that counts.
STUDIO_DIR = Path(__file__).resolve().parents[2]
INFRA_MODULES = STUDIO_DIR / "infra" / "modules"
SEEDS = STUDIO_DIR / "seeds"
