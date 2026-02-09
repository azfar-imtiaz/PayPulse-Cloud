"""
Invoice ID generation utilities for manual invoices.
"""

from uuid import uuid4


def generate_manual_invoice_id() -> str:
    """
    Generate unique invoice ID for manually created invoices.

    Returns:
        Invoice ID with 'manual_' prefix to distinguish from Gmail-sourced invoices
    """
    return f"manual_{uuid4()}"