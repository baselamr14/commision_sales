{
    'name': 'Sales Profit Commission',
    'version': '19.0.1.0.0',
    'summary': 'Commission on profit for salespersons on sale order lines',
    'description': """
Sales Profit Commission
=======================
Calculates salesperson commission from profit on each sales order line.
Formula:
    commission = max((price_subtotal - (cost_price * quantity)), 0) * commission_percent / 100
""",
    'author': 'OpenAI',
    'website': 'https://www.odoo.com',
    'category': 'Sales/Sales',
    'license': 'OPL-1',
    'depends': ['sale_management'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
