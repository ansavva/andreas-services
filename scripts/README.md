# Developer / CI toolchain scripts

Idempotent bootstrap scripts that install the tools needed to build and test
this monorepo. Safe to re-run: every tool is checked before install, and
Homebrew (macOS) / vendor installers (Ubuntu) are used so an already-installed
dependency is never reinstalled.

Two layers (see `CLAUDE.md` → "Install scripts"):

| Script | Scope | Installs |
|---|---|---|
| `scripts/dev-setup.sh` | Shared base (all services) | Terraform, AWS CLI, Node.js, jq, zip (+ Docker check) |
| `humbugg/scripts/dev-setup.sh` | Humbugg service | .NET SDK 10 (ASP.NET Core backend, pinned by `humbugg/backend/global.json`) |

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
