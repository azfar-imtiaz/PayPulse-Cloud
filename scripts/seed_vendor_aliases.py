#!/usr/bin/env python3
"""
One-time seed of the VendorAliases table with curated Tier 2 vendor-name mappings -
the genuine renames/branch-name/reordering cases that Tier 1's generic suffix-stripping
normalization (see lambda_layers/common/python/utils/vendor_normalization.py) can't
catch on its own, found via a live survey of RetailInvoices' distinct vendor_name values.

Each raw variant's compute_lookup_key() output becomes a NormalizedKey row pointing at
the chosen canonical name - idempotent, re-running just overwrites the same entries.

Usage:
    python3 scripts/seed_vendor_aliases.py --dry-run
    python3 scripts/seed_vendor_aliases.py --apply
"""

import argparse
import sys
from datetime import datetime, timezone

import boto3

sys.path.insert(0, "lambda_layers/common/python")
from utils.vendor_normalization import compute_lookup_key  # noqa: E402

REGION = "eu-west-1"
TABLE_NAME = "VendorAliases"

# canonical -> raw variants observed in RetailInvoices that should resolve to it
CURATED_ALIASES = {
    "Domino's": [
        "Domino's Pizza", "Domino's Eriksberg", "Domino's Gteborg Eriksberg",
        "Domino's Göteborg Eriksberg",
    ],
    "Parkering Göteborg": [
        "Gteborgs Stads Parkering AB",
    ],
    "Kinto": [
        "KintoShare",
    ],
    "Wise": [
        "TransferWise",
    ],
    "Zalando": [
        "Lounge by Zalando",
    ],
    "Humus Hus": [
        "Humus Hus Foodtruck",
    ],
    "Amazon Web Services": [
        "Amazonaws",
    ],
}


def build_entries():
    entries = []
    for canonical, variants in CURATED_ALIASES.items():
        for variant in variants:
            key = compute_lookup_key(variant)
            if not key:
                print(f"  [skip] could not compute a lookup key for {variant!r}", file=sys.stderr)
                continue
            entries.append((key, canonical, variant))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                       help="Print what would be written without writing (default)")
    mode.add_argument("--apply", action="store_true", help="Actually write the entries")
    args = parser.parse_args()
    apply_writes = args.apply

    entries = build_entries()
    print(f"[Seed] {len(entries)} alias entries to write:")
    for key, canonical, variant in entries:
        print(f"  {key!r:30s} -> {canonical!r:25s} (from {variant!r})")

    if not apply_writes:
        print("\nDry run - no writes performed. Re-run with --apply to write changes.")
        return

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
    created_at = datetime.now(timezone.utc).isoformat()

    for key, canonical, variant in entries:
        table.put_item(Item={
            "NormalizedKey": key,
            "CanonicalName": canonical,
            "Source": "seed",
            "CreatedAt": created_at,
        })

    print(f"\nWrote {len(entries)} alias entries to {TABLE_NAME}.")


if __name__ == "__main__":
    main()
