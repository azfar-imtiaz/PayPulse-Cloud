"""
Thin wrapper around the Jev (TypeSafe AI) SDK for a single combined classification call.

Verified against the installed typesafe_sdk==0.7.2 package (all public names - Noul,
Choice, TypeSafeClient - are exported directly from the top-level `typesafe_sdk` package,
not a `.questions` submodule). A single system_one() call evaluates multiple independent
questions (Noul and Choice here) against the same input in parallel, which is what this
module relies on to merge Tier 1 + Tier 2 into one request.
"""

import logging
from typing import Dict, Any

from typesafe_sdk import TypeSafeClient, Noul, Choice

from utils.exceptions import ClassificationError

logger = logging.getLogger()


def build_email_state(subject: str, sender: str, snippet: str) -> str:
    """
    Build the text input ("state") Jev classifies against, from lightweight email metadata.
    """
    return (
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Snippet: {snippet}"
    )


def classify_email(api_key: str, subject: str, sender: str, snippet: str,
                    category_descriptions: Dict[str, str]) -> Dict[str, Any]:
    """
    Run a single combined Jev call: is this an invoice/transaction email (Noul), and if
    so which category does it belong to (Choice, with a "none of these" escape hatch).

    Args:
        api_key: Jev (TypeSafe AI) API key
        subject: Email subject
        sender: Email "From" header
        snippet: Gmail snippet text
        category_descriptions: Mapping of category name -> short description/disambiguation
            hint, fed into Choice.criteria so Jev has real guidance instead of bare labels
            (see CATEGORY_DESCRIPTIONS in lambda_function.py for the actual hints, e.g.
            routing cloud/SaaS billing to 'subscriptions' rather than 'technology').

    Returns:
        {
            'noul_result': float (0-1),
            'choice_category': str or None,  # one of the category keys, or None if "none of these"
            'choice_confidence': float (0-1),
            'token_usage': {'input_tokens': int, 'output_tokens': int} or None
        }

    Raises:
        ClassificationError: on any SDK/API failure - callers should catch this, skip the
        message, and continue the sweep rather than aborting the whole run.
    """
    try:
        state = build_email_state(subject, sender, snippet)
        # Choice.criteria is a mapping of label -> optional description.
        choice_criteria = dict(category_descriptions)
        choice_criteria["none of these"] = "This is not a retail purchase invoice or receipt at all."

        with TypeSafeClient(api_key=api_key) as client:
            response = client.system_one(
                state=state,
                questions={
                    "is_invoice": Noul(
                        instructions=(
                            "Is this email an invoice, receipt, order confirmation, or other "
                            "transaction-related email for a purchase?"
                        )
                    ),
                    "category": Choice(
                        instructions=(
                            "Which category does this purchase belong to? Choose 'none of these' "
                            "if it clearly isn't a retail purchase or doesn't fit any category."
                        ),
                        criteria=choice_criteria,
                    ),
                }
            )

        noul_answer = response.nouls["is_invoice"]
        choice_answer = response.choices["category"]

        choice_category = choice_answer.choice
        if choice_category == "none of these":
            choice_category = None

        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return {
            "noul_result": float(noul_answer.noul),
            "choice_category": choice_category,
            "choice_confidence": float(choice_answer.confidence),
            "token_usage": token_usage,
        }
    except Exception as e:
        raise ClassificationError(f"Jev classification failed: {str(e)}") from e
