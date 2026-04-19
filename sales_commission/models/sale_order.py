# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    commission_rule_ids = fields.Many2many(
        comodel_name='commission.rule',
        relation='sale_order_commission_rule_rel',
        column1='order_id',
        column2='rule_id',
        string='Commission Rules',
        help='Manually assigned commission rules for this sale order. '
             'If empty, rules are matched automatically via salesperson.',
        domain="[('salesperson_id', '=', user_id)]",
    )

    def _get_commission_rules(self):
        """Return commission rules for this order (manual override or auto-lookup)."""
        self.ensure_one()
        if self.commission_rule_ids:
            return self.commission_rule_ids
        return self.env['commission.rule'].search([
            ('salesperson_id', '=', self.user_id.id),
            ('active', '=', True),
        ])
