import quopri
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
    This helper function removes fields which we don't want to return to the app, and sorts them in descending order
    """
    invoices_grouped_by_year = defaultdict(lambda: [])
    for invoice in invoices:
        invoice.pop('UserID', None)
        invoice.pop('Mervärdesskatt 25%', None)
        invoice.pop('Retroaktiv hyra avser 2302', None)
        invoice.pop('Retroaktiv hyra avser 2402', None)
        invoice.pop('Retroaktiv hyra avser 2403', None)

        # The following keys are not present in some invoices from 2022.
        # TODO: This should be done in the parsing
        if 'El' not in invoice.keys():
            invoice['El'] = "0"
        if 'Varmvatten' not in invoice.keys():
            invoice['Varmvatten'] = "0"
        if 'Kallvatten' not in invoice.keys():
            invoice['Kallvatten'] = "0"
        if 'Hyra' not in invoice.keys():
            invoice['Hyra'] = "0"

        invoice_year = invoice['due_date_year']
        # sort the invoices per year in descending order
        invoices_grouped_by_year[invoice_year].insert(0, invoice)

    return invoices_grouped_by_year