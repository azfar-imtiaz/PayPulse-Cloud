import json
import logging
from .base_parser import RetailInvoiceBaseParser
from vendor_prompt_configs.grocery import CONFIGS


class GroceryParser(RetailInvoiceBaseParser):
    """
    Parser for grocery invoices (supermarkets, grocery delivery services).
    Handles vendors like ICA, Coop, etc.
    """

    def __init__(self, gemini_api_key: str):
        super().__init__(gemini_api_key=gemini_api_key)
        self.schema.update({
            "store_name": "string",
            "store_location": "string",
            "items": [
                {
                    "name": "string",
                    "price": "number",
                    "quantity": "number",
                    "unit": "string (e.g. kg, pcs, liter)",
                    "category": "string (e.g. produce, dairy, bakery)"
                }
            ]
        })

    def __generate_custom_instructions(self, swedish_instructions: str = None):
        custom_instructions = "- Extract ALL fields from the invoice."
        if swedish_instructions:
            custom_instructions += "\n"
            custom_instructions += "- " + swedish_instructions
        else:
            custom_instructions += "\n"

        custom_instructions += "\n".join([
            '- For items array, include all purchased items with their name, price, quantity, unit, and category',
            '- If unit is not specified for an item, use "pcs" as the default',
            '- If category cannot be determined for an item, use "miscellaneous"',
        ] + self._generate_base_instructions())

        return custom_instructions

    def __create_extraction_prompt(self, email_content: str, vendor_name: str, is_email_in_swedish: bool = False,
                                   vendor_desc: str = None, swedish_instructions: str = None, items_desc: str = None,
                                   header_info: str = None) -> str:
        """
        This method returns the extraction prompt for grocery invoices.

        Args:
            email_content: The content extracted from the invoice HTML
            vendor_name: The name of the vendor (grocery store, in this case)
            vendor_desc: A small description of the vendor
            is_email_in_swedish: Boolean specifying the language of the email content (True = Swedish, False = English)
            swedish_instructions: Specific translation instructions for this type of invoice
            items_desc: A description of what the items in this invoice can be
            header_info: Information about the header below which the invoice information can be found
        """
        prompt = f"""You are an expert at extracting structured information from grocery store invoices/receipts.

{self._generate_invoice_description(vendor_name, vendor_desc, is_email_in_swedish, items_desc, header_info)}

Extract the following information from the HTML invoice below and return it as a valid JSON object.

Required JSON structure:
{json.dumps(self.schema, indent=2)}

Instructions:
{self.__generate_custom_instructions(swedish_instructions)}

HTML Invoice:
{email_content}
        """

        return prompt

    def create_extraction_prompt(self, email_content: str, vendor_name: str) -> str:
        """
        Create vendor-specific extraction prompt for grocery invoices.

        Args:
            email_content: HTML content of the invoice email
            vendor_name: Name of the vendor (e.g., 'ica', 'coop')

        Returns:
            Formatted prompt for Gemini API
        """
        config = CONFIGS.get(vendor_name.lower())
        if config is None:
            logging.warning(f"No prompt config found for vendor '{vendor_name}', using defaults.")
            return self.__create_extraction_prompt(email_content=email_content, vendor_name=vendor_name)

        cfg = dict(config)
        field_translations = cfg.pop("field_translations", None)
        swedish_instructions = self._format_field_translations(field_translations) if field_translations else None

        return self.__create_extraction_prompt(
            email_content=email_content,
            vendor_name=vendor_name,
            swedish_instructions=swedish_instructions,
            **cfg
        )
