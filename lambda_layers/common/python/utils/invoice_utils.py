"""
Invoice utility functions for ID generation and common operations.
"""

from uuid import uuid4


def generate_manual_invoice_id() -> str:
    """
    Generate unique invoice ID for manually created invoices.

    Returns:
        Invoice ID with 'manual_' prefix to distinguish from Gmail-sourced invoices
    """
    return f"manual_{uuid4()}"


def generate_recurring_invoice_id() -> str:
    """
    Generate unique recurring invoice ID for recurring schedules.

    Returns:
        Recurring invoice ID with 'recurring_' prefix
    """
    return f"recurring_{uuid4()}"