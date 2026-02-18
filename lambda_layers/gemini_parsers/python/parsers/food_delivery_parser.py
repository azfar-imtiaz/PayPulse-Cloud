import json
import logging
from .base_parser import RetailInvoiceBaseParser
from vendor_prompt_configs.food_delivery import CONFIGS


class FoodDeliveryParser(RetailInvoiceBaseParser):
    """
    Parser for food delivery invoices (restaurants, delivery services).
    Handles vendors like Foodora, Dominos, etc.
    """

    def __init__(self, gemini_api_key: str):
        super().__init__(gemini_api_key=gemini_api_key)
        self.schema.update({
            "delivery_fee": "number",
            "items": [
                {
                    "name": "string",
                    "description": "string (optional)",
                    "price": "number",
                    "quantity": "number"
                }
            ],
            "discount": "number or 0 if not present"
        })

    def __generate_custom_instructions(self, swedish_instructions: str = None):
        custom_instructions = "- Extract ALL fields from the invoice."
        if swedish_instructions:
            custom_instructions += "\n"
            custom_instructions += "- " + swedish_instructions
        else:
            custom_instructions += "\n"

        custom_instructions += "\n".join([
            '- Delivery fee should not be part of the items array',
            '- For items array, include all ordered items with their name, price, and quantity',
            '- In the items array, the description field is optional. It can contain information about a product such as selected sides or drinks. This field should be empty if no such information is mentioned about the item',
        ] + self._generate_base_instructions())

        return custom_instructions

    def __create_extraction_prompt(self, email_content: str, vendor_name: str, is_email_in_swedish: bool = False,
                                   vendor_desc: str = None, swedish_instructions: str = None, items_desc: str = None,
                                   header_info: str = None) -> str:
        """
        This method returns the extraction prompt for food delivery invoices.

        Args:
            email_content: The content extracted from the invoice HTML
            vendor_name: The name of the vendor (restaurant, in this case)
            vendor_desc: A small description of the vendor
            is_email_in_swedish: Boolean specifying the language of the email content (True = Swedish, False = English)
            swedish_instructions: Specific translation instructions for this type of invoice
            items_desc: A description of what the items in this invoice can be
            header_info: Information about the header below which the invoice information can be found
        """
        prompt = f"""You are an expert at extracting structured information from food delivery invoices.

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
        Create vendor-specific extraction prompt for food delivery invoices.

        Args:
            email_content: HTML content of the invoice email
            vendor_name: Name of the vendor (e.g., 'dominos', 'foodora')

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