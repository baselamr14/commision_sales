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

    # ------------------------------------------------------------------ #
    #  Commission payable trigger                                        #
    # ------------------------------------------------------------------ #
    def reconcile(self):
        """Hook the single point that BOTH payment flows pass through.

        Whether the user clicks "Register Payment" or reconciles a bank
        statement line, the underlying journal items are reconciled via
        this method. After reconciliation completes, any linked customer
        invoice/refund may have just become fully settled, so we trigger
        the commission payable journal entry for those.

        This is more reliable than watching account.move.payment_state in
        write(), because payment_state is a computed-stored field whose
        recompute does not always surface in a write() the override sees.
        """
        # Collect the invoices touched by these lines before reconciling,
        # so we can re-evaluate their settlement state afterwards.
        candidate_moves = self.mapped("move_id").filtered(
            lambda m: m.move_type in ("out_invoice", "out_refund")
        )

        result = super().reconcile()

        settled_states = ("paid", "in_payment")
        if candidate_moves:
            # Invalidate so payment_state reflects the reconciliation we
            # just performed.
            candidate_moves.invalidate_recordset(["payment_state"])
            newly_settled = candidate_moves.filtered(
                lambda m: m.payment_state in settled_states
            )
            if newly_settled:
                newly_settled._create_commission_payable_entries()

        return result
