"""
Canonical list of supported retail invoice categories. Deliberately has zero imports -
many lambdas (get_invoices, recategorize_retail_invoice, fetch_and_classify_outlook_invoices,
etc.) need this list but don't have the jev_layer/google_api_layer attached, so this must
not pull in utils.retail_sweep or anything else with heavy dependencies.
"""

SUPPORTED_CATEGORIES = [
    'food-delivery',
    'miscellaneous',
    'technology',
    'clothing',
    'travel',
    'subscriptions',
    'grocery',
    'utility',
]

# Short disambiguation hints fed into Jev's Choice criteria (and the Gemini fallback
# prompt) so classification has real guidance instead of bare labels. Added after
# reviewing the first production run: parking providers were landing in 'miscellaneous'
# instead of 'travel', and cloud/SaaS billing (AWS, GCP) was landing in 'technology'
# instead of 'subscriptions'. Tune these as more misclassification patterns surface.
CATEGORY_DESCRIPTIONS = {
    'food-delivery': (
        "Restaurant or food delivery orders - meals ordered for delivery or pickup "
        "(e.g. Foodora, Uber Eats, Dominos)."
    ),
    'clothing': "Clothing, shoes, or apparel purchases.",
    'technology': (
        "One-time purchases of technology hardware, gadgets, or software/app licenses. "
        "Does NOT include recurring cloud or SaaS platform bills - those belong in "
        "'subscriptions' even though the vendor sounds technical (e.g. an AWS or Google "
        "Cloud invoice is a subscription, not technology)."
    ),
    'subscriptions': (
        "Recurring, regularly-billed services: streaming, cloud/SaaS platforms (AWS, "
        "Google Cloud, Azure, Anthropic, OpenAI), software subscriptions, and recurring "
        "membership or community dues (gym, club, religious organization). If the email "
        "describes a monthly or periodic charge, prefer this category even if the vendor "
        "sounds technical or otherwise unrelated."
    ),
    'grocery': "Grocery store or supermarket purchases.",
    'utility': "Home utility bills: electricity, water, heating, or home internet/broadband service.",
    'miscellaneous': (
        "General purchases that don't clearly fit any other category. Use this only "
        "when no other category applies."
    ),
    'travel': (
        "Transportation and travel-related purchases: flights, trains, ride-hailing, "
        "parking, tolls, hotels. Parking providers (e.g. Parkering, EasyPark, APCOA, "
        "P-Hus, Parkster) always belong here, not 'miscellaneous'."
    ),
}
