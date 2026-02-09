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