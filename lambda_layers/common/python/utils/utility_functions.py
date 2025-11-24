import quopri
from decimal import Decimal
from typing import List, Dict
from collections import defaultdict
from email.header import decode_header


def decode_string(s):
    decoded_bytes, charset = decode_header(s)[0]
    decoded_string = decoded_bytes.decode(charset) \
        if isinstance(decoded_bytes, bytes) else decoded_bytes
    return decoded_string


def get_body_from_email(s):
    decoded_bytes = quopri.decodestring(s)
    decoding_string = decoded_bytes.decode('utf-8')
    return decoding_string


def postprocess_rental_invoices(invoices: List[Dict]) -> Dict:
    """
    This helper function groups rental invoices by year, and sorts them in descending order
    """
    invoices_grouped_by_year = defaultdict(lambda: [])
    for invoice in invoices:
        invoice_year = invoice['due_date_year']
        # sort the invoices per year in descending order
        invoices_grouped_by_year[invoice_year].insert(0, invoice)

    return invoices_grouped_by_year


def postprocess_retail_invoices(invoices: List[Dict]) -> Dict:
    """
    This helper function groups retail invoices by sub-type, and sorts them by invoice_date in descending order
    """
    invoices_grouped_by_subtype = defaultdict(lambda: [])
    for invoice in invoices:
        sub_type = invoice.get('sub_type', 'unknown')
        # Convert invoice_date string to compare for sorting
        invoice_date = invoice.get('invoice_date', '1900-01-01')
        invoice['_sort_date'] = invoice_date
        invoices_grouped_by_subtype[sub_type].append(invoice)

    # Sort each sub-type group by invoice_date in descending order (newest first)
    for sub_type in invoices_grouped_by_subtype:
        invoices_grouped_by_subtype[sub_type].sort(
            key=lambda x: x.get('_sort_date', '1900-01-01'),
            reverse=True
        )
        # Remove the temporary sort field
        for invoice in invoices_grouped_by_subtype[sub_type]:
            invoice.pop('_sort_date', None)

    return invoices_grouped_by_subtype


def convert_decimal_to_int(obj):
    """
    This helper function converts Decimal objects to int or float. This is needed because boto3 converts numeric values
    to Decimal by default, and the Decimal datatype is unsupported by json.dumps
    """
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    raise TypeError(f"Object of type '{type(obj).__name__}' for 'obj' is not JSON serializable.")