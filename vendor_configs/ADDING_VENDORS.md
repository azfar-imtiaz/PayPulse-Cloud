# Adding a New Vendor

Two steps are required to add support for a new vendor.

## Step 1 — Create the vendor config

Add `{vendor_id}.json` to this directory. This config handles routing: it tells the system how to identify emails from this vendor and which parser to use.

```json
{
  "vendor_id": {"S": "vendor_id"},
  "vendor_name": {"S": "Vendor Name"},
  "invoice_category": {"S": "retail"},
  "invoice_sub_type": {"S": "clothing"},
  "default_email_patterns": {"SS": ["noreply@vendor.com"]},
  "default_subject_keywords": {"SS": ["Your order"]},
  "parser_type": {"S": "html"},
  "active": {"BOOL": true},
  "supports_pdf": {"BOOL": false},
  "supports_html": {"BOOL": true},
  "logo_url": {"S": ""},
  "created_at": {"S": "2026-01-01T00:00:00Z"},
  "updated_at": {"S": "2026-01-01T00:00:00Z"}
}
```

`invoice_sub_type` must be one of: `clothing`, `food_delivery`, `miscellaneous`, `subscriptions`, `technology`, `travel`.

## Step 2 — Add the prompt config

Add an entry to the corresponding file in `lambda_layers/gemini_parsers/python/vendor_prompt_configs/{sub_type}.py`.

```python
"vendor_id": {
    "vendor_desc": "Short description of the vendor",
    "is_email_in_swedish": False,
    "items_desc": "what the items are (e.g. electronics)",       # optional
    "header_info": 'Look for "Order confirmation" header.',      # optional
    "field_translations": {                                       # optional, Swedish vendors only
        "Ordernummer": "Order number",
        "Totalt": "Total",
    },
},
```

The `vendor_id` key must match the `vendor_id` in the JSON config (lowercase).
NOTE: This step can also be skipped. It allows for more accurate parsing at the expense of manually adding parsing specifics for the new vendor.