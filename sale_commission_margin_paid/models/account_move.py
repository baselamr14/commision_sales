import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_commission_margin(self):
        """Margin of this document for commission purposes.

        Product lines:  revenue - (qty * standard_price)
        Discount lines: the full amount (a pure price discount carries NO
                        cost, so the whole reduction is margin)

        The second case is why a pure-discount credit note still reduces
        commission even though it has no product: a 100 discount on an
        invoice reduces margin by exactly 100.

        Returned unsigned (always positive magnitude).
        """
        self.ensure_one()
        margin = 0.0
        for line in self.invoice_line_ids:
            if line.display_type:
                continue
            subtotal = line.price_subtotal or 0.0
            if line.product_id:
                cost = line.product_id.standard_price or 0.0
                margin += subtotal - ((line.quantity or 0.0) * cost)
            else:
                # No product => no cost => the whole amount is margin.
                margin += subtotal
        return abs(margin)

    # ------------------------------------------------------------------ #
    #  1. Document Posted -> commission already calculated by the SQL    #
    #     achievement view -> create/track the commission record and    #
    #     book the (full) accrual journal entry.                         #
    #                                                                    #
    #     Handles BOTH invoices (out_invoice) and credit notes           #
    #     (out_refund). Credit notes are linked back to the original     #
    #     invoice via reversed_entry_id and accrue in the reverse        #
    #     direction (Dr Accrual / Cr Expense).                           #
    # ------------------------------------------------------------------ #
    def _post(self, soft=True):
        posted = super()._post(soft=soft)

        sale_docs = posted.filtered(
            lambda m: m.move_type in ("out_invoice", "out_refund")
        )
        if sale_docs:
            sale_docs._create_commission_accrual_entries()

        return posted

    def _create_commission_accrual_entries(self):
        AchievementReport = self.env["sale.commission.achievement.report"]
        InvoiceMap = self.env["sale.commission.invoice.map"]

        for move in self:
            is_credit_note = move.move_type == "out_refund"

            # Per business decision #6: only act on credit notes that are
            # linked to an original invoice. A standalone credit note with
            # no reversed_entry_id does not affect commission (for now).
            origin_invoice = move.reversed_entry_id if is_credit_note else False
            if is_credit_note and not origin_invoice:
                _logger.info(
                    "Skipping commission for standalone credit note %s "
                    "(no linked original invoice).", move.name,
                )
                continue

            achievement_lines = AchievementReport.search([
                ("related_res_model", "=", "account.move"),
                ("related_res_id", "=", move.id),
                ("achieved", ">", 0),
            ])
            if not achievement_lines:
                # A PURE-DISCOUNT credit note has no product line, so the
                # margin-based achievement view produces nothing for it.
                # It must still reduce commission (a 100 discount reduces
                # margin by 100), so fall back to deriving the commission
                # from the ORIGIN invoice's effective rate.
                if is_credit_note and origin_invoice:
                    move._create_discount_credit_note_commission(origin_invoice)
                continue

            for line in achievement_lines:
                salesperson = line.user_id
                partner = salesperson.partner_id if salesperson else False
                if not partner:
                    _logger.warning(
                        "Skipping commission accrual for %s: salesperson "
                        "%s has no linked partner.",
                        move.name, salesperson.name if salesperson else "?",
                    )
                    continue

                existing = InvoiceMap.search([
                    ("user_id", "=", salesperson.id),
                    ("plan_id", "=", line.plan_id.id),
                    ("target_id", "=", line.target_id.id),
                    ("source_model", "=", "account.move"),
                    ("source_res_id", "=", move.id),
                    ("company_id", "=", move.company_id.id),
                ], limit=1)

                if existing:
                    commission_map = existing
                else:
                    commission_map = InvoiceMap.create({
                        "user_id": salesperson.id,
                        "partner_id": partner.id,
                        "plan_id": line.plan_id.id,
                        "target_id": line.target_id.id,
                        "source_model": "account.move",
                        "source_res_id": move.id,
                        "source_invoice_id": move.id,
                        "source_date": move.invoice_date or move.date or line.date,
                        "customer_id": line.partner_id.id,
                        "achieved_amount": line.achieved,
                        "currency_id": line.currency_id.id,
                        "company_id": move.company_id.id,
                        "document_type": "credit_note" if is_credit_note else "invoice",
                        "origin_invoice_id": origin_invoice.id if origin_invoice else False,
                        "state": "draft",
                    })

                commission_map._create_accrual_journal_entry()

                # A credit note may post AFTER its invoice was already
                # (partly) paid. In that case the refund on the credit note
                # may also already be (partly) settled, so immediately
                # evaluate its proportional payable too.
                commission_map._sync_payable_journal_entry()

    def _create_discount_credit_note_commission(self, origin_invoice):
        """Create the commission record for a PURE-DISCOUNT credit note.

        Such a credit note has no product line, so the margin-based
        achievement report yields nothing for it -- yet it must still
        reduce the salesperson's commission, because a price discount
        directly reduces margin.

        The commission rate is derived from the ORIGIN invoice's own
        commission record:  rate = origin_commission / origin_margin.
        Then:  credit_note_commission = rate * credit_note_margin.

        Example: invoice margin 400, commission 40 -> rate 10%.
                 Discount credit note of 100 -> margin 100 -> commission 10.
                 Net commission becomes 40 - 10 = 30.
        """
        self.ensure_one()
        InvoiceMap = self.env["sale.commission.invoice.map"]

        origin_maps = InvoiceMap.search([
            ("source_model", "=", "account.move"),
            ("source_res_id", "=", origin_invoice.id),
            ("company_id", "=", self.company_id.id),
            ("document_type", "=", "invoice"),
        ])
        if not origin_maps:
            _logger.info(
                "Discount credit note %s: origin invoice %s has no "
                "commission record, nothing to reverse.",
                self.name, origin_invoice.name,
            )
            return

        origin_margin = origin_invoice._get_commission_margin()
        if not origin_margin:
            _logger.warning(
                "Discount credit note %s: origin invoice %s has zero "
                "margin, cannot derive a commission rate.",
                self.name, origin_invoice.name,
            )
            return

        cn_margin = self._get_commission_margin()
        if not cn_margin:
            return

        for origin_map in origin_maps:
            rate = origin_map.achieved_amount / origin_margin
            cn_commission = rate * cn_margin
            if not cn_commission:
                continue

            existing = InvoiceMap.search([
                ("user_id", "=", origin_map.user_id.id),
                ("plan_id", "=", origin_map.plan_id.id),
                ("target_id", "=", origin_map.target_id.id),
                ("source_model", "=", "account.move"),
                ("source_res_id", "=", self.id),
                ("company_id", "=", self.company_id.id),
            ], limit=1)

            if existing:
                commission_map = existing
            else:
                commission_map = InvoiceMap.create({
                    "user_id": origin_map.user_id.id,
                    "partner_id": origin_map.partner_id.id,
                    "plan_id": origin_map.plan_id.id,
                    "target_id": origin_map.target_id.id,
                    "source_model": "account.move",
                    "source_res_id": self.id,
                    "source_invoice_id": self.id,
                    "source_date": self.invoice_date or self.date,
                    "customer_id": origin_map.customer_id.id,
                    "achieved_amount": cn_commission,
                    "currency_id": origin_map.currency_id.id,
                    "company_id": self.company_id.id,
                    "document_type": "credit_note",
                    "origin_invoice_id": origin_invoice.id,
                    "state": "draft",
                })

            commission_map._create_accrual_journal_entry()
            commission_map._sync_payable_journal_entry()

    # ------------------------------------------------------------------ #
    #  2. Cash collected/refunded -> post the PROPORTIONAL payable delta #
    #     for every affected commission record.                          #
    #                                                                    #
    #  Primary trigger is reconciliation (account_move_line.reconcile,   #
    #  the single chokepoint for both "Register Payment" and bank        #
    #  statement reconciliation). write() is a secondary trigger and     #
    #  the daily cron is a safety net. All three converge on the same    #
    #  idempotent _sync_payable_journal_entry(), which posts only the    #
    #  delta for the newly-settled fraction, so repeated calls are safe. #
    # ------------------------------------------------------------------ #
    def write(self, vals):
        previous_states = {move.id: move.payment_state for move in self}
        result = super().write(vals)

        settled_states = ("paid", "in_payment", "partial")
        changed = self.filtered(
            lambda m: m.move_type in ("out_invoice", "out_refund")
            and m.payment_state in settled_states
            and previous_states.get(m.id) != m.payment_state
        )
        if changed:
            changed._sync_commission_payable_entries()

        return result

    def _sync_commission_payable_entries(self):
        """For each document in self, post the proportional payable delta
        on every linked accrued commission record."""
        InvoiceMap = self.env["sale.commission.invoice.map"]

        for move in self:
            commission_maps = InvoiceMap.search([
                ("source_model", "=", "account.move"),
                ("source_res_id", "=", move.id),
                ("company_id", "=", move.company_id.id),
                ("accrual_posted", "=", True),
            ])
            if commission_maps:
                commission_maps._sync_payable_journal_entry()

    @api.model
    def _cron_create_commission_payable_entries(self):
        """Safety-net scheduled job: re-evaluate the proportional payable
        for every accrued commission record whose source document has any
        settlement, catching anything the live hooks missed."""
        InvoiceMap = self.env["sale.commission.invoice.map"]

        pending = InvoiceMap.search([
            ("accrual_posted", "=", True),
            ("source_model", "=", "account.move"),
            ("journal_state", "in", ("accrued", "partial")),
        ])
        for commission_map in pending:
            move = self.browse(commission_map.source_res_id).exists()
            if not move:
                continue
            commission_map._sync_payable_journal_entry()
