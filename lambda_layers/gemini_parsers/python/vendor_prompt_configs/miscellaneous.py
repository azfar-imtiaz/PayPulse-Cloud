CONFIGS = {
    "amazon.se": {
        "vendor_desc": "online marketplace",
        "is_email_in_swedish": False,
    },
    "amazon.com": {
        "vendor_desc": "online marketplace",
        "is_email_in_swedish": False,
    },
    "clasohlson": {
        "vendor_desc": "Swedish home improvement and hardware store",
        "is_email_in_swedish": True,
        "header_info": 'Look for "Orderbekräftelse" header.',
        "field_translations": {
            "Ordernummer": "Order number",
            "Betalningssätt": "Payment method",
            "Leveranssätt": "Delivery method",
            "Produkt": "Product",
            "Art. nr": "Article number",
            "Pris per styck": "Item price",
            "Frakt": "Delivery fee",
            "Betalningsavgift": "Payment fee",
            "Antal": "Amount/Quantity",
            "Totalt": "Total",
            "moms": "Tax",
        },
    },
    "liseberg": {
        "vendor_desc": "Swedish amusement park",
        "is_email_in_swedish": True,
        "items_desc": "amusement park tickets",
        "header_info": 'Look for "Dit köpp" header.',
        "field_translations": {
            "Beställningsdatum": "The date (YYYY-MM-DD) and time (HH:MM) of the order",
            "Ordernummer": "Order number",
            "Betalmetod": "Payment method",
            "Antal": "Amount/Quantity",
            "Pris": "Item price",
            "Entré": "Entry (this is the item name in the case of an amusement park ticket)",
            "Summa produkter": "Sum of products",
            "Totalpris": "Total",
            "Total moms": "Tax",
        },
    },
    "sternglas": {
        "vendor_desc": "German watch microbrand",
        "is_email_in_swedish": False,
    },
    "filmstaden": {
        "vendor_desc": "Cinema",
        "is_email_in_swedish": True,
        "field_translations": {
            "Artikel": "Article",
            "Totalt": "Total",
            "Moms": "Tax",
            "Betalmedel Kort": "Payment method card",
            "Transaktionsdatum": "Transaction date"
        },
        "header_info": 'Look for "Bokningsinformation" header'
    }
}
