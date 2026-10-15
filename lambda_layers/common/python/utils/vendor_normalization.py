import logging
import re
import unicodedata

from botocore.exceptions import ClientError

# Generic corporate-suffix tokens stripped from the trailing end of a vendor name when
# computing the matching key (not the display name) - deliberately narrow and generic,
# not vendor-specific, so this never risks merging two genuinely different brands.
_SUFFIX_TOKENS = {
    "ab", "se", "com", "sverige", "sweden", "ltd", "llc", "pbc", "gmbh", "inc",
    "group", "co", "limited", "de", "it",
}
_YEAR_RE = re.compile(r"^\d{4}$")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _tokenize(vendor_name: str) -> list:
    s = _strip_accents(vendor_name.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return [t for t in s.split(" ") if t]


def _strip_trailing_suffixes(tokens: list) -> list:
    tokens = list(tokens)
    while tokens and (tokens[-1] in _SUFFIX_TOKENS or _YEAR_RE.match(tokens[-1])):
        tokens.pop()
    return tokens


def compute_lookup_key(vendor_name: str) -> str:
    """Tier 1: fold a vendor name down to an aggressive matching key - case/accent/
    punctuation-insensitive, with generic corporate suffixes and trailing year tokens
    stripped. Used for VendorAliases lookups and as the vendor_order_key fallback
    component, never shown to a user."""
    if not vendor_name:
        return ""
    tokens = _strip_trailing_suffixes(_tokenize(vendor_name))
    return "".join(tokens)


def clean_display_name(vendor_name: str) -> str:
    """Conservative cosmetic cleanup for display/persistence when no Tier 2 alias
    exists: strips only a matched trailing suffix word from the original string
    (preserving casing/accents elsewhere - uses \\w+ token boundaries, not whitespace,
    so dot-glued suffixes like "Teknikmagasinet.se" are caught too), and title-cases
    the result only if the whole original was all-uppercase or all-lowercase."""
    if not vendor_name:
        return vendor_name

    tokens = list(re.finditer(r"\w+", vendor_name, re.UNICODE))
    keep_count = len(tokens)
    while keep_count > 0:
        norm = re.sub(r"[^a-z0-9]", "", _strip_accents(tokens[keep_count - 1].group().lower()))
        if norm in _SUFFIX_TOKENS or _YEAR_RE.match(norm):
            keep_count -= 1
        else:
            break

    if keep_count == 0:
        cleaned = vendor_name.strip()
    else:
        cleaned = vendor_name[:tokens[keep_count - 1].end()].strip()

    if cleaned.isupper() or cleaned.islower():
        return cleaned.title()
    return cleaned


def resolve_vendor_name(vendor_name: str, aliases_table) -> str:
    """Resolve a raw extracted vendor_name to its canonical form: a curated Tier 2
    alias if one is registered for this name's lookup key, else a Tier 1 cosmetic
    cleanup of the original string."""
    if not vendor_name:
        return vendor_name

    lookup_key = compute_lookup_key(vendor_name)
    if lookup_key:
        try:
            response = aliases_table.get_item(Key={"NormalizedKey": lookup_key})
            item = response.get("Item")
            if item:
                return item["CanonicalName"]
        except ClientError as e:
            logging.warning(f"VendorAliases lookup failed for '{lookup_key}', falling back to Tier 1: {e}")

    return clean_display_name(vendor_name)
