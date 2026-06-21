from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    margin_paid_base = fields.Monetary(
        string="Margin Paid Base",
        compute="_compute_margin_paid_base",
        currency_field="currency_id",
        store=False,
        help="Margin base used for paid-invoice margin commission calculation.",
    )

    @api.depends(
        "price_subtotal",
        "quantity",
        "product_id",
        "move_id.move_type",
    )
    def _compute_margin_paid_base(self):
        for line in self:
            move = line.move_id

            if not move or move.move_type not in ("out_invoice", "out_refund"):
                line.margin_paid_base = 0.0
                continue

            if line.display_type or not line.product_id:
                line.margin_paid_base = 0.0
                continue

            qty = line.quantity or 0.0
            subtotal = line.price_subtotal or 0.0

            cost = line.product_id.standard_price or 0.0
            cost_total = qty * cost
            raw_margin = subtotal - cost_total

            sign = 1.0 if move.move_type == "out_invoice" else -1.0
            line.margin_paid_base = sign * raw_margin
