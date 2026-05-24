"""
Idempotent migration: backfill region/category/status taxonomy.

Brings pre-taxonomy data up to the new model so the live site does not go
dark under the new approval + classification gates:

  - existing events get status="published" (they were already live),
  - sender_key is derived and stamped on every event and email,
  - a "nyc" region is seeded in scout-regions,
  - each distinct sender is recorded in scout-senders as classified -> ["nyc"],
  - existing events/emails get regions=["nyc"].

Categories are left empty for existing events (they gain categories on future
processing). Safe to run repeatedly — items already carrying the new fields
are skipped.

Table names are derived from SCOUT_TABLE_SUFFIX (empty for prod, "-pr-N" for
PR previews).

Usage:
    SCOUT_TABLE_SUFFIX="" python backfill_taxonomy.py [--dry-run] [--region us-east-1]
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

import boto3

DEFAULT_REGION_SLUG = "nyc"
DEFAULT_REGION_NAME = "New York City"

_ADDR_RE = re.compile(r"<([^>]+)>")


def normalize_sender(from_header):
    """Mirror of taxonomy.normalize_sender (kept local so this script is standalone)."""
    raw = (from_header or "").strip()
    match = _ADDR_RE.search(raw)
    addr = match.group(1) if match else raw
    return addr.strip().lower(), (raw or addr)


def scan_all(table):
    items = []
    result = table.scan()
    items.extend(result.get("Items", []))
    while "LastEvaluatedKey" in result:
        result = table.scan(ExclusiveStartKey=result["LastEvaluatedKey"])
        items.extend(result.get("Items", []))
    return items


def main():
    parser = argparse.ArgumentParser(description="Backfill region/category/status taxonomy")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    suffix = os.environ.get("SCOUT_TABLE_SUFFIX", "")
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    events_table = dynamodb.Table(f"scout-events{suffix}")
    emails_table = dynamodb.Table(f"scout-emails{suffix}")
    senders_table = dynamodb.Table(f"scout-senders{suffix}")
    regions_table = dynamodb.Table(f"scout-regions{suffix}")

    now_iso = datetime.now(timezone.utc).isoformat()
    default_regions = [DEFAULT_REGION_SLUG]

    # 1. Seed the default region.
    print(f"Seeding region '{DEFAULT_REGION_SLUG}'...")
    if not args.dry_run:
        regions_table.put_item(Item={
            "slug": DEFAULT_REGION_SLUG,
            "name": DEFAULT_REGION_NAME,
            "created_at": now_iso,
        })

    # 2. Backfill emails: sender_key + regions, and collect distinct senders.
    emails = scan_all(emails_table)
    print(f"Scanning {len(emails)} emails...")
    senders = {}  # sender_key -> display
    for em in emails:
        sender_key, display = normalize_sender(em.get("email_sender", ""))
        if sender_key:
            senders.setdefault(sender_key, display)
        needs = "sender_key" not in em or "regions" not in em
        if needs and not args.dry_run:
            emails_table.update_item(
                Key={"email_id": em["email_id"]},
                UpdateExpression="SET sender_key = :sk, #r = :r",
                ExpressionAttributeNames={"#r": "regions"},
                ExpressionAttributeValues={":sk": sender_key, ":r": default_regions},
            )

    # 3. Record each distinct sender as classified -> default region.
    print(f"Recording {len(senders)} classified senders...")
    for sender_key, display in senders.items():
        if not args.dry_run:
            senders_table.put_item(Item={
                "sender_key": sender_key,
                "display_sender": display,
                "regions": default_regions,
                "status": "classified",
                "first_seen": now_iso,
                "updated_at": now_iso,
            })

    # 4. Backfill events: status + regions + categories + sender_key.
    events = scan_all(events_table)
    print(f"Scanning {len(events)} events...")
    updated = 0
    for ev in events:
        if all(k in ev for k in ("status", "regions", "categories", "sender_key")):
            continue
        # Resolve sender_key via the joined email record when available.
        sender_key = ev.get("sender_key", "")
        if not sender_key:
            email = emails_table.get_item(Key={"email_id": ev.get("email_id", "")}).get("Item", {})
            sender_key, _ = normalize_sender(email.get("email_sender", ""))
        if args.dry_run:
            print(f"  [dry-run] event {ev['event_id'][:12]}... -> published, regions={default_regions}")
        else:
            events_table.update_item(
                Key={"event_id": ev["event_id"]},
                UpdateExpression=(
                    "SET #s = if_not_exists(#s, :pub), #r = if_not_exists(#r, :reg), "
                    "categories = if_not_exists(categories, :cat), "
                    "sender_key = if_not_exists(sender_key, :sk)"
                ),
                ExpressionAttributeNames={"#s": "status", "#r": "regions"},
                ExpressionAttributeValues={
                    ":pub": "published",
                    ":reg": default_regions,
                    ":cat": [],
                    ":sk": sender_key,
                },
            )
        updated += 1

    print(f"Backfilled {updated} events.")
    print("Dry run — no writes performed." if args.dry_run else "Migration complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()
