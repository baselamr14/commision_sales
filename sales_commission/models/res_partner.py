# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    commission_rule_ids = fields.One2many(
        comodel_name='commission.rule',
        inverse_name='salesperson_id',
        string='Commission Rules',
        help='Commission rules assigned when this partner is set as salesperson.',
        domain="[('salesperson_id.partner_id', '=', id)]",
    )
