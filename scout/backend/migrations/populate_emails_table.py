"""
Idempotent migration: populate scout-emails from existing scout-events data.

For each unique email_id in scout-events that carries legacy email metadata
fields, creates one record in scout-emails, then removes the redundant fields
from scout-events. Safe to run on every deployment — exits immediately when
there is nothing to migrate.

Table names are derived from SCOUT_TABLE_SUFFIX (empty for prod,
"-pr-N" for PR previews). Override with --events-table / --emails-table.

Usage:
    SCOUT_TABLE_SUFFIX="" python populate_emails_table.py [--dry-run]
"""

import argparse
import os
import sys
from collections import defaultdict

import boto3

EMAIL_FIELDS = {"email_subject", "email_sender", "source_email_date", "image_url", "created_at"}


def scan_all(table):
    """Paginate through a full table scan and return all items."""
    items = []
    result = table.scan()
    items.extend(result.get("Items", []))
    while "LastEvaluatedKey" in result:
        result = table.scan(ExclusiveStartKey=result["LastEvaluatedKey"])
        items.extend(result.get("Items", []))
    return items


def build_email_records(events):
    """
    Group events by email_id and produce one scout-emails record per email.
    Uses the first event seen per email_id as the source of email metadata.
    Counts events per email for event_count.
    """
    groups = defaultdict(list)
    for event in events:
        email_id = event.get("email_id")
        if email_id:
            groups[email_id].append(event)

    records = []
    for email_id, group in groups.items():
        first = group[0]
        records.append({
            "email_id": email_id,
            "email_subject": first.get("email_subject", ""),
            "email_sender": first.get("email_sender", ""),
            "source_email_date": first.get("source_email_date", ""),
            "image_url": first.get("image_url", ""),
            "processed_at": first.get("created_at", ""),
            "event_count": len(group),
        })
    return records


def batch_write(table, items):
    """Write items to DynamoDB using BatchWriteItem (25 items per call)."""
    for i in range(0, len(items), 25):
        batch = items[i:i + 25]
        with table.batch_writer() as writer:
            for item in batch:
                writer.put_item(Item=item)


def remove_email_fields_from_events(table, events, dry_run):
    """
    Remove the now-redundant email metadata fields from each scout-events item.
    Only removes fields that actually exist on the item.
    """
    updated = 0
    skipped = 0
    for event in events:
        fields_present = [f for f in EMAIL_FIELDS if f in event]
        if not fields_present:
            skipped += 1
            continue

        remove_expr = "REMOVE " + ", ".join(f"#{f}" for f in fields_present)
        expr_names = {f"#{f}": f for f in fields_present}

        if dry_run:
            print(f"  [dry-run] Would remove {fields_present} from event {event['event_id']}")
        else:
            table.update_item(
                Key={"event_id": event["event_id"]},
                UpdateExpression=remove_expr,
                ExpressionAttributeNames=expr_names,
            )
        updated += 1

    return updated, skipped


def main():
    parser = argparse.ArgumentParser(description="Migrate email metadata to scout-emails table")
    parser.add_argument("--events-table", help="Override events table name")
    parser.add_argument("--emails-table", help="Override emails table name")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    suffix = os.environ.get("SCOUT_TABLE_SUFFIX", "")
    events_table_name = args.events_table or f"scout-events{suffix}"
    emails_table_name = args.emails_table or f"scout-emails{suffix}"

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    events_table = dynamodb.Table(events_table_name)
    emails_table = dynamodb.Table(emails_table_name)

    print(f"Scanning {events_table_name}...")
    events = scan_all(events_table)
    print(f"Found {len(events)} events")

    email_records = build_email_records(events)
    print(f"Found {len(email_records)} unique emails")

    if not email_records:
        print("Nothing to migrate.")
        sys.exit(0)

    for rec in email_records:
        print(f"  {rec['email_id'][:12]}... | {rec['email_subject'][:50]} | {rec['event_count']} events")

    if args.dry_run:
        print("\n[dry-run] Would write the above records to", emails_table_name)
    else:
        print(f"\nWriting {len(email_records)} records to {emails_table_name}...")
        batch_write(emails_table, email_records)
        print("Done.")

    print(f"\nRemoving email fields from {events_table_name} items...")
    updated, skipped = remove_email_fields_from_events(events_table, events, args.dry_run)
    print(f"Updated {updated} items, skipped {skipped} (already clean)")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
