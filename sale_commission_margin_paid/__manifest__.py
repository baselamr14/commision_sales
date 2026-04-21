{
    'name': 'Commission on Paid Invoice Margin',
    'version': '19.0.1.0.0',
    'summary': 'Adds a new commission achievement type: Margin on Paid Invoices',
    'description': """
        Extends the sale_commission module to add a new achievement type:
        'Margin (Paid Invoices)' — calculates commission based on the profit margin
        (price_subtotal - cost) of invoice lines where the invoice is fully paid,
        i.e. payment_state in ('paid', 'in_payment').
    """,
    'category': 'Sales/Sales',
    'author': 'Custom',
    'depends': ['sale_commission'],
    'data': [
        'views/sale_commission_plan_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
}
