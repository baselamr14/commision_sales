from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    total_commission = fields.Monetary(
        string='Total Commission',
        currency_field='currency_id',
        compute='_compute_total_commission',
        store=True,
        help='Sum of all commission amounts on the order lines.'
    )

    @api.depends('order_line.commission_amount')
    def _compute_total_commission(self):
        for order in self:
            order.total_commission = sum(order.order_line.mapped('commission_amount'))
