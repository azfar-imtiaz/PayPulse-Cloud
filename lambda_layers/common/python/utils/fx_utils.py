import csv
import io
import logging
import time
import zipfile
import urllib.request
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

ECB_HISTORICAL_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
DEFAULT_CURRENCY = "SEK"
TARGET_CURRENCY = "SEK"
MAX_FALLBACK_DAYS = 7
RATES_CACHE_TTL_SECONDS = 12 * 60 * 60

# Raw currency strings seen in parser output (lowercased, stripped) -> ISO 4217 code.
CURRENCY_ALIASES = {
    "kr": "SEK",
    "kr.": "SEK",
    "sek": "SEK",
    ":-": "SEK",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "£": "GBP",
    "gbp": "GBP",
    "kč": "CZK",
    "czk": "CZK",
    "₨": "PKR",
    "rs": "PKR",
    "rs.": "PKR",
    "pkr": "PKR",
}

_rates_cache: Optional[Dict[str, Dict[str, Decimal]]] = None
_rates_loaded_at: float = 0.0


def normalize_currency(raw: Optional[str]) -> Optional[str]:
    """Map a raw parser currency string to an ISO 4217 code; missing values default to SEK, unrecognized ones return None."""
    if raw is None or not str(raw).strip():
        return DEFAULT_CURRENCY
    cleaned = str(raw).strip().lower()
    if cleaned in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[cleaned]
    if len(cleaned) == 3 and cleaned.isalpha():
        return cleaned.upper()
    return None


def _load_ecb_rates() -> Dict[str, Dict[str, Decimal]]:
    """Download the ECB historical reference rates (EUR-based) and return {YYYY-MM-DD: {currency: rate}}, cached in memory."""
    global _rates_cache, _rates_loaded_at
    if _rates_cache is not None and time.time() - _rates_loaded_at < RATES_CACHE_TTL_SECONDS:
        return _rates_cache

    with urllib.request.urlopen(ECB_HISTORICAL_RATES_URL, timeout=30) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    with archive.open(archive.namelist()[0]) as csv_file:
        reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8"))
        rates = {}
        for row in reader:
            day_rates = {"EUR": Decimal("1")}
            for currency, value in row.items():
                if currency and currency != "Date" and value and value.strip() not in ("", "N/A"):
                    day_rates[currency.strip()] = Decimal(value.strip())
            rates[row["Date"]] = day_rates

    _rates_cache = rates
    _rates_loaded_at = time.time()
    return rates


def convert_to_sek(amount, currency: str, invoice_date: str) -> Optional[Dict]:
    """Convert an amount in an ISO currency to SEK using the ECB rate on invoice_date (or the nearest earlier banking day); returns None if no rate is available."""
    amount = Decimal(str(amount))
    if currency == TARGET_CURRENCY:
        return {
            "total_amount_sek": amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "fx_rate": Decimal("1"),
            "fx_rate_date": invoice_date[:10],
            "fx_source": "native",
        }

    rates = _load_ecb_rates()
    day = date.fromisoformat(invoice_date[:10])
    for _ in range(MAX_FALLBACK_DAYS + 1):
        day_rates = rates.get(day.isoformat())
        if day_rates and currency in day_rates and TARGET_CURRENCY in day_rates:
            rate = (day_rates[TARGET_CURRENCY] / day_rates[currency]).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            return {
                "total_amount_sek": (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "fx_rate": rate,
                "fx_rate_date": day.isoformat(),
                "fx_source": "ECB",
            }
        day -= timedelta(days=1)
    return None


def build_currency_fields(amount, raw_currency: Optional[str], invoice_date: Optional[str]) -> Dict:
    """Return the currency/currency_raw/total_amount_sek/fx_* fields to store on a retail invoice; never raises, omitting the SEK fields if conversion isn't possible."""
    currency = normalize_currency(raw_currency) or raw_currency
    fields = {"currency": currency}
    if raw_currency is not None and raw_currency != currency:
        fields["currency_raw"] = raw_currency
    if amount is None or not invoice_date or not currency:
        return fields
    try:
        conversion = convert_to_sek(amount, currency, invoice_date)
    except Exception as e:
        logging.warning(f"SEK conversion failed for {amount} {currency} on {invoice_date}: {e}")
        conversion = None
    if conversion:
        fields.update(conversion)
    else:
        logging.info(f"No SEK conversion available for {amount} {currency} on {invoice_date}")
    return fields
