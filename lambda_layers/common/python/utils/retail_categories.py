"""
Canonical list of supported retail invoice categories. Deliberately has zero imports -
many lambdas (get_invoices, recategorize_retail_invoice, fetch_and_classify_outlook_invoices,
etc.) need this list but don't have the jev_layer/google_api_layer attached, so this must
not pull in utils.retail_sweep or anything else with heavy dependencies.
"""

SUPPORTED_CATEGORIES = [
    'food-delivery',
    'miscellaneous',
    'technology',
    'clothing',
    'travel',
    'subscriptions',
    'grocery',
    'utility',
]
