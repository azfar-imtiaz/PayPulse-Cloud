CONFIGS = {
    "ryanair": {
        "vendor_desc": "airline",
        "is_email_in_swedish": False,
        "items_desc": "flight details",
        "header_info": 'Look for "Your flight information" header.',
    },
    "vr": {
        "vendor_desc": "railway company",
        "is_email_in_swedish": False,
        "items_desc": "trains journey details",
        "header_info": 'Look for "Thank you for your booking!" header.',
    },
    "flix": {
        "vendor_desc": "bus and train service",
        "is_email_in_swedish": False,
        "items_desc": "bus and train journey details",
        "header_info": 'Look for "Your booking is confirmed" header.',
    },
    "bus4you": {
        "vendor_desc": "bus service",
        "is_email_in_swedish": True,
        "items_desc": "bus journey details",
        "header_info": 'Look for "Nedan finner du dina bokningsuppgifter:" header',
        "field_translations": {
            "Bokningsnummer": "Booking number",
            "Datum": "Date",
            "Avgång": "Departure details (time HH:MM, location, stop name)",
            "Ankomst": "Arrival details (time HH:MM, location, stop name)",
        },
    },
}
