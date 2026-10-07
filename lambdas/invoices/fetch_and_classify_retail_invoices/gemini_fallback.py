"""
Small Gemini-based category fallback, used only when Jev's choice classification is
low-confidence or lands on "none of these". Deliberately much smaller than the
per-category extraction prompts in lambda_layers/gemini_parsers/ - this just resolves a
category label, it does not extract invoice fields.
"""

import json
import logging
from typing import Dict, Optional

from google import genai
from google.genai import types

logger = logging.getLogger()


def gemini_category_fallback(gemini_api_key: str, subject: str, sender: str, snippet: str,
                              category_descriptions: Dict[str, str]) -> Optional[str]:
    """
    Ask Gemini to resolve a category when Jev's Tier 1+2 call couldn't confidently do so.

    Args:
        gemini_api_key: Gemini API key
        subject: Email subject
        sender: Email "From" header
        snippet: Gmail snippet text
        category_descriptions: Mapping of category name -> short description/disambiguation
            hint (same CATEGORY_DESCRIPTIONS used for the Jev call, kept consistent so the
            fallback doesn't contradict Jev's own guidance).

    Returns:
        One of the category keys, or None if Gemini also can't confidently categorize it
        (message should then be parked as `parked_unclassifiable`).
    """
    categories_block = "\n".join(f"- {name}: {desc}" for name, desc in category_descriptions.items())
    prompt = (
        "You are classifying whether an email is a retail purchase invoice/receipt, and "
        "if so which category it belongs to.\n\n"
        f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n\n"
        f"Categories:\n{categories_block}\n\n"
        "Respond with ONLY a JSON object: "
        '{"category": "<one of the category names above, or null if this is not a retail '
        'purchase invoice/receipt or doesn\'t confidently fit any category>"}'
    )

    try:
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        result = json.loads(response.text.strip())
        category = result.get("category")

        if category in category_descriptions:
            return category

        logger.info(f"Gemini fallback did not resolve a known category: {category!r}")
        return None
    except Exception as e:
        logger.error(f"Gemini category fallback failed: {e}")
        return None
