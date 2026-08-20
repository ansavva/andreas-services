---
name: github-access
description: >-
  Repo rule. GitHub access differs sharply between a Claude cloud session and a local
  machine — in the cloud the egress proxy denies almost every repo-scoped `gh` command
  and the GitHub MCP tools are the only working channel, while locally `gh` works
  normally. Read before running any `gh` command, debugging a GitHub 403, believing
  `gh auth status`, or trying to read or set Actions secrets or variables.
---

# GitHub: two environments, two channels

Which channel works depends on where the session runs. Establish that first —
every rule below forks on it.

```bash
curl -sS "$HTTPS_PROXY/__agentproxy/status"   # responds  → cloud session
                                              # no HTTPS_PROXY → local
```

| | Cloud session | Local machine |
|---|---|---|
| GitHub MCP tools | **use these** | available |
| `gh` for repo work | denied — see below | **use these** |
| `git` over HTTPS | works | works |
| Actions secrets / variables | unreachable | `gh secret`, `gh variable` |

## In the cloud, do GitHub work through MCP

`gh` is on `PATH` and authenticates, which makes the denials look like bugs. They
are policy. Measured on 2026-08-20 against `ansavva/andreas-services`:

| Command | Result |
|---|---|
| `gh api user`, `gh api rate_limit` | ✅ 200 |
| `gh api repos/OWNER/REPO` | ❌ 403 *GitHub access is not enabled for this session…* |
| `gh run list`, `gh workflow list` | ❌ 403 — same message |
| `gh repo view`, `gh pr list` | ❌ 403 *This GraphQL query is not enabled…* |
| `gh secret list`, `gh variable list` | ❌ 403 *…Actions path is not permitted through this proxy* |
| `git ls-remote`, fetch, push | ✅ credentials injected by the proxy |

So `gh` reaches exactly the endpoints that tell you nothing. Anything repo-scoped
— PRs, issues, workflows, runs, file contents, reviews — goes through the
`mcp__github__*` tools, which are separately authorized and work fine. Load them
with `ToolSearch` (`select:mcp__github__get_me,…`); they are deferred, so a
missing schema is a not-yet-loaded tool, not a missing capability.

## Three different 403s, none meaning your setup is broken

Read the message, not just the status code:

- **"GitHub access is not enabled for this session. An org admin must connect the
  Claude GitHub App"** — the canned reply for *any* direct REST call to `/repos/*`.
  It is not a diagnosis. The App connection can be perfectly healthy and this still
  appears. Confirm with `mcp__github__get_me` plus one repo-scoped MCP call before
  believing a word of it.
- **"This GraphQL query is not enabled for this session"** — only a pinned set of
  PR-review operations is allowed on GraphQL. Kills most porcelain `gh` subcommands,
  which prefer GraphQL.
- **"Access to this GitHub Actions path is not permitted through this proxy"** —
  `/actions/secrets`, `/actions/secrets/public-key`, `/actions/variables`. The
  credential-administration surface, fenced off deliberately.

`/root/.ccr/README.md` on any of them: *do not retry or route around a 403 — report
the blocked host.* Follow that.

## `GH_TOKEN` is decorative in the cloud, and `gh auth status` lies

The proxy strips the `Authorization` header and substitutes its own GitHub App
identity. Your PAT never reaches GitHub. Proof, re-runnable in seconds:

```bash
curl -sS -H "Authorization: token ghp_deadbeefdeadbeefdeadbeefdeadbeef0000" \
  https://api.github.com/user --jq .login   # → ansavva
curl -sS https://api.github.com/user | head -c 40   # no header at all → ansavva
```

A garbage token and no token authenticate identically. Consequences:

- `gh auth status` reports **"The token in GH_TOKEN is invalid."** It is not. The
  injected App identity returns an empty `X-Oauth-Scopes` header and `gh` concludes
  the token is bad. **Never report this as an expired or invalid token, and never
  ask for a fresh PAT on the strength of it** — rotating the token changes nothing,
  because the token is discarded before the request leaves the container.
- Verify identity with `gh api user` or `mcp__github__get_me` instead.

## Secret values are unreadable everywhere — cloud and local alike

GitHub Actions secrets are write-only by design. No API endpoint returns a value;
`gh secret` has only `list` (names), `set`, `delete`. This is not a permissions
problem and no access change fixes it.

| | Read a value | List names | Create / update |
|---|---|---|---|
| Cloud session | impossible | ❌ proxy 403 | ❌ no MCP tool exists |
| Local machine | impossible | ✅ `gh secret list` | ✅ `gh secret set` |

The GitHub MCP server ships **no** secrets or variables tool — the only
secret-adjacent one is `run_secret_scanning`, which scans content you hand it for
leaked credentials. Don't go looking for a management tool; it isn't there.

In a cloud session, setting a secret is the user's job: repo **Settings → Secrets
and variables → Actions**. What you *can* do is read the workflow YAML and tell
them exactly which `secrets.*` and `vars.*` names it expects, and read job logs via
`mcp__github__get_job_logs` to spot a missing or stale one.

## There is no knob to turn

Don't spend a session hunting for one. The policy is enforced at a remote
egress proxy, outside the container:

- `/root/.ccr/` holds CA material only — `README.md`, `agent-proxy-ca.crt`,
  `ca-bundle.crt`, `java-truststore.p12`. No allowlist, no rules file. The local
  proxy is a tunnel, not the decider.
- `.claude/settings.json` governs **tool permissions**, not network reach.
  Allowlisting `gh secret set` there only buys the right to run a command that
  still 403s.
- The environment's network policy is host-level and already permits
  `api.github.com` — everything else there succeeds. The path denials are a
  separate layer.

If a blocked path genuinely matters, report it to Anthropic support rather than
working around it.

## Locally, none of this applies

A real PAT in `GH_TOKEN`, no proxy, no path guards: `gh` behaves as documented,
`gh auth status` is truthful, and `gh secret set` / `gh variable set` work. Prefer
`gh` locally — it is faster and less roundabout than MCP for the same job. Secret
values remain unreadable, because that part was never about the environment.
