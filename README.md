# Andreas Services

This repository is a small portfolio of independently deployed applications that share a single source tree for convenience. Each directory under the root represents its own deployable unit with its own tech stack, pipeline, and README:

- **`storybook/`** – AI-assisted portrait studio.
- **`humbugg/`** – Secret gift-exchange platform.
- **`scout/`** - Email events aggregator. 

Because the projects have separate cloud resources and release cadences, changes should normally be scoped to a single directory. Refer to the README in each folder for details on setup, technology choices, prerequisites, and deployment assumptions.

## Local development setup

Bootstrap the toolchain with the idempotent setup scripts (Homebrew on both macOS
and Linux; safe to re-run — already-installed tools are skipped). From the repo root:

```bash
./humbugg/scripts/dev-setup.sh  # shared tools + .NET + per-machine Humbugg AWS

# See what's missing without installing anything:
./humbugg/scripts/dev-setup.sh --check
```

The `humbugg/` and `website/` frontends depend on the private
`@ansavva/design-system` package on GitHub Packages, so `npm ci` needs a token
with the `read:packages` scope exposed as `NODE_AUTH_TOKEN`:

```bash
export GITHUB_PACKAGES_TOKEN=<pat-with-read:packages>
eval "$(./scripts/github-packages-auth.sh --export)"   # sets NODE_AUTH_TOKEN
```

Full details (macOS vs. Linux specifics, how the Linux path runs Homebrew as a
non-root user, per-service scripts) are in [`scripts/README.md`](scripts/README.md).

## Pre-commit hooks

`.pre-commit-config.yaml` mirrors the PR-side checks (cfn-lint, terraform fmt + validate) so bad templates never make it into a PR. To enable locally:

```bash
pip install pre-commit
pre-commit install
```

Run manually against the whole tree: `pre-commit run --all-files`.
