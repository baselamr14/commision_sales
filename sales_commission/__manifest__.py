# -*- coding: utf-8 -*-
{
    'name': 'sales_commission',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Calculate and manage sales commissions based on invoice payments',
    'description': """
Sales Commission Module
=======================
Features:
- Commission calculated when invoice is paid
- Commission by payment amount, product, product category, margin % or margin amount
- Auto-create vendor bill (invoice) for commission payout
- Sales commission analysis per salesperson
- Print commission reports by date range or commission type
    """,
    'author': 'Your Company',
    'depends': ['sale_management', 'account', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/commission_data.xml',
        'views/commission_rule_views.xml',
        'views/commission_line_views.xml',
        'views/commission_analysis_views.xml',
        'wizard/commission_invoice_wizard_views.xml',
        'report/commission_report_template.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
