#!/usr/bin/env python3
"""
One-time backfill that normalizes RetailInvoices.currency to ISO 4217 codes and adds
total_amount_sek / fx_rate / fx_rate_date / fx_source using ECB reference rates (see
utils/fx_utils.py). The original value is kept in currency_raw; rows already carrying
total_amount_sek are skipped, and currencies ECB doesn't publish are normalized but left
unconverted. Rows with no currency are re-parsed with the current Gemini prompt first; if
that still yields nothing, SEK is used (recorded in currency_source).
The re-parse needs GEMINI_API_KEY in the environment and is cached in --reparse-cache.

Usage:
    python3 scripts/backfill_retail_invoice_sek_amounts.py --dry-run
    python3 scripts/backfill_retail_invoice_sek_amounts.py --apply
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, "lambda_layers/common/python")
from utils.fx_utils import DEFAULT_CURRENCY, normalize_currency, convert_to_sek  # noqa: E402

REGION = "eu-west-1"
TABLE_NAME = "RetailInvoices"
BUCKET_NAME = "rental-invoices-bucket"
REPARSE_CACHE_PATH = "retail_fx_reparse_cache.json"


def reparse_missing_currencies(items, cache_path):
    """Re-run the (updated) Gemini parser on every row with no currency and record what it returns,
    cached to cache_path so --apply reuses exactly the results reviewed in the dry run."""
    try:
        with open(cache_path) as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}

    missing = [item for item in items if item.get("currency") is None and "total_amount_sek" not in item]
    to_parse = [item for item in missing if item["InvoiceID"] not in cache]
    if to_parse:
        sys.path.insert(0, "lambda_layers/gemini_parsers/python")
        from parser_factory import get_parser_for_subtype  # noqa: E402
        s3 = boto3.client("s3", region_name=REGION)
        gemini_api_key = os.environ["GEMINI_API_KEY"]

        for n, item in enumerate(to_parse, 1):
            key = item.get("s3_path")
            entry = {"gemini_currency": None, "gemini_total_amount": None, "error": None}
            try:
                html = s3.get_object(Bucket=BUCKET_NAME, Key=key)["Body"].read().decode("utf-8")
                pdf_bytes = None
                try:
                    pdf_bytes = s3.get_object(Bucket=BUCKET_NAME, Key=key[:-len(".html")] + ".pdf")["Body"].read()
                except ClientError as e:
                    if e.response["Error"]["Code"] != "NoSuchKey":
                        raise
                parser = get_parser_for_subtype(item["sub_type"], gemini_api_key)
                parsed = parser.parse_invoice(html, parser.create_extraction_prompt(html, item.get("vendor_name") or ""),
                                              pdf_bytes=pdf_bytes)
                if parsed:
                    entry["gemini_currency"] = parsed.get("currency")
                    entry["gemini_total_amount"] = parsed.get("total_amount")
                else:
                    entry["error"] = "parser returned no data"
            except Exception as e:
                entry["error"] = f"{type(e).__name__}: {e}"
            cache[item["InvoiceID"]] = entry
            print(f"  [re-parse {n}/{len(to_parse)}] {item['InvoiceID']}: {entry}")

        with open(cache_path, "w") as f:
            json.dump(cache, f, cls=_DecimalEncoder, indent=2)
        print(f"[Re-parse] Cached {len(to_parse)} new result(s) to {cache_path}")

    return {item["InvoiceID"]: cache[item["InvoiceID"]] for item in missing}


def resolve_currency(item, reparsed):
    """Return (iso_currency, currency_source) for a row: stored value, else Gemini re-parse, else SEK."""
    if item.get("currency") is not None:
        return normalize_currency(item["currency"]), "stored"
    gemini_currency = (reparsed.get(item["InvoiceID"]) or {}).get("gemini_currency")
    if gemini_currency:
        iso = normalize_currency(gemini_currency)
        if iso:
            return iso, "reparse"
    return DEFAULT_CURRENCY, "default"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def scan_all_items(table):
    items, kwargs = [], {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def plan_updates(items, reparsed):
    """Compute the per-row update for every row not yet backfilled, plus buckets for reporting."""
    updates, unconvertible, unrecognized, skipped = [], [], [], []
    for item in items:
        if "total_amount_sek" in item:
            skipped.append(item)
            continue

        raw = item.get("currency")
        iso, source = resolve_currency(item, reparsed)
        if iso is None:
            unrecognized.append(item)
            continue

        fields = {"currency": iso}
        if raw is not None and raw != iso:
            fields["currency_raw"] = raw
        if raw is None:
            fields["currency_source"] = source

        total, invoice_date = item.get("total_amount"), item.get("invoice_date")
        conversion = convert_to_sek(total, iso, invoice_date) if total is not None and invoice_date else None
        if conversion:
            fields.update(conversion)
        else:
            unconvertible.append((item, iso))

        if fields.get("currency") != raw or len(fields) > 1:
            updates.append((item, fields))
    return updates, unconvertible, unrecognized, skipped


def report_reparsed(items, reparsed):
    """List every currency-less row with what the Gemini re-parse returned and how its currency was resolved."""
    print(f"\n[Re-parsed missing currencies] {len(reparsed)} row(s)")
    print(f"  {'invoice_date':<12} {'vendor':<28} {'stored amt':>10} {'gemini amt':>10} {'gemini cur':>10} -> resolved (source)")
    rows = sorted((item for item in items if item["InvoiceID"] in reparsed), key=lambda i: (i.get("vendor_name") or "", i.get("invoice_date") or ""))
    for item in rows:
        entry = reparsed[item["InvoiceID"]]
        iso, source = resolve_currency(item, reparsed)
        flags = []
        stored, gemini_amount = item.get("total_amount"), entry.get("gemini_total_amount")
        if stored is not None and gemini_amount is not None and Decimal(str(stored)) != Decimal(str(gemini_amount)):
            flags.append("AMOUNT MISMATCH")
        if entry.get("error"):
            flags.append(f"ERROR: {entry['error']}")
        print(f"  {item.get('invoice_date', ''):<12} {(item.get('vendor_name') or '?')[:28]:<28} {str(stored):>10} "
              f"{str(gemini_amount):>10} {str(entry.get('gemini_currency')):>10} -> {iso} ({source})"
              + (f"  [{'; '.join(flags)}]" if flags else ""))
    print("  Sources:", dict(Counter(resolve_currency(item, reparsed)[1] for item in rows)))


def report(items, reparsed, updates, unconvertible, unrecognized, skipped):
    mapping = Counter((repr(item.get("currency")), resolve_currency(item, reparsed)[0]) for item in items)
    print(f"\nScanned {len(items)} row(s); {len(skipped)} already backfilled, {len(updates)} to update.")

    print("\n[Currency mapping] raw -> ISO (row count)")
    for (raw, iso), count in sorted(mapping.items(), key=lambda kv: -kv[1]):
        print(f"  {raw:>10} -> {str(iso):<5} {count}")

    converted = defaultdict(list)
    for item, fields in updates:
        if "total_amount_sek" in fields:
            converted[fields["currency"]].append((item, fields))
    print("\n[Converted] per currency (count, total -> SEK, sample rows)")
    for currency, rows in sorted(converted.items(), key=lambda kv: -len(kv[1])):
        total_sek = sum(fields["total_amount_sek"] for _, fields in rows)
        print(f"  {currency}: {len(rows)} row(s), {total_sek} SEK")
        if currency != "SEK":
            for item, fields in rows[:3]:
                print(f"    {item['invoice_date']} {item.get('vendor_name', '?')!r}: {item['total_amount']} {currency} "
                      f"x {fields['fx_rate']} (rate of {fields['fx_rate_date']}) = {fields['total_amount_sek']} SEK")

    print(f"\n[Unconvertible] {len(unconvertible)} row(s) (normalized but no SEK amount):")
    for item, iso in unconvertible:
        print(f"  {item['InvoiceID']}: {item.get('total_amount')} {iso} on {item.get('invoice_date')} ({item.get('vendor_name', '?')!r})")

    print(f"\n[Unrecognized currency] {len(unrecognized)} row(s) (left untouched):")
    for item in unrecognized:
        print(f"  {item['InvoiceID']}: currency={item.get('currency')!r} ({item.get('vendor_name', '?')!r})")


def apply_updates(table, updates):
    written = 0
    for item, fields in updates:
        names = {f"#{k}": k for k in fields}
        values = {f":{k}": v for k, v in fields.items()}
        condition = "attribute_not_exists(total_amount_sek)"
        if item.get("currency") is None:
            # A missing currency is stored either as an absent attribute or as an explicit NULL.
            condition += " AND (attribute_not_exists(#currency) OR attribute_type(#currency, :null_type))"
            values[":null_type"] = "NULL"
        else:
            condition += " AND #currency = :old_currency"
            values[":old_currency"] = item["currency"]
        try:
            table.update_item(
                Key={"UserID": item["UserID"], "InvoiceID": item["InvoiceID"]},
                UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
                ConditionExpression=condition,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
            written += 1
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            print(f"  [skip] {item['InvoiceID']} changed concurrently - leaving as-is")
    print(f"\n[Apply] Wrote {written} row(s).")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--reparse-cache", default=REPARSE_CACHE_PATH,
                        help="JSON cache of Gemini re-parse results, reused by --apply so it writes what the dry run showed")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)
    items = scan_all_items(table)
    reparsed = reparse_missing_currencies(items, args.reparse_cache)
    updates, unconvertible, unrecognized, skipped = plan_updates(items, reparsed)
    report_reparsed(items, reparsed)
    report(items, reparsed, updates, unconvertible, unrecognized, skipped)

    if args.apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = f"retail_invoices_pre_fx_backfill_snapshot_{stamp}.json"
        with open(snapshot_path, "w") as f:
            json.dump([item for item, _ in updates], f, cls=_DecimalEncoder, indent=2)
        print(f"\n[Snapshot] Wrote pre-write state of {len(updates)} row(s) to {snapshot_path}")
        apply_updates(table, updates)
    else:
        print("\nDry run - nothing written. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
