"""
Input validation schemas for manual retail invoice creation.

Validates base retail invoice fields and sub-type specific detail fields
for all 8 retail invoice categories.
"""

from datetime import datetime
from typing import Dict, Any

from utils.exceptions import ValidationError
from utils.s3_utils import get_valid_retail_categories


# Base invoice field validation
def validate_base_invoice_fields(data: Dict[str, Any]) -> None:
    """Validate required base retail invoice fields."""

    # Required fields
    required_fields = ['sub_type', 'vendor_name', 'total_amount', 'currency', 'invoice_date']
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")
        if not data[field]:
            raise ValidationError(f"Field '{field}' cannot be empty")

    # Sub-type validation
    valid_categories = get_valid_retail_categories()
    if data['sub_type'] not in valid_categories:
        raise ValidationError(f"Invalid sub_type. Must be one of: {', '.join(valid_categories)}")

    # Vendor name validation
    vendor_name = data['vendor_name']
    if not isinstance(vendor_name, str) or len(vendor_name.strip()) == 0:
        raise ValidationError("vendor_name must be a non-empty string")
    if len(vendor_name) > 100:
        raise ValidationError("vendor_name must be 100 characters or less")

    # Total amount validation
    try:
        amount = float(data['total_amount'])
        if amount < 0:
            raise ValidationError("total_amount must be non-negative")
        if amount > 999999.99:
            raise ValidationError("total_amount must be less than 1,000,000")
    except (ValueError, TypeError):
        raise ValidationError("total_amount must be a valid number")

    # Currency validation
    currency = data['currency'].upper()
    valid_currencies = ['SEK', 'USD', 'EUR', 'GBP', 'NOK', 'DKK']
    if currency not in valid_currencies:
        raise ValidationError(f"Invalid currency. Must be one of: {', '.join(valid_currencies)}")

    # Invoice date validation
    try:
        invoice_date = datetime.strptime(data['invoice_date'], '%Y-%m-%d')
        if invoice_date.year < 2020 or invoice_date.year > 2030:
            raise ValidationError("invoice_date must be between 2020 and 2030")
    except ValueError:
        raise ValidationError("invoice_date must be in YYYY-MM-DD format")

    # Optional fields validation
    if 'order_id' in data and data['order_id']:
        if not isinstance(data['order_id'], str) or len(data['order_id']) > 50:
            raise ValidationError("order_id must be a string with 50 characters or less")

    if 'payment_status' in data and data['payment_status']:
        valid_statuses = ['paid', 'pending', 'overdue', 'cancelled']
        if data['payment_status'] not in valid_statuses:
            raise ValidationError(f"Invalid payment_status. Must be one of: {', '.join(valid_statuses)}")

    if 'due_date' in data and data['due_date']:
        try:
            datetime.strptime(data['due_date'], '%Y-%m-%d')
        except ValueError:
            raise ValidationError("due_date must be in YYYY-MM-DD format")


# Sub-type specific validations
def validate_food_delivery_details(details: Dict[str, Any]) -> None:
    """Validate food delivery invoice details."""
    if 'delivery_fee' in details:
        try:
            fee = float(details['delivery_fee'])
            if fee < 0:
                raise ValidationError("delivery_fee must be non-negative")
        except (ValueError, TypeError):
            raise ValidationError("delivery_fee must be a valid number")

    if 'items' in details:
        if not isinstance(details['items'], list):
            raise ValidationError("items must be a list")
        for i, item in enumerate(details['items']):
            if not isinstance(item, dict):
                raise ValidationError(f"Item {i+1} must be an object")
            if 'name' not in item or not item['name']:
                raise ValidationError(f"Item {i+1} must have a name")
            if 'price' in item:
                try:
                    price = float(item['price'])
                    if price < 0:
                        raise ValidationError(f"Item {i+1} price must be non-negative")
                except (ValueError, TypeError):
                    raise ValidationError(f"Item {i+1} price must be a valid number")
            if 'quantity' in item:
                try:
                    qty = int(item['quantity'])
                    if qty <= 0:
                        raise ValidationError(f"Item {i+1} quantity must be positive")
                except (ValueError, TypeError):
                    raise ValidationError(f"Item {i+1} quantity must be a valid integer")

    if 'promo_code' in details and details['promo_code']:
        if not isinstance(details['promo_code'], str) or len(details['promo_code']) > 20:
            raise ValidationError("promo_code must be a string with 20 characters or less")


def validate_clothing_details(details: Dict[str, Any]) -> None:
    """Validate clothing invoice details."""
    if 'brand' in details and details['brand']:
        if not isinstance(details['brand'], str) or len(details['brand']) > 50:
            raise ValidationError("brand must be a string with 50 characters or less")

    if 'shipping_cost' in details:
        try:
            cost = float(details['shipping_cost'])
            if cost < 0:
                raise ValidationError("shipping_cost must be non-negative")
        except (ValueError, TypeError):
            raise ValidationError("shipping_cost must be a valid number")

    if 'discount_applied' in details:
        try:
            discount = float(details['discount_applied'])
            if discount < 0:
                raise ValidationError("discount_applied must be non-negative")
        except (ValueError, TypeError):
            raise ValidationError("discount_applied must be a valid number")

    if 'items' in details:
        if not isinstance(details['items'], list):
            raise ValidationError("items must be a list")
        for i, item in enumerate(details['items']):
            if not isinstance(item, dict):
                raise ValidationError(f"Item {i+1} must be an object")
            if 'name' not in item or not item['name']:
                raise ValidationError(f"Item {i+1} must have a name")


def validate_technology_details(details: Dict[str, Any]) -> None:
    """Validate technology invoice details."""
    if 'product_category' in details and details['product_category']:
        valid_categories = ['smartphone', 'laptop', 'tablet', 'accessory', 'software', 'other']
        if details['product_category'] not in valid_categories:
            raise ValidationError(f"Invalid product_category. Must be one of: {', '.join(valid_categories)}")

    if 'items' in details:
        if not isinstance(details['items'], list):
            raise ValidationError("items must be a list")
        for i, item in enumerate(details['items']):
            if not isinstance(item, dict):
                raise ValidationError(f"Item {i+1} must be an object")
            if 'name' not in item or not item['name']:
                raise ValidationError(f"Item {i+1} must have a name")


def validate_subscription_details(details: Dict[str, Any]) -> None:
    """Validate subscription invoice details."""
    if 'service_name' in details and details['service_name']:
        if not isinstance(details['service_name'], str) or len(details['service_name']) > 50:
            raise ValidationError("service_name must be a string with 50 characters or less")

    if 'billing_period_start' in details and details['billing_period_start']:
        try:
            datetime.strptime(details['billing_period_start'], '%Y-%m-%d')
        except ValueError:
            raise ValidationError("billing_period_start must be in YYYY-MM-DD format")

    if 'billing_period_end' in details and details['billing_period_end']:
        try:
            datetime.strptime(details['billing_period_end'], '%Y-%m-%d')
        except ValueError:
            raise ValidationError("billing_period_end must be in YYYY-MM-DD format")

    if 'subscription_type' in details and details['subscription_type']:
        valid_types = ['monthly', 'yearly', 'one-time', 'other']
        if details['subscription_type'] not in valid_types:
            raise ValidationError(f"Invalid subscription_type. Must be one of: {', '.join(valid_types)}")


def validate_grocery_details(details: Dict[str, Any]) -> None:
    """Validate grocery invoice details."""
    if 'store_name' in details and details['store_name']:
        if not isinstance(details['store_name'], str) or len(details['store_name']) > 50:
            raise ValidationError("store_name must be a string with 50 characters or less")

    if 'store_location' in details and details['store_location']:
        if not isinstance(details['store_location'], str) or len(details['store_location']) > 100:
            raise ValidationError("store_location must be a string with 100 characters or less")

    if 'items' in details:
        if not isinstance(details['items'], list):
            raise ValidationError("items must be a list")
        for i, item in enumerate(details['items']):
            if not isinstance(item, dict):
                raise ValidationError(f"Item {i+1} must be an object")
            if 'name' not in item or not item['name']:
                raise ValidationError(f"Item {i+1} must have a name")


def validate_utility_details(details: Dict[str, Any]) -> None:
    """Validate utility invoice details."""
    if 'utility_type' in details and details['utility_type']:
        valid_types = ['electricity', 'gas', 'water', 'internet', 'phone', 'waste', 'other']
        if details['utility_type'] not in valid_types:
            raise ValidationError(f"Invalid utility_type. Must be one of: {', '.join(valid_types)}")

    if 'provider' in details and details['provider']:
        if not isinstance(details['provider'], str) or len(details['provider']) > 50:
            raise ValidationError("provider must be a string with 50 characters or less")

    if 'usage_details' in details and details['usage_details']:
        if not isinstance(details['usage_details'], str) or len(details['usage_details']) > 200:
            raise ValidationError("usage_details must be a string with 200 characters or less")


def validate_miscellaneous_details(details: Dict[str, Any]) -> None:
    """Validate miscellaneous invoice details."""
    if 'tax' in details:
        try:
            tax = float(details['tax'])
            if tax < 0:
                raise ValidationError("tax must be non-negative")
        except (ValueError, TypeError):
            raise ValidationError("tax must be a valid number")

    if 'category' in details and details['category']:
        if not isinstance(details['category'], str) or len(details['category']) > 50:
            raise ValidationError("category must be a string with 50 characters or less")

    if 'description' in details and details['description']:
        if not isinstance(details['description'], str) or len(details['description']) > 500:
            raise ValidationError("description must be a string with 500 characters or less")

    if 'notes' in details and details['notes']:
        if not isinstance(details['notes'], str) or len(details['notes']) > 500:
            raise ValidationError("notes must be a string with 500 characters or less")


def validate_travel_details(details: Dict[str, Any]) -> None:
    """Validate travel invoice details."""
    if 'transport_type' in details and details['transport_type']:
        valid_types = ['flight', 'train', 'bus', 'taxi', 'ferry', 'rental_car', 'other']
        if details['transport_type'] not in valid_types:
            raise ValidationError(f"Invalid transport_type. Must be one of: {', '.join(valid_types)}")

    if 'transport_company' in details and details['transport_company']:
        if not isinstance(details['transport_company'], str) or len(details['transport_company']) > 50:
            raise ValidationError("transport_company must be a string with 50 characters or less")

    # Date validations for travel-specific fields
    date_fields = ['departure_date', 'arrival_date', 'return_departure_date', 'return_arrival_date']
    for field in date_fields:
        if field in details and details[field]:
            try:
                datetime.strptime(details[field], '%Y-%m-%d')
            except ValueError:
                raise ValidationError(f"{field} must be in YYYY-MM-DD format")


# Main validation dispatcher
def validate_manual_invoice_request(data: Dict[str, Any]) -> None:
    """
    Main validation function for manual invoice creation requests.

    Args:
        data: Request body data

    Raises:
        ValidationError: If any validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    # Validate base invoice fields
    validate_base_invoice_fields(data)

    # Validate sub-type specific details if provided
    sub_type = data['sub_type']
    details = data.get('details', {})

    if details and isinstance(details, dict):
        validation_functions = {
            'food-delivery': validate_food_delivery_details,
            'clothing': validate_clothing_details,
            'technology': validate_technology_details,
            'subscriptions': validate_subscription_details,
            'grocery': validate_grocery_details,
            'utility': validate_utility_details,
            'miscellaneous': validate_miscellaneous_details,
            'travel': validate_travel_details
        }

        validator = validation_functions.get(sub_type)
        if validator:
            validator(details)
        else:
            raise ValidationError(f"No validator found for sub_type: {sub_type}")
    elif details and not isinstance(details, dict):
        raise ValidationError("details field must be an object")