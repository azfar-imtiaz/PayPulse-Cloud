import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from google import genai
from google.genai import types


class RetailInvoiceBaseParser:
    """
    Base class for retail invoice parsing using Gemini Flash API.
    This class provides common functionality for all retail invoice sub-types.
    """

    def __init__(self, gemini_api_key: str):
        self.client = genai.Client(api_key=gemini_api_key)
        self.schema = {
            "vendor_name": "string",
            "total_amount": "number",
            "currency": "string",
            "invoice_date": "string (ISO 8601 format: YYYY-MM-DD)",
            "order_id": "string"
        }

    def parse_invoice(self, email_content: str, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Parse invoice content using Gemini Flash API.

        Args:
            email_content: HTML content of the email invoice
            prompt: Extraction prompt for the specific parser

        Returns:
            Parsed invoice data as dictionary or None if parsing fails
        """
        try:
            logging.info("Sending request to Gemini Flash API...")
            response = self.client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )

            result_text = response.text.strip()
            invoice_data = json.loads(result_text, parse_float=Decimal)
            logging.info("Invoice data parsed successfully!")
            return invoice_data
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response: {e}")
            logging.error(f"Response text: {response.text if 'response' in locals() else 'No response'}")
            return None
        except Exception as e:
            logging.error(f"Error during invoice parsing: {e}")
            return None

    def _generate_invoice_description(self, vendor_name: str, vendor_desc: str = None,
                                      is_email_in_swedish: bool = False, items_desc: str = None,
                                      header_info: str = None) -> str:
        """
        Crafts the invoice description section at the start of the prompt.
        """
        invoice_description = f"Parse this {vendor_name.capitalize()} email"
        if vendor_desc:
            invoice_description += f" ({vendor_desc})."
        else:
            invoice_description += "."

        if is_email_in_swedish:
            invoice_description += "\nThis email is in Swedish."

        if items_desc:
            invoice_description += f"\nItems are {items_desc}."

        if header_info:
            invoice_description += "\n" + header_info
            if not header_info.endswith("."):
                invoice_description += "."

        return invoice_description

    def _generate_base_instructions(self) -> list:
        """
        Returns the universal instruction lines shared across all parsers.
        """
        return [
            '- For dates, use ISO 8601 format (invoice_date: YYYY-MM-DD)',
            '- For amounts, extract only the numeric value (no currency symbols)',
            '- If a field is not found in the invoice, use null for strings and 0 for numbers',
            '- Ensure the JSON is valid and properly formatted',
            '- Do NOT include any explanations or text outside the JSON object',
            '- Return ONLY the JSON object, nothing else',
        ]

    def create_extraction_prompt(self, email_content: str, vendor_name: str) -> str:
        """
        Create extraction prompt for the invoice. Must be implemented by subclasses.

        Args:
            email_content: HTML content of the email
            vendor_name: Name of the vendor

        Returns:
            Formatted prompt for Gemini API
        """
        raise NotImplementedError("Subclasses must implement create_extraction_prompt method")