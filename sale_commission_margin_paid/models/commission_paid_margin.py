from odoo import fields, models


class SaleCommissionPlanAchievement(models.Model):
    _inherit = "sale.commission.plan.achievement"


    type = fields.Selection(
        selection_add=[("margin_paid", "Margin (Paid Invoices)")],
        ondelete={"margin_paid": "cascade"},
    )

    def _compute_achievement_value(self, salesperson, date_from, date_to):
        self.ensure_one()

        if self.type == "margin_paid":
            return self._get_margin_paid(salesperson, date_from, date_to)

        return super()._compute_achievement_value(salesperson, date_from, date_to)

    def _get_margin_paid(self, salesperson, date_from, date_to):
        domain = [
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("move_id.payment_state", "=", "paid"),
            ("move_id.invoice_date", ">=", date_from),
            ("move_id.invoice_date", "<=", date_to),
            ("display_type", "=", False),
            ("product_id", "!=", False),
            ("move_id.invoice_user_id", "=", salesperson.id),
        ]

        lines = self.env["account.move.line"].search(domain)
        return sum(lines.mapped("margin_paid_base"))

    def _compute_commission(self, amount, achieved):
        self.ensure_one()
        if self.type == "margin_paid":
            return achieved  # commission = achieved (rate already applied)
        return super()._compute_commission(amount, achieved)

   
