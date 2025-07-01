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


def postprocess_invoices(invoices: List[Dict]) -> Dict:
    """
    This helper function groups invoices by year, and sorts them in descending order
    """
    invoices_grouped_by_year = defaultdict(lambda: [])
    for invoice in invoices:
        invoice_year = invoice['due_date_year']
        # sort the invoices per year in descending order
        invoices_grouped_by_year[invoice_year].insert(0, invoice)

    return invoices_grouped_by_year


def convert_decimal_to_int(obj):
    """
    This helper function converts Decimal objects to int or float. This is needed because boto3 converts numeric values
    to Decimal by default, and the Decimal datatype is unsupported by json.dumps
    """
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    raise TypeError(f"Object of type '{type(obj).__name__}' for 'obj' is not JSON serializable.")