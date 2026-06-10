from odoo import fields, models


class SaleCommissionPlanAchievement(models.Model):
    _inherit = "sale.commission.plan.achievement"

    type = fields.Selection(
        selection_add=[
            ("margin_paid", "Margin (Paid Invoices)"),
            ("margin_posted", "Margin (Posted Invoices)"),  # ✅ NEW
        ],
        ondelete={
            "margin_paid": "cascade",
            "margin_posted": "cascade",               # ✅ NEW
        },
    )

    def _compute_achievement_value(self, salesperson, date_from, date_to):
        self.ensure_one()

        if self.type == "margin_paid":
            # ✅ CHANGED: now delegates to shared helper
            return self._get_margin_by_payment_state(
                salesperson, date_from, date_to, payment_state="paid"
            )

        # ✅ NEW: posted invoices branch
        if self.type == "margin_posted":
            return self._get_margin_by_payment_state(
                salesperson, date_from, date_to, payment_state=None
            )

        return super()._compute_achievement_value(salesperson, date_from, date_to)

    # ✅ NEW: shared helper replacing the old _get_margin_paid
    def _get_margin_by_payment_state(self, salesperson, date_from, date_to, payment_state):
        """
        payment_state='paid'  → only fully collected invoices
        payment_state=None    → all posted invoices regardless of payment
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

    # ✅ NEW: backward-compat alias so any external callers still work
    def _get_margin_paid(self, salesperson, date_from, date_to):
        return self._get_margin_by_payment_state(
            salesperson, date_from, date_to, payment_state="paid"
        )

    def _compute_commission(self, amount, achieved):
        self.ensure_one()
        # ✅ CHANGED: handles both types
        if self.type in ("margin_paid", "margin_posted"):
            return achieved
        return super()._compute_commission(amount, achieved)
