{
    "name": "CRM Lead Geolocation",
    "version": "19.0.1.0.0",
    "summary": "Capture GPS location and auto-fill address on CRM leads",
    "description": """
Capture salesperson current GPS coordinates on CRM leads,
store latitude/longitude/accuracy, generate a map link,
and reverse-geocode the address fields.
""",
    "category": "Sales/CRM",
    "author": "Your Company",
    "license": "LGPL-3",
    "depends": ["crm", "web"],
    "data": [
        "views/crm_lead_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "crm_lead_geolocation/static/src/js/geo_location_button.js",
            "crm_lead_geolocation/static/src/xml/geo_location_button.xml",
        ],
    },
    "installable": True,
    "application": False,
}