# Developer / CI toolchain scripts

Idempotent bootstrap scripts that install the tools needed to build and test
this monorepo. Safe to re-run: every tool is checked before install, and
Homebrew (macOS) / vendor installers (Ubuntu) are used so an already-installed
dependency is never reinstalled.

Two layers (see `CLAUDE.md` → "Install scripts"):

| Script | Scope | Installs |
|---|---|---|
| `scripts/dev-setup.sh` | Shared base (all services) | Terraform, tflint (+ pinned AWS ruleset, best-effort), AWS CLI, Node.js, jq, zip (+ Docker check) |
| `scripts/github-packages-auth.sh` | Shared base (all frontends) | Ensures a `read:packages` token is available as `NODE_AUTH_TOKEN` so `npm ci` can install the private `@ansavva/design-system` from GitHub Packages |
| `humbugg/scripts/dev-setup.sh` | Humbugg service | .NET SDK 10 (ASP.NET Core backend, pinned by `humbugg/backend/global.json`) |

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

## Targets

- **macOS** (developer machines) — installs via **Homebrew** (`brew install …`).
  Docker Desktop and Homebrew itself are the only interactive/GUI steps.
- **Ubuntu** (this cloud sandbox / GitHub Actions) — installs via `apt` plus the
  official vendor installers (HashiCorp release zips, `dotnet-install.sh`,
  NodeSource, AWS CLI v2 bundle).

## Usage

```bash
# From the repo root — install everything missing:
./scripts/dev-setup.sh
./humbugg/scripts/dev-setup.sh

# Report what's missing without installing anything:
./scripts/dev-setup.sh --check
./humbugg/scripts/dev-setup.sh --check
```

On Ubuntu the .NET SDK is installed system-wide to `/usr/local/share/dotnet`
and symlinked to `/usr/local/bin/dotnet`. If `dotnet` is not on your PATH in a
fresh shell, add:

```bash
export PATH="/usr/local/share/dotnet:$PATH"
```

## Adding a new service

Give each service its own `<service>/scripts/dev-setup.sh` for stack-specific
runtimes (following `humbugg/scripts/dev-setup.sh`), and keep cross-cutting
tools in the shared `scripts/dev-setup.sh`.
