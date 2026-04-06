from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    purchase_cost = fields.Float(
        string='Cost Price',
        digits='Product Price',
        help='Cost used to calculate salesperson commission.'
    )

    commission_percent = fields.Float(
        string='Commission %',
        digits=(16, 2),
        help='Editable commission percentage for this line.'
    )

    profit_amount = fields.Monetary(
        string='Profit',
        currency_field='currency_id',
        compute='_compute_profit_and_commission',
        store=True
    )

    commission_amount = fields.Monetary(
        string='Commission Amount',
        currency_field='currency_id',
        compute='_compute_profit_and_commission',
        store=True
    )

    @api.depends('product_uom_qty', 'price_subtotal', 'purchase_cost', 'commission_percent')
    def _compute_profit_and_commission(self):
        for line in self:
            cost_total = (line.purchase_cost or 0.0) * (line.product_uom_qty or 0.0)
            profit = (line.price_subtotal or 0.0) - cost_total
            line.profit_amount = profit
            line.commission_amount = max(profit, 0.0) * (line.commission_percent / 100.0)

    @api.onchange('product_id')
    def _onchange_product_id_set_purchase_cost(self):
        for line in self:
            if line.product_id:
                line.purchase_cost = line.product_id.standard_price
# from odoo import api, fields, models
#
#
# class SaleOrderLine(models.Model):
#     _inherit = 'sale.order.line'
#
#     purchase_cost = fields.Float(
#         string='Cost Price',
#         digits='Product Price',
#         help='Cost price used to compute line profit and commission.'
#     )
#     commission_percent = fields.Float(
#         string='Commission %',
#         digits=(16, 2),
#         help='Editable commission percentage for this order line.'
#     )
#     profit_amount = fields.Monetary(
#         string='Profit',
#         currency_field='currency_id',
#         compute='_compute_profit_and_commission',
#         store=True,
#         help='Untaxed profit for the line after discounts.'
#     )
#     commission_amount = fields.Monetary(
#         string='Commission Amount',
#         currency_field='currency_id',
#         compute='_compute_profit_and_commission',
#         store=True,
#         help='Commission amount based on positive profit only.'
#     )
#
#     @api.depends('product_uom_qty', 'price_subtotal', 'purchase_cost', 'commission_percent')
#     def _compute_profit_and_commission(self):
#         for line in self:
#             qty = line.product_uom_qty or 0.0
#             cost_total = (line.purchase_cost or 0.0) * qty
#             profit = (line.price_subtotal or 0.0) - cost_total
#             line.profit_amount = profit
#             line.commission_amount = max(profit, 0.0) * ((line.commission_percent or 0.0) / 100.0)
#
#     @api.onchange('product_id')
#     def _onchange_product_id_set_purchase_cost(self):
#         for line in self:
#             if line.product_id:
#                 line.purchase_cost = line.product_id.standard_price
#
#     @api.onchange('order_id.user_id')
#     def _onchange_order_user_id_set_default_commission(self):
#         """Hook left intentionally simple.
#         Add your own default commission source here later if needed.
#         """
#         return
