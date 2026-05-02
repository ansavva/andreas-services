# Andreas Services

This repository is a small portfolio of independently deployed applications that share a single source tree for convenience. Each directory under the root represents its own deployable unit with its own tech stack, pipeline, and README:

- **`storybook/`** – AI-assisted portrait studio.
- **`humbugg/`** – Secret gift-exchange platform.
- **`scout/`** - Email events aggregator. 

Because the projects have separate cloud resources and release cadences, changes should normally be scoped to a single directory. Refer to the README in each folder for details on setup, technology choices, prerequisites, and deployment assumptions.

## Pre-commit hooks

`.pre-commit-config.yaml` mirrors the PR-side checks (cfn-lint, terraform fmt + validate) so bad templates never make it into a PR. To enable locally:

```bash
pip install pre-commit
pre-commit install
```

Run manually against the whole tree: `pre-commit run --all-files`.
