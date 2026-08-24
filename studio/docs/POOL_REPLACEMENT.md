# Replacing the studio pool — what dies, what does not, and how to get back in

`studio/infra/modules/auth/main.tf` carries `username_configuration`, which AWS
accepts only at pool creation. Any change to it destroys the pool and every
account in it. This is the runbook for that, written when #374 was applied.

It is also the runbook for any future pool replacement, because the recovery is
the same whatever forced it.

## What a pool replacement destroys

Two things, and neither of them is media:

1. **Every account.** New pool, new accounts, new `sub` for each.
2. **The link between an account and its library** — but only in the sense that
   the link now points at a `sub` that no longer exists. The rows themselves
   survive; they are simply addressed to nobody.

## What it cannot touch

Measured against the real table before the #374 apply, not inferred:

| Item type | Count | References a `sub`? |
| --- | --- | --- |
| `NODE#…` | 416 | no |
| `CHAR#…` | 36 | no |
| `LIB#…` | 4 | no |
| `USER#…` | 2 | **yes — this is the whole of it** |

Every item's full JSON was searched for both subs; nothing outside `USER#`
mentioned one. The media bucket was searched the same way: **zero** keys contain
a sub. Objects are addressed by character and project UUID, and those are
independent of who is signed in.

So the library — every character, every project, every run, scene and movie, and
every byte in S3 — is untouched by a pool replacement. What breaks is the ability
to *reach* it, and that is two rows.

## Before the apply

```bash
# 1. A named snapshot, independent of PITR.
aws dynamodb create-backup --table-name studio-prod-catalog \
  --backup-name "studio-prod-catalog-pre-<reason>"

# 2. The rows you are about to orphan — this is where the library id lives.
aws dynamodb scan --table-name studio-prod-catalog \
  --filter-expression "begins_with(pk, :u)" \
  --expression-attribute-values '{":u":{"S":"USER#"}}' \
  > memberships-before.json
```

Point-in-time recovery is already enabled on `studio-prod-catalog` with 35 days
of retention, so a restore to any second is available without the snapshot. Take
the snapshot anyway: PITR retention is a rolling window, and a named backup is
the one you can still find in three months.

**The library id is the only thing you actually need.** Keep it somewhere that is
not the table you are about to change.

## After the apply

The deploy does most of it. `deploy-infra` replaces the pool and its client and
writes the new ids to SSM; `update-lambda` picks up the pool id; the frontend is
rebuilt with the new client id in the same run.

**The smoke account needs nothing.** `scripts/prod-seed-smoke.py` runs in the
same deploy, creates it in the new pool, and writes its membership row. That is
half the recovery done before anyone looks.

**A human account is one command — but pass the ROLE as well:**

```bash
STUDIO_LIBRARY=lib-<the id from memberships-before.json> \
STUDIO_ROLE=<the role from memberships-before.json> \
  ./studio/scripts/create-user.sh
```

Email and password come from `~/.config/andreas-services/studio/prod.env`. The
script creates the account and calls `add-member.sh` to grant the library in one
step — without `STUDIO_LIBRARY` it creates an account that signs in and sees
nothing, and says so.

**`STUDIO_ROLE` defaults to `member`, and that is not what an owner had.** This
runbook omitted it on the first real use and quietly restored an owner as a
member; the difference is real — `role` is what
`routes/support.py:owner_of` checks before allowing a node to be transferred
into or out of a library. It is the one field the default gets wrong, so read it
back out of `memberships-before.json` rather than trusting the default.

A wrong role is now correctable in place: `add-member.sh` converges it, and
`--no-converge` opts out. It refused to until this was found — the only way back
to `owner` was deleting the row by hand first.

Verify before believing it:

```bash
# The new sub holds exactly one membership, on the right library.
aws dynamodb query --table-name studio-prod-catalog \
  --key-condition-expression "pk = :p" \
  --expression-attribute-values '{":p":{"S":"USER#<new-sub>"}}'
```

## Then clean up the orphans

The old `USER#<old-sub>` rows are still there, pointing at subs that no longer
exist. They are inert — every route resolves the caller's library from the
caller's *own* rows, so a row addressed to a dead sub is unreachable — but they
read like configuration, and the next person to scan this table will wonder
which account they belong to.

```bash
aws dynamodb delete-item --table-name studio-prod-catalog \
  --key '{"pk":{"S":"USER#<old-sub>"},"sk":{"S":"LIB#<lib>"}}'
```

Do this **after** confirming the new membership works, not before. The old row is
the last written record of which library the account owned.

## What this costs while it is happening

Sign-in is broken from the moment the pool is replaced until `create-user.sh`
runs. There is no way to shorten that: the account cannot exist before the pool
does. Nothing is queued or lost in the window — the API simply refuses
unauthenticated requests, which is what it does anyway.
