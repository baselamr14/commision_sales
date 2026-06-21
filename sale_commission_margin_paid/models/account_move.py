import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # ------------------------------------------------------------------ #
    #  1. Invoice Posted -> commission already calculated by the SQL    #
    #     achievement view -> create/track the commission record and    #
    #     book the accrual journal entry.                                #
    # ------------------------------------------------------------------ #
    def _post(self, soft=True):
        posted = super()._post(soft=soft)

        sale_invoices = posted.filtered(
            lambda m: m.move_type in ("out_invoice", "out_refund")
        )
        if sale_invoices:
            sale_invoices._create_commission_accrual_entries()

        return posted

    def _create_commission_accrual_entries(self):
        """For each posted customer invoice/refund in self, find the
        commission achievement lines generated for it, make sure each
        has a corresponding sale.commission.invoice.map record, and book
        the accrual journal entry (Dr Commission Expense / Cr Commission
        Accrual) for any that don't have one yet.
        """
        AchievementReport = self.env["sale.commission.achievement.report"]
        InvoiceMap = self.env["sale.commission.invoice.map"]

        for move in self:
            achievement_lines = AchievementReport.search([
                ("related_res_model", "=", "account.move"),
                ("related_res_id", "=", move.id),
                ("achieved", ">", 0),
            ])

            if not achievement_lines:
                continue

            for line in achievement_lines:
                salesperson = line.user_id
                partner = salesperson.partner_id if salesperson else False

                if not partner:
                    _logger.warning(
                        "Skipping commission accrual for invoice %s: "
                        "salesperson %s has no linked partner.",
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
                        "state": "draft",
                    })

                commission_map._create_accrual_journal_entry()

    # ------------------------------------------------------------------ #
    #  2. Invoice Paid -> book the payable journal entry, moving the     #
    #     amount from the accrual account to the salesperson payable     #
    #     account.                                                       #
    # ------------------------------------------------------------------ #
    def action_register_payment(self):
        # Run the standard payment registration first; the wizard it
        # returns is opened by the client, so the actual reconciliation
        # (and the resulting payment_state change) happens after this
        # method returns. We therefore detect newly-paid invoices via the
        # write() override below, which fires once reconciliation sets
        # payment_state to 'paid' or 'in_payment'.
        return super().action_register_payment()

    def write(self, vals):
        previous_states = {move.id: move.payment_state for move in self}
        result = super().write(vals)

        if "payment_state" in vals:
            newly_paid = self.filtered(
                lambda m: m.payment_state == "paid"
                and previous_states.get(m.id) != "paid"
                and m.move_type in ("out_invoice", "out_refund")
            )
            if newly_paid:
                newly_paid._create_commission_payable_entries()

        return result

    def _create_commission_payable_entries(self):
        """For each invoice in self that just became fully paid, create
        the payable journal entry for every linked commission record
        that has already been accrued.
        """
        InvoiceMap = self.env["sale.commission.invoice.map"]

        for move in self:
            commission_maps = InvoiceMap.search([
                ("source_model", "=", "account.move"),
                ("source_res_id", "=", move.id),
                ("company_id", "=", move.company_id.id),
                ("journal_state", "=", "accrued"),
            ])

            if not commission_maps:
                continue

            commission_maps._create_payable_journal_entry()
