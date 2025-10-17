"""
Parser factory for routing retail invoice sub-types to appropriate parsers.
"""

import logging
from typing import Optional

from parsers.base_parser import RetailInvoiceBaseParser
from parsers.food_delivery_parser import FoodDeliveryParser
from parsers.miscellaneous_parser import MiscellaneousParser
from parsers.technology_parser import TechnologyParser


def get_parser_for_subtype(sub_type: str, gemini_api_key: str) -> Optional[RetailInvoiceBaseParser]:
    """
    Factory function to get the appropriate parser for a given retail invoice sub-type.

    Args:
        sub_type: The retail invoice sub-type (e.g., 'food-delivery', 'miscellaneous')
        gemini_api_key: API key for Gemini Flash API

    Returns:
        Parser instance for the specified sub-type, or None if unsupported

    Raises:
        ValueError: If sub_type is not supported
    """
    parser_mapping = {
        'food-delivery': FoodDeliveryParser,
        'miscellaneous': MiscellaneousParser,
        'technology': TechnologyParser,
        # TODO: Add remaining parsers as they are implemented
        # 'clothing': ClothingParser,
        # 'subscriptions': SubscriptionParser,
        # 'grocery': GroceryParser,
        # 'utility': UtilityParser,
    }

    parser_class = parser_mapping.get(sub_type)
    if not parser_class:
        supported_types = list(parser_mapping.keys())
        logging.error(f"Unsupported sub-type: {sub_type}. Supported types: {supported_types}")
        raise ValueError(f"Unsupported retail invoice sub-type: {sub_type}")

    logging.info(f"Creating parser for sub-type: {sub_type}")
    return parser_class(gemini_api_key)


def extract_subtype_from_s3_path(s3_key: str) -> str:
    """
    Extract retail invoice sub-type from S3 object key.

    Expected S3 path format: invoices/{user_id}/retail/{sub_type}/{vendor}_{date}_{hash}.html

    Args:
        s3_key: S3 object key

    Returns:
        Sub-type string (e.g., 'food-delivery', 'miscellaneous')

    Raises:
        ValueError: If S3 path format is invalid
    """
    try:
        path_parts = s3_key.split('/')
        if len(path_parts) < 4 or path_parts[2] != 'retail':
            raise ValueError(f"Invalid retail invoice S3 path: {s3_key}")

        sub_type = path_parts[3]
        logging.info(f"Extracted sub-type '{sub_type}' from S3 path: {s3_key}")
        return sub_type

    except Exception as e:
        logging.error(f"Failed to extract sub-type from S3 path '{s3_key}': {e}")
        raise ValueError(f"Invalid S3 path format: {s3_key}") from e


def extract_vendor_from_filename(s3_key: str) -> str:
    """
    Extract vendor name from S3 object filename.

    Expected filename format: {vendor}_{date}_{hash}.html

    Args:
        s3_key: S3 object key

    Returns:
        Vendor name (e.g., 'dominos', 'amazon.com')

    Raises:
        ValueError: If filename format is invalid
    """
    try:
        filename = s3_key.split('/')[-1]  # Get just the filename
        vendor_name = filename.split('_')[0]  # Get part before first underscore

        if not vendor_name:
            raise ValueError(f"Could not extract vendor from filename: {filename}")

        logging.info(f"Extracted vendor '{vendor_name}' from filename: {filename}")
        return vendor_name

    except Exception as e:
        logging.error(f"Failed to extract vendor from S3 key '{s3_key}': {e}")
        raise ValueError(f"Invalid filename format in S3 key: {s3_key}") from e