"""
Vendor-specific prompt configuration for each retail invoice sub-type parser.

Each module contains a CONFIGS dict keyed by vendor name (lowercase).
To add a new vendor, add an entry to the relevant sub-type config file —
no parser code changes required.

Supported config keys:
    vendor_desc (str):          Short description of the vendor.
    is_email_in_swedish (bool): Whether the invoice email is in Swedish. Defaults to False.
    items_desc (str):           Description of the items in the invoice (e.g. "electronics").
    header_info (str):          Instruction for locating the relevant section of the email.
    field_translations (dict):  Mapping of Swedish field names to English equivalents.
                                Only used when is_email_in_swedish is True.
"""
