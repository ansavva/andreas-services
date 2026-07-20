# Developer / CI toolchain scripts

Idempotent bootstrap scripts that install the tools needed to build and test
this monorepo. Safe to re-run: every tool is checked before install, so an
already-installed dependency is never reinstalled. **Homebrew is the installer
on both macOS and Linux.**

Two layers — a shared base plus thin per-service scripts:

| Script | Scope | Installs |
|---|---|---|
| `scripts/dev-setup.sh` | Shared base (all services) | Terraform, tflint (+ pinned AWS ruleset, best-effort), AWS CLI, Node.js, jq, zip, Stripe CLI (+ Docker check) |
| `scripts/github-packages-auth.sh` | Shared base (all frontends) | Ensures a `read:packages` token is available as `NODE_AUTH_TOKEN` so `npm ci` can install the private `@ansavva/design-system` from GitHub Packages |
| `humbugg/scripts/dev-setup.sh` | Humbugg service | .NET SDK 10 (ASP.NET Core backend, pinned by `humbugg/backend/global.json`) |

## Targets (both use Homebrew)

- **macOS** (developer machines) — `brew` runs as your normal user. Docker
  Desktop and Homebrew itself are the only interactive/GUI steps.
- **Linux** (this cloud sandbox / GitHub Actions) — Homebrew **refuses to run as
  root**, and these environments are root, so the script installs Homebrew into
  the default prefix `/home/linuxbrew/.linuxbrew` **owned by the non-root
  `ubuntu` user** and runs every `brew` call as that user via `sudo -u ubuntu`.
  The prefix `bin` is put on `PATH` for the current run and for future shells via
  `/etc/profile.d/homebrew.sh`, so root and CI agents can execute the tools.

Notes:
- **Terraform** and **tflint** are not in homebrew-core; the scripts install them
  from taps (`hashicorp/tap/terraform`, `terraform-linters/tap/tflint`) on every
  platform.
- **Stripe CLI** is installed from Stripe's official Homebrew tap with
  `brew install stripe/stripe-cli/stripe`.
- **.NET SDK**: Homebrew's `dotnet` formula currently ships exactly `10.0.302`,
  matching `humbugg/backend/global.json`, so the Humbugg script installs it via
  `brew install dotnet`.
- The tflint **AWS ruleset plugin** is installed best-effort (it downloads from
  GitHub releases, which some sandboxes block); tflint's bundled `terraform`
  ruleset still catches the common CI failures (e.g. `terraform_unused_declarations`).

## Usage

```bash
# From the repo root — install everything missing:
./scripts/dev-setup.sh
./humbugg/scripts/dev-setup.sh

# Report what's missing without installing anything:
./scripts/dev-setup.sh --check
./humbugg/scripts/dev-setup.sh --check
```

On Linux, if `brew`/its tools aren't on your `PATH` in a fresh non-login shell:

```bash
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
```

## GitHub Packages auth (`@ansavva/design-system`)

The `humbugg/` and `website/` frontends depend on the private
`@ansavva/design-system` package published to `npm.pkg.github.com`. Their
`.npmrc` reads the token from `${NODE_AUTH_TOKEN}`, and installing the package
requires a token with the **`read:packages`** scope (classic PAT) / **Packages:
Read-only** permission (fine-grained PAT). The default `GH_TOKEN` in CI/sandboxes
does not have it, so `npm ci` fails with `403 ... does not match expected scopes`.

`scripts/github-packages-auth.sh` resolves this idempotently:

```bash
# CI / sandbox: provide a read:packages PAT, then the script picks it up:
export GITHUB_PACKAGES_TOKEN=<pat-with-read:packages>
eval "$(./scripts/github-packages-auth.sh --export)"   # sets NODE_AUTH_TOKEN

# Developer machine with gh: adds the scope to your existing login:
./scripts/github-packages-auth.sh                       # runs `gh auth refresh -s read:packages`

# Verify only (no changes):
./scripts/github-packages-auth.sh --check
```

The script never writes a token into a committed file — the repo `.npmrc` uses the
`${NODE_AUTH_TOKEN}` env indirection. The only non-scriptable step is creating a
token with the scope in the first place (a GitHub UI / `gh` action); the script
does everything after that.

## Adding a new service

Give each service its own `<service>/scripts/dev-setup.sh` for stack-specific
runtimes (following `humbugg/scripts/dev-setup.sh`), and keep cross-cutting
tools in the shared `scripts/dev-setup.sh`.
