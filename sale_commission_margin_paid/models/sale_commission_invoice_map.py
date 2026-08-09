from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleCommissionInvoiceMap(models.Model):
    """Commission earned for one source document (invoice or credit note),
    for one salesperson/plan/target.

    Accounting model (approved matrix):
      * ACCRUAL  -> full commission, posted ONCE when the document posts.
                    Invoice:     Dr Expense / Cr Accrual
                    Credit note: Dr Accrual / Cr Expense   (reversed)
      * PAYABLE  -> PROPORTIONAL to cash collected/refunded, posted as
                    deltas across multiple payments.
                    Invoice payment: Dr Accrual / Cr Payable
                    Refund payment:  Dr Payable / Cr Accrual  (reversed)

    Every posted JE is recorded as an append-only row in
    sale.commission.journal.entry. Nothing is ever mutated.

    No cap: net commission for an invoice may go negative if linked credit
    notes exceed it (per business decision).
    """

    _name = "sale.commission.invoice.map"
    _description = "Commission Invoice Mapping"
    _order = "id desc"

    user_id = fields.Many2one(
        "res.users", string="Salesperson", required=True, index=True,
    )
    partner_id = fields.Many2one(
        "res.partner", string="Vendor", required=True, index=True,
    )
    plan_id = fields.Many2one(
        "sale.commission.plan", string="Commission Plan", required=True, index=True,
    )
    target_id = fields.Many2one(
        "sale.commission.plan.target", string="Target Period", required=True, index=True,
    )

    source_model = fields.Char(string="Source Model", required=True, index=True)
    source_res_id = fields.Integer(string="Source Record ID", required=True, index=True)
    source_invoice_id = fields.Many2one(
        "account.move", string="Source Document", index=True,
        help="The invoice or credit note this commission is earned on.",
    )
    source_date = fields.Date(string="Commission Date", index=True)
    customer_id = fields.Many2one("res.partner", string="Customer")

    # ------------------------------------------------------------------ #
    #  Document classification & credit-note linkage                     #
    # ------------------------------------------------------------------ #
    document_type = fields.Selection(
        [
            ("invoice", "Invoice"),
            ("credit_note", "Credit Note"),
        ],
        string="Document Type",
        required=True,
        default="invoice",
        index=True,
        help="Invoice: normal commission (Dr Expense / Cr Accrual).\n"
        "Credit Note: reversal commission (Dr Accrual / Cr Expense), "
        "linked to the original invoice.",
    )
    origin_invoice_id = fields.Many2one(
        "account.move",
        string="Original Invoice",
        index=True,
        help="For a credit note: the original invoice it reverses "
        "(account.move.reversed_entry_id).",
    )

    # ------------------------------------------------------------------ #
    #  Commission amount                                                 #
    # ------------------------------------------------------------------ #
    achieved_amount = fields.Monetary(
        string="Commission Amount",
        required=True,
        help="Full commission for this document (always stored positive; "
        "direction is derived from document_type).",
    )
    currency_id = fields.Many2one("res.currency", string="Currency", required=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
    )

    # ------------------------------------------------------------------ #
    #  Vendor bill (manual payout wizard - unchanged behaviour)          #
    # ------------------------------------------------------------------ #
    vendor_bill_id = fields.Many2one("account.move", string="Vendor Bill", index=True)
    vendor_bill_line_id = fields.Many2one("account.move.line", string="Vendor Bill Line")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("invoiced", "Invoiced"),
            ("cancelled", "Cancelled"),
        ],
        string="Status", default="draft", required=True, index=True,
    )

    reference = fields.Char(string="Reference", compute="_compute_reference", store=True)

    # ------------------------------------------------------------------ #
    #  Accrual tracking (one accrual JE per document)                    #
    # ------------------------------------------------------------------ #
    accrual_move_id = fields.Many2one(
        "account.move", string="Accrual Journal Entry", readonly=True, copy=False,
        help="The single accrual JE booked when this document posted.",
    )
    accrual_posted = fields.Boolean(
        string="Accrual Posted", default=False, copy=False, index=True,
    )

    # ------------------------------------------------------------------ #
    #  Append-only JE ledger + proportional payable tracking             #
    # ------------------------------------------------------------------ #
    journal_entry_ids = fields.One2many(
        "sale.commission.journal.entry", "map_id", string="Journal Entries",
    )
    payable_posted = fields.Monetary(
        string="Payable Posted",
        compute="_compute_payable_posted",
        store=True,
        help="Cumulative commission already moved to the payable account "
        "for this document (sum of payable ledger rows). Compared against "
        "the current paid fraction to compute the next delta.",
    )
    journal_state = fields.Selection(
        [
            ("pending", "Pending Accrual"),
            ("accrued", "Accrued"),
            ("partial", "Partially Payable"),
            ("payable", "Fully Payable"),
        ],
        string="Accounting Status",
        compute="_compute_journal_state",
        store=True,
        index=True,
    )

    _unique_commission_line = models.Constraint(
        "unique(user_id, plan_id, target_id, source_model, source_res_id, company_id)",
        "This commission line has already been tracked.",
    )

    # ================================================================== #
    #  Computes                                                          #
    # ================================================================== #
    @api.depends("source_model", "source_res_id")
    def _compute_reference(self):
        for rec in self:
            if rec.source_model and rec.source_res_id:
                rec.reference = f"{rec.source_model},{rec.source_res_id}"
            else:
                rec.reference = False

    @api.depends("journal_entry_ids.amount", "journal_entry_ids.entry_type")
    def _compute_payable_posted(self):
        for rec in self:
            rec.payable_posted = sum(
                rec.journal_entry_ids.filtered(
                    lambda e: e.entry_type == "payable"
                ).mapped("amount")
            )

    @api.depends("accrual_posted", "payable_posted", "achieved_amount")
    def _compute_journal_state(self):
        for rec in self:
            if not rec.accrual_posted:
                rec.journal_state = "pending"
                continue
            target = rec._signed_commission()
            posted = rec.payable_posted
            # Compare magnitudes so credit notes (negative) behave the same.
            if rec.currency_id and rec.currency_id.is_zero(posted):
                rec.journal_state = "accrued"
            elif rec.currency_id and rec.currency_id.compare_amounts(
                abs(posted), abs(target)
            ) >= 0:
                rec.journal_state = "payable"
            else:
                rec.journal_state = "partial"

    # ================================================================== #
    #  Helpers                                                           #
    # ================================================================== #
    def _signed_commission(self):
        """Commission with sign: positive for invoices, negative for
        credit notes. All JE amounts are derived from this."""
        self.ensure_one()
        amount = self.achieved_amount or 0.0
        return -amount if self.document_type == "credit_note" else amount

    def _get_commission_accounts(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        expense_account = company.commission_expense_account_id
        accrual_account = company.commission_accrual_account_id
        payable_account = company.commission_payable_account_id

        missing = []
        if not expense_account:
            missing.append(_("Commission Expense Account"))
        if not accrual_account:
            missing.append(_("Commission Accrual Account"))
        if not payable_account:
            missing.append(_("Salesperson Payable Account"))
        if missing:
            raise UserError(_(
                "Please configure the following accounts in "
                "Settings > Commission Accounting before commission "
                "journal entries can be created: %(accounts)s",
                accounts=", ".join(missing),
            ))
        return expense_account, accrual_account, payable_account

    def _get_commission_misc_journal(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "No miscellaneous journal found for company %(company)s.",
                company=company.name,
            ))
        return journal

    def _get_commission_entry_date(self):
        self.ensure_one()
        if self.source_date:
            return self.source_date
        if self.source_invoice_id:
            return self.source_invoice_id.invoice_date or self.source_invoice_id.date
        return fields.Date.context_today(self)

    def _get_source_paid_fraction(self):
        """Return how much of the source document has been settled BY CASH,
        as a fraction 0.0 .. 1.0.

        IMPORTANT: we deliberately do NOT use amount_residual here.
        amount_residual drops for BOTH real payments AND credit-note
        reconciliation. If a credit note is reconciled against an invoice,
        the invoice's residual falls even though no money was received --
        which would wrongly make the salesperson's commission payable.

        Instead we walk the reconciliation partials on the receivable /
        payable lines and count only those whose counterpart is NOT an
        invoice-type document (i.e. only bank/cash/payment counterparts).
        """
        self.ensure_one()
        move = self.source_invoice_id
        if not move:
            return 0.0
        total = move.amount_total
        if not total:
            return 0.0

        # Counterparts of these types are NOT cash -- they are credit-note
        # or invoice offsets and must not count as payment.
        invoice_types = ("out_invoice", "out_refund", "in_invoice", "in_refund")

        settlement_lines = move.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                "asset_receivable", "liability_payable",
            )
        )

        paid = 0.0
        for line in settlement_lines:
            # Partials where this line is the debit side (invoice receivable
            # being credited by a payment).
            for partial in line.matched_credit_ids:
                counterpart = partial.credit_move_id.move_id
                if counterpart.move_type in invoice_types:
                    continue
                paid += partial.amount
            # Partials where this line is the credit side (credit-note
            # receivable being debited by a refund payment).
            for partial in line.matched_debit_ids:
                counterpart = partial.debit_move_id.move_id
                if counterpart.move_type in invoice_types:
                    continue
                paid += partial.amount

        fraction = paid / total if total else 0.0
        if fraction < 0.0:
            return 0.0
        if fraction > 1.0:
            return 1.0
        return fraction

    def _record_journal_entry(self, move, entry_type, amount, paid_fraction=0.0):
        """Append a row to the JE ledger."""
        self.ensure_one()
        self.env["sale.commission.journal.entry"].create({
            "map_id": self.id,
            "move_id": move.id,
            "entry_type": entry_type,
            "amount": amount,
            "paid_fraction_at_posting": paid_fraction,
        })

    def _post_move(self, ref, account_debit, account_credit, amount):
        """Create and post a two-line balanced JE for `amount` (must be
        positive) and return the move."""
        self.ensure_one()
        journal = self._get_commission_misc_journal()
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self._get_commission_entry_date(),
            "ref": ref,
            "line_ids": [
                (0, 0, {
                    "name": ref,
                    "account_id": account_debit.id,
                    "partner_id": self.partner_id.id,
                    "debit": amount,
                    "credit": 0.0,
                }),
                (0, 0, {
                    "name": ref,
                    "account_id": account_credit.id,
                    "partner_id": self.partner_id.id,
                    "debit": 0.0,
                    "credit": amount,
                }),
            ],
        })
        move._post()
        return move

    # ================================================================== #
    #  ACCRUAL  (full commission, once, on document post)                #
    # ================================================================== #
    def _create_accrual_journal_entry(self):
        """Post the accrual JE for each record that hasn't accrued yet.

        Invoice:     Dr Expense / Cr Accrual
        Credit note: Dr Accrual / Cr Expense   (reversed direction)
        """
        for rec in self:
            if rec.accrual_posted or rec.accrual_move_id:
                continue
            if not rec.achieved_amount:
                continue

            expense, accrual, _payable = rec._get_commission_accounts()
            amount = rec.achieved_amount  # always positive
            salesperson = rec.user_id.name
            ref_base = rec.reference or rec.source_res_id

            if rec.document_type == "credit_note":
                ref = _("Commission accrual reversal (credit note) - %(sp)s - %(r)s",
                        sp=salesperson, r=ref_base)
                # Dr Accrual / Cr Expense
                move = rec._post_move(ref, accrual, expense, amount)
                signed = -amount
            else:
                ref = _("Commission accrual - %(sp)s - %(r)s",
                        sp=salesperson, r=ref_base)
                # Dr Expense / Cr Accrual
                move = rec._post_move(ref, expense, accrual, amount)
                signed = amount

            rec.write({
                "accrual_move_id": move.id,
                "accrual_posted": True,
            })
            rec._record_journal_entry(move, "accrual", signed)

    # ================================================================== #
    #  PAYABLE  (proportional to cash, delta on every payment)           #
    # ================================================================== #
    def _sync_payable_journal_entry(self):
        """Post the incremental payable JE for the newly-settled fraction.

        Target payable = paid_fraction * signed_commission.
        Delta = target - already_posted. Only posts when |delta| is non-zero.

        Invoice payment: Dr Accrual / Cr Payable
        Refund payment:  Dr Payable / Cr Accrual   (reversed direction)

        Idempotent & repeatable: safe to call on every reconciliation.
        Requires the accrual to have been posted first.
        """
        for rec in self:
            if not rec.accrual_posted:
                # Cannot make something payable before it is accrued.
                continue
            if not rec.achieved_amount:
                continue

            currency = rec.currency_id or rec.company_id.currency_id
            fraction = rec._get_source_paid_fraction()
            target = fraction * rec._signed_commission()
            delta = target - rec.payable_posted

            if currency and currency.is_zero(delta):
                continue

            expense, accrual, payable = rec._get_commission_accounts()
            salesperson = rec.user_id.name
            ref_base = rec.reference or rec.source_res_id
            amount = abs(delta)

            # Direction depends on the SIGN OF THE DELTA, not just the
            # document type. This correctly handles both normal settlement
            # and any downward correction.
            if delta > 0:
                # Moving commission INTO payable (invoice being paid).
                ref = _("Commission payable - %(sp)s - %(r)s",
                        sp=salesperson, r=ref_base)
                # Dr Accrual / Cr Payable
                move = rec._post_move(ref, accrual, payable, amount)
            else:
                # Reversing payable (credit-note refund being paid, or a
                # downward adjustment).
                ref = _("Commission payable reversal - %(sp)s - %(r)s",
                        sp=salesperson, r=ref_base)
                # Dr Payable / Cr Accrual
                move = rec._post_move(ref, payable, accrual, amount)

            # Record the SIGNED delta so payable_posted stays a running
            # signed total that converges on `target`.
            rec._record_journal_entry(move, "payable", delta, paid_fraction=fraction)

    # ================================================================== #
    #  Manual action buttons                                             #
    # ================================================================== #
    def action_create_accrual_entry(self):
        self._create_accrual_journal_entry()
        return True

    def action_create_payable_entry(self):
        self._sync_payable_journal_entry()
        return True
