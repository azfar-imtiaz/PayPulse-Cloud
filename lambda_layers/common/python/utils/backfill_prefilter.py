import re

_SENDER_DOMAIN_RE = re.compile(r'[\w.+-]+@([\w.-]+)')


def extract_sender_domain(sender: str) -> str:
    """
    Extract the full lowercased domain from a sender address/header. Returns the raw
    domain (unlike derive_vendor_slug_from_sender, which slugifies down to just the
    second-level label and drops subdomains/TLD) - exact domain matching needs the real
    domain, not a lossy slug.
    """
    match = _SENDER_DOMAIN_RE.search(sender or '')
    return match.group(1).lower() if match else ''


def should_prefilter_candidate(sender: str, excluded_domains: set) -> bool:
    """
    Cheap, backfill-only pre-check to skip a candidate before it ever reaches the Jev
    classification call. Only matches domains that can never be a real transactional
    vendor - an exact-match configured list (e.g. a personal bank the user doesn't want
    surfaced) plus the generic "notifications." subdomain convention used by platforms
    like Freelancer that only ever send activity notifications, never purchase invoices.

    Deliberately NOT a blanket noisy-domain blocklist - e.g. nayatel.com generates a lot
    of mail volume but is a real, confirmed vendor, so only unambiguous non-transactional
    domains belong here.
    """
    domain = extract_sender_domain(sender)
    if not domain:
        return False
    if domain in excluded_domains:
        return True
    return domain.startswith('notifications.') or domain.startswith('notification.')
