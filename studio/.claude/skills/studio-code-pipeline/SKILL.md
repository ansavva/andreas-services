---
name: studio-code-pipeline
description: Working on studio's own pipeline code — the `studio` CLI, its modules, its tests. Use when adding or changing a subcommand, moving code between subpackages, touching the model registry's machinery, debugging an import or wiring failure, or writing pipeline tests. This is the code-facing half of studio; to USE the pipeline to generate media, use a `studio-media-*` skill instead.
---

# studio-code-pipeline — changing the pipeline itself

Two families of skill live under `studio/.claude/skills/`, and picking the wrong
one wastes a session:

| | `studio-media-*` | `studio-code-*` |
|---|---|---|
| You are | making media with studio | changing studio |
| Fifteen of them, covering | characters, prompts, engines, scenes, the stores | this |
| They describe | the CLI surface — `studio <command>` | the code behind it |
| May name modules | **no** | **yes** — that is the subject |

The pipeline is **one package, one console script**:
`studio/pipeline/src/studio_pipeline/`, exposing `studio`. It runs locally inside
Claude and **never deploys** — the CI path filters exclude it from
`studio-prod.yaml` but *not* from `studio-pr.yml`, because it is 7k lines of
Python with a suite and "does not ship" is not a reason to leave it unchecked.

## Read this first

[**docs/PIPELINE.md**](../../../docs/PIPELINE.md) is the reference and this skill
does not restate it. Go straight to:

- [The modules](../../../docs/PIPELINE.md#the-modules) — every module and what it
  holds, by subpackage. **The only place internals are named.**
- [Layout](../../../docs/PIPELINE.md#layout) — why `src/`, why the subpackages
  are named after what things *are*, and which way dependencies point
  (`cli` → `domain` → `adapters`).
- [How the code is invoked](../../../docs/PIPELINE.md#how-the-code-is-invoked) —
  the Click tree and what the argparse port cost.
- [How to add a new skill](../../../docs/PIPELINE.md#how-to-add-a-new-skill) —
  the seven steps, in order.

The [hard rules](../../../docs/PIPELINE.md#hard-rules) bind here exactly as they
do in a media skill. **No character name in code, docstrings, tests, fixtures,
commit messages or PR titles** — the test fixtures use `subject-a` / `subject-b`
for this reason, and a new fixture should too.

## Conventions that bite

These are the ones that have actually cost time.

- **`--help` is not a test.** Every subcommand printed usage happily while
  `engine/refs.py` referenced an undefined name, and again while `character`,
  `curate` and `run` had no handler to dispatch to. Usage never reaches either.
  `pipeline/tests/` is weighted towards **wiring and execution** for that reason,
  not features — a restructure is what actually breaks this code.
- **The CLI surface is a contract.** `pipeline/tests/cli_surface_reference.json`
  records every option, arity, default, choice list and help string — 255 params,
  captured off the real argparse parsers before the Click port. Changing the CLI
  means regenerating it *deliberately*; never edit it to make a test pass. It is
  an argparse capture, so a wholesale re-capture from Click would discard the
  provenance it exists to preserve — change the fields you meant to change.
- **One constant knows where `studio/` is**: `studio_pipeline.STUDIO_DIR`. It
  searches upward for the directory holding both `backend/` and `pipeline/`.
  Counting `".."` segments is right for exactly one file's depth and broke every
  time something moved — adopting `src/` proved it again.
- **One package, one dependency set** (`pipeline/pyproject.toml`, locked in
  `uv.lock`). Not a venv per module; that was the pre-CLI shape and bought
  nothing.
- **`pipeline/scripts/lint_skills.py` guards the docs.** It checks that every
  `studio …` line in a skill names a real command, that no script-era invocation
  survives, and that a `studio-media-*` skill names no module. Run it directly,
  or let pre-commit and the PR workflow run it.
- **New Bash permissions go in the monorepo root `.claude/settings.json`**, not
  a nested one — Claude Code does not read nested settings, even though these
  skills are nested.

## Testing

```bash
cd studio/pipeline && uv run pytest tests/ -q     # moto-backed, needs no AWS
uv run ruff check studio/pipeline
uv run python scripts/lint_skills.py              # the docs guard
```

The suite never reaches the network: `conftest.py` pins a fake
`REPLICATE_API_TOKEN` and a moto bucket seeded with a miniature of the real tree.
It deliberately mirrors `studio/backend/tests/conftest.py` — both halves of
studio read the same tree, so the two fixtures agreeing is what makes a
disagreement between them mean something.

## The rule that keeps the two halves apart

**No code in this package generates prose, and no media skill names code.**

Both directions failed once and cost the same way. `add_model.py` held a format
string that wrote each new model's `SKILL.md`; it emitted boilerplate around a
`TODO` asking for the only content worth having, rotted unread, and began
stamping a long-dead path into every new model's page. In the other direction,
two media skills carried tables of every module in the package, and five of those
names had become files that did not exist.

So: prose is authored, in a skill or in `docs/`. Code is documented once, in
`docs/PIPELINE.md`, next to what it describes.
