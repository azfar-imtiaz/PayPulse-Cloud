#!/usr/bin/env python3
"""
One-time retroactive cleanup for duplicate RetailInvoices rows.

Backfills discovery_source on legacy rows (the old vendor-driven fetch_retail_invoices
pipeline never wrote this field), then finds duplicate invoices WITHIN the same
discovery_source only - legacy-vs-sweep duplicates are deliberately left alone here and
handled by the `exclude` query param on GET invoices instead (see
lambdas/invoices/get_invoices/main.py), since the legacy pipeline's rows are headed for
eventual deletion and merging across pipelines would leave fragile provenance for that.

Three grouping passes per (UserID, discovery_source) bucket:
  A. (sub_type, order_id) - the common case
  B. exact s3_path match, for rows with no order_id
  C. (vendor_name, invoice_date day) fallback, for rows with no order_id and no exact
     s3_path match (e.g. a recurring subscription where each month is a distinct email)

For each duplicate group, the most-recently-created row is kept canonical; the rest are
marked is_duplicate=True / duplicate_of_invoice_id=<canonical> via the same update_item
call mark_duplicate_invoice's Lambda uses - not invoked through the deployed endpoint
(extra auth complexity for no benefit; this script already has direct table access).
Rows whose total_amount doesn't match the canonical's are skipped and reported separately
rather than force-merged.

The canonical row's vendor_order_key is also rewritten to the new discovery_source-scoped
format, so a future email for an already-merged order attaches to the canonical row
instead of inserting a third duplicate (see compute_vendor_order_key in dynamodb_utils.py).

Usage:
    python3 scripts/retroactive_merge_duplicate_retail_invoices.py --dry-run
    python3 scripts/retroactive_merge_duplicate_retail_invoices.py --apply
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

sys.path.insert(0, "lambda_layers/common/python")
from utils.vendor_normalization import resolve_vendor_name  # noqa: E402

REGION = "eu-west-1"
TABLE_NAME = "RetailInvoices"
VENDOR_ALIASES_TABLE_NAME = "VendorAliases"
LEGACY_DISCOVERY_SOURCE = "legacy-vendor-pipeline"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def snapshot_items(items, path):
    """Dump full pre-write item state to a local JSON file, so every write this script
    makes has an exact, scriptable undo (restore via BatchWriteItem put_item) independent
    of DynamoDB's 35-day point-in-time-recovery window."""
    with open(path, "w") as f:
        json.dump(items, f, cls=_DecimalEncoder, indent=2)
    print(f"\n[Snapshot] Wrote pre-write state of {len(items)} row(s) to {path}")


def scan_all_items(table):
    items = []
    kwargs = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def backfill_discovery_source(table, items, apply_writes):
    """Set discovery_source=legacy-vendor-pipeline on every row currently missing it."""
    to_backfill = [item for item in items if "discovery_source" not in item]
    print(f"\n[Backfill] {len(to_backfill)} rows missing discovery_source -> "
          f"'{LEGACY_DISCOVERY_SOURCE}'")

    for item in to_backfill:
        item["discovery_source"] = LEGACY_DISCOVERY_SOURCE
        if apply_writes:
            try:
                table.update_item(
                    Key={"UserID": item["UserID"], "InvoiceID": item["InvoiceID"]},
                    UpdateExpression="SET discovery_source = :src",
                    ConditionExpression=Attr("discovery_source").not_exists(),
                    ExpressionAttributeValues={":src": LEGACY_DISCOVERY_SOURCE},
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                print(f"  [skip] {item['InvoiceID']} got a discovery_source concurrently - leaving as-is")

    return to_backfill


def normalize_vendor_names(table, aliases_table, items, apply_writes):
    """Resolve every row's vendor_name through the Tier 1/Tier 2 normalizer (see
    resolve_vendor_name), mutating in-memory so grouping benefits within this same run.
    Rows with no order_id also get their vendor_order_key rewritten, since that key's
    fallback branch embeds vendor_name directly."""
    renamed = []
    for item in items:
        old_name = item.get("vendor_name")
        if not old_name:
            continue
        new_name = resolve_vendor_name(old_name, aliases_table)
        if new_name == old_name:
            continue

        renamed.append({"InvoiceID": item["InvoiceID"], "old": old_name, "new": new_name})
        item["vendor_name"] = new_name

        if apply_writes:
            try:
                table.update_item(
                    Key={"UserID": item["UserID"], "InvoiceID": item["InvoiceID"]},
                    UpdateExpression="SET vendor_name = :new",
                    ConditionExpression="vendor_name = :old",
                    ExpressionAttributeValues={":new": new_name, ":old": old_name},
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                print(f"  [skip] {item['InvoiceID']} vendor_name changed concurrently - leaving as-is")
                continue

            if not item.get("order_id"):
                new_key = compute_new_vendor_order_key(item)
                if new_key and item.get("vendor_order_key") != new_key:
                    try:
                        table.update_item(
                            Key={"UserID": item["UserID"], "InvoiceID": item["InvoiceID"]},
                            UpdateExpression="SET vendor_order_key = :key",
                            ConditionExpression="attribute_not_exists(is_duplicate) OR is_duplicate = :false",
                            ExpressionAttributeValues={":key": new_key, ":false": False},
                        )
                    except ClientError as e:
                        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                            raise
                        print(f"  [skip] {item['InvoiceID']} became a duplicate concurrently - not rewriting its vendor_order_key")

    print(f"\n[Vendor normalization] {len(renamed)} row(s) renamed:")
    for r in renamed:
        print(f"  {r['InvoiceID']}: {r['old']!r} -> {r['new']!r}")

    return renamed


def group_duplicates(items):
    """
    Three-pass grouping, scoped to (UserID, discovery_source) so cross-pipeline rows can
    never land in the same group. Returns a list of groups (each a list of 2+ items).
    """
    groups = []

    by_user_source = defaultdict(list)
    for item in items:
        by_user_source[(item["UserID"], item["discovery_source"])].append(item)

    for bucket_items in by_user_source.values():
        remaining = list(bucket_items)

        # Items with a real order_id are never candidates for Pass B/C, even if Pass A
        # finds no match for them - a unique, present order_id already proves they're
        # distinct transactions, so they must not fall through to the looser fallbacks.
        has_order_id = [item for item in remaining if item.get("order_id")]
        no_order_id = [item for item in remaining if not item.get("order_id")]

        # Pass A: (sub_type, order_id)
        by_order = defaultdict(list)
        for item in has_order_id:
            by_order[(item["sub_type"], item["order_id"])].append(item)
        for group in by_order.values():
            if len(group) > 1:
                groups.append(group)

        # Pass B: exact s3_path, only for rows with no order_id at all
        by_path = defaultdict(list)
        still_remaining = []
        for item in no_order_id:
            s3_path = item.get("s3_path")
            if s3_path:
                by_path[s3_path].append(item)
            else:
                still_remaining.append(item)
        for group in by_path.values():
            if len(group) > 1:
                groups.append(group)
            else:
                still_remaining.extend(group)

        # Pass C: (vendor_name, invoice_date day) fallback, only for rows with no
        # order_id and no exact s3_path match
        by_vendor_date = defaultdict(list)
        for item in still_remaining:
            vendor_name = item.get("vendor_name")
            invoice_date = item.get("invoice_date")
            if vendor_name and invoice_date:
                by_vendor_date[(item["sub_type"], vendor_name, invoice_date[:10])].append(item)
        for group in by_vendor_date.values():
            if len(group) > 1:
                groups.append(group)

    return groups


def pick_canonical(group):
    """Most-recent created_at wins, excluding rows already marked is_duplicate; tiebreak on
    smallest InvoiceID. Returns None if every row in the group is already a duplicate."""
    candidates = [item for item in group if not item.get("is_duplicate")]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.get("created_at", ""), item["InvoiceID"]))[-1]


def compute_new_vendor_order_key(item):
    """Mirrors the post-fix compute_vendor_order_key in dynamodb_utils.py."""
    discovery_source = item["discovery_source"]
    sub_type = item.get("sub_type")
    order_id = item.get("order_id")
    vendor_name = item.get("vendor_name")
    invoice_date = item.get("invoice_date")

    if order_id:
        return f"{discovery_source}_{sub_type}_{order_id}"
    if invoice_date:
        return f"{discovery_source}_{vendor_name}_{invoice_date[:10]}"
    return None


def apply_merge(table, group, apply_writes, merged_report, review_report, skipped_report):
    canonical = pick_canonical(group)
    if canonical is None:
        skipped_report.append({
            "reason": "all rows already is_duplicate",
            "invoice_ids": [item["InvoiceID"] for item in group],
        })
        return
    canonical_amount = canonical.get("total_amount")

    for item in group:
        if item["InvoiceID"] == canonical["InvoiceID"]:
            continue
        if item.get("is_duplicate"):
            continue  # already merged in a prior run

        if item.get("total_amount") != canonical_amount:
            review_report.append({
                "user_id": item["UserID"],
                "canonical_invoice_id": canonical["InvoiceID"],
                "mismatched_invoice_id": item["InvoiceID"],
                "canonical_amount": canonical_amount,
                "mismatched_amount": item.get("total_amount"),
                "sub_type": item.get("sub_type"),
                "discovery_source": item["discovery_source"],
            })
            continue

        merged_report.append({
            "user_id": item["UserID"],
            "canonical_invoice_id": canonical["InvoiceID"],
            "duplicate_invoice_id": item["InvoiceID"],
            "sub_type": item.get("sub_type"),
            "discovery_source": item["discovery_source"],
        })

        if apply_writes:
            # Condition guards against a concurrent write (e.g. a manual mark-duplicate
            # call, or the live sweep pipeline) flipping this row's is_duplicate state
            # between the scan at the top of this script and this write.
            try:
                table.update_item(
                    Key={"UserID": item["UserID"], "InvoiceID": item["InvoiceID"]},
                    UpdateExpression="SET is_duplicate = :true, duplicate_of_invoice_id = :canonical_id",
                    ConditionExpression="attribute_not_exists(is_duplicate) OR is_duplicate = :false",
                    ExpressionAttributeValues={
                        ":true": True,
                        ":false": False,
                        ":canonical_id": canonical["InvoiceID"],
                    },
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                print(f"  [skip] {item['InvoiceID']} changed concurrently - leaving as-is")

    new_key = compute_new_vendor_order_key(canonical)
    if apply_writes and new_key and canonical.get("vendor_order_key") != new_key:
        try:
            table.update_item(
                Key={"UserID": canonical["UserID"], "InvoiceID": canonical["InvoiceID"]},
                UpdateExpression="SET vendor_order_key = :key",
                ConditionExpression="attribute_not_exists(is_duplicate) OR is_duplicate = :false",
                ExpressionAttributeValues={":key": new_key, ":false": False},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            print(f"  [skip] {canonical['InvoiceID']} became a duplicate concurrently - not rewriting its vendor_order_key")


def print_report(title, rows):
    print(f"\n[{title}] {len(rows)} rows")
    for row in rows:
        print(f"  {row}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                       help="Print what would change without writing (default)")
    mode.add_argument("--apply", action="store_true", help="Actually perform the writes")
    parser.add_argument("--normalize-vendors", action="store_true",
                         help="Also resolve vendor_name through the Tier 1/Tier 2 normalizer "
                              "before grouping, so inconsistent naming doesn't hide duplicates")
    args = parser.parse_args()
    apply_writes = args.apply

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    print(f"Scanning {TABLE_NAME}...")
    items = scan_all_items(table)
    print(f"Scanned {len(items)} total rows.")

    if apply_writes:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_items(items, f"retail_invoices_pre_merge_snapshot_{timestamp}.json")

    backfill_discovery_source(table, items, apply_writes)

    if args.normalize_vendors:
        aliases_table = dynamodb.Table(VENDOR_ALIASES_TABLE_NAME)
        normalize_vendor_names(table, aliases_table, items, apply_writes)

    groups = group_duplicates(items)
    print(f"\n[Grouping] Found {len(groups)} duplicate group(s) "
          f"({sum(len(g) for g in groups)} rows involved).")
    for group in groups:
        print(f"  user={group[0]['UserID']} source={group[0]['discovery_source']} "
              f"sub_type={group[0].get('sub_type')} "
              f"invoice_ids={[item['InvoiceID'] for item in group]} "
              f"amounts={[item.get('total_amount') for item in group]} "
              f"created_at={[item.get('created_at') for item in group]}")

    merged_report = []
    review_report = []
    skipped_report = []
    for group in groups:
        apply_merge(table, group, apply_writes, merged_report, review_report, skipped_report)

    print_report("Merged" if apply_writes else "Would merge", merged_report)
    print_report("Needs manual review (amount mismatch)", review_report)
    print_report("Skipped (all rows already duplicates)", skipped_report)

    if not apply_writes:
        print("\nDry run - no writes performed. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
