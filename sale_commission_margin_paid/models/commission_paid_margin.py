from odoo import fields, models


class SaleCommissionPlanAchievement(models.Model):
    _inherit = "sale.commission.plan.achievement"

    type = fields.Selection(
        selection_add=[
            ("margin_paid", "Margin (Paid Invoices)"),
            ("margin_posted", "Margin (Posted Invoices)"),
        ],
        ondelete={
            "margin_paid": "cascade",
            "margin_posted": "cascade",
        },
    )

    def _compute_achievement_value(self, salesperson, date_from, date_to):
        self.ensure_one()

        if self.type == "margin_paid":
            return self._get_margin_by_payment_state(
                salesperson, date_from, date_to, payment_state="paid"
            )

        if self.type == "margin_posted":
            return self._get_margin_by_payment_state(
                salesperson, date_from, date_to, payment_state=None
            )

        return super()._compute_achievement_value(salesperson, date_from, date_to)

    def _get_margin_by_payment_state(self, salesperson, date_from, date_to, payment_state):
        """
        Compute margin commission for the given salesperson and date range.

        :param payment_state: if 'paid', restrict to fully paid invoices only;
                              if None, include all posted invoices regardless of payment.
        """
        domain = [
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("move_id.invoice_date", ">=", date_from),
            ("move_id.invoice_date", "<=", date_to),
            ("display_type", "=", False),
            ("product_id", "!=", False),
            ("move_id.invoice_user_id", "=", salesperson.id),
        ]

        if payment_state:
            domain.append(("move_id.payment_state", "=", payment_state))

        lines = self.env["account.move.line"].search(domain)
        return sum(lines.mapped("margin_paid_base"))

    # Keep the old helper as an alias so any existing calls still work
    def _get_margin_paid(self, salesperson, date_from, date_to):
        return self._get_margin_by_payment_state(
            salesperson, date_from, date_to, payment_state="paid"
        )

    def _compute_commission(self, amount, achieved):
        self.ensure_one()
        if self.type in ("margin_paid", "margin_posted"):
            return achieved
        return super()._compute_commission(amount, achieved)
