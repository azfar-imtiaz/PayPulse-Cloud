import quopri
from typing import List, Dict
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


def remove_user_id_from_invoices(invoices: List[Dict]) -> List[Dict]:
    """
    This helper function removes the user ID from all parsed invoices data. We don't want to return that to the app
    """
    for index in range(len(invoices)):
        invoices[index].pop('UserID', None)
    return invoices