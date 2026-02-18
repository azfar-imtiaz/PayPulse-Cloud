import json
from .base_parser import RetailInvoiceBaseParser


class SubscriptionParser(RetailInvoiceBaseParser):
    """
    Parser for subscription invoices (Netflix, mosque charity etc.).
    """

    def __init__(self, gemini_api_key: str):
        super().__init__(gemini_api_key=gemini_api_key)
        self.schema.update({
            "receipt_number": "string",
            "invoice_number": "string",
            "payment_method": "string",
            "duration": "string"
        })

    def __generate_custom_instructions(self, swedish_instructions: str = None):
        custom_instructions = "- Extract ALL fields from the invoice."
        if swedish_instructions:
            custom_instructions += "\n"
            custom_instructions += "- " + swedish_instructions
        else:
            custom_instructions += "\n"

        custom_instructions += "\n".join([
            '- For duration, extract the date range (month and year), if available',
        ] + self._generate_base_instructions())

        return custom_instructions

    def __create_extraction_prompt(self, email_content: str, vendor_name: str, is_email_in_swedish: bool = False,
                                   vendor_desc: str = None, swedish_instructions: str = None, items_desc: str = None,
                                   header_info: str = None) -> str:
        """
        This method returns the extraction prompt for miscellaneous invoices.

        Args:
            email_content: The content extracted from the invoice HTML
            vendor_name: The name of the vendor
            vendor_desc: A small description of the vendor
            is_email_in_swedish: Boolean specifying the language of the email content (True = Swedish, False = English)
            swedish_instructions: Specific translation instructions for this type of invoice
            items_desc: A description of what the items in this invoice can be
            header_info: Information about the header below which the invoice information can be found
        """
        prompt = f"""You are an expert at extracting structured information from subscription invoices.

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
        Create vendor-specific extraction prompt for subscription invoices.

        Args:
            email_content: HTML content of the invoice email
            vendor_name: Name of the vendor (e.g., 'mevlana moske', 'netflix')

        Returns:
            Formatted prompt for Gemini API
        """
        if vendor_name.lower() == "mevlana":
            vendor_desc = "Mosque (charity)"
            is_email_in_swedish = False
            header_info = 'Look for "Kvitto från Mevlana Moské Göteborg" header.'

            return self.__create_extraction_prompt(
                email_content=email_content,
                vendor_name=vendor_name,
                vendor_desc=vendor_desc,
                is_email_in_swedish=is_email_in_swedish,
                header_info=header_info
            )
        else:
            # Default prompt with no specific vendor instructions
            return self.__create_extraction_prompt(email_content=email_content, vendor_name=vendor_name)