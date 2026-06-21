from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleCommissionInvoiceMap(models.Model):
    _name = "sale.commission.invoice.map"
    _description = "Commission Invoice Mapping"
    _order = "id desc"

    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        required=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        index=True,
    )

    plan_id = fields.Many2one(
        "sale.commission.plan",
        string="Commission Plan",
        required=True,
        index=True,
    )
    target_id = fields.Many2one(
        "sale.commission.plan.target",
        string="Target Period",
        required=True,
        index=True,
    )

    source_model = fields.Char(
        string="Source Model",
        required=True,
        index=True,
    )
    source_res_id = fields.Integer(
        string="Source Record ID",
        required=True,
        index=True,
    )

    source_invoice_id = fields.Many2one(
        "account.move",
        string="Source Invoice",
        index=True,
    )
    source_date = fields.Date(
        string="Commission Date",
        index=True,
    )
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
    )

    achieved_amount = fields.Monetary(
        string="Commission Amount",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
    )

    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        index=True,
    )
    vendor_bill_line_id = fields.Many2one(
        "account.move.line",
        string="Vendor Bill Line",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("invoiced", "Invoiced"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
    )

    reference = fields.Char(
        string="Reference",
        compute="_compute_reference",
        store=True,
    )

    # ------------------------------------------------------------------ #
    #  Accrual / payable journal entry tracking                          #
    # ------------------------------------------------------------------ #
    accrual_move_id = fields.Many2one(
        "account.move",
        string="Accrual Journal Entry",
        readonly=True,
        copy=False,
        help="Journal entry booking the commission expense against the "
        "commission accrual liability, created when the source invoice "
        "is posted.",
    )
    payable_move_id = fields.Many2one(
        "account.move",
        string="Payable Journal Entry",
        readonly=True,
        copy=False,
        help="Journal entry moving the commission from accrual to a "
        "salesperson payable account, created when the source invoice "
        "is fully paid.",
    )
    journal_state = fields.Selection(
        [
            ("pending", "Pending Accrual"),
            ("accrued", "Accrued"),
            ("payable", "Payable"),
        ],
        string="Accounting Status",
        default="pending",
        required=True,
        index=True,
        copy=False,
        help="Pending Accrual: commission earned but no JE created yet.\n"
        "Accrued: Dr Commission Expense / Cr Commission Accrual booked.\n"
        "Payable: invoice has been paid, Dr Commission Accrual / "
        "Cr Salesperson Payable booked.",
    )

    _sql_constraints = [
        (
            "sale_commission_invoice_map_unique",
            "unique(user_id, plan_id, target_id, source_model, source_res_id, company_id)",
            "This commission line has already been tracked.",
        ),
    ]

    @api.depends("source_model", "source_res_id")
    def _compute_reference(self):
        for rec in self:
            if rec.source_model and rec.source_res_id:
                rec.reference = f"{rec.source_model},{rec.source_res_id}"
            else:
                rec.reference = False

    # ------------------------------------------------------------------ #
    #  Accounting settings helpers                                       #
    # ------------------------------------------------------------------ #
    def _get_commission_accounts(self):
        """Return (expense_account, accrual_account, payable_account) for
        self.company_id, raising a clear error if any is missing."""
        self.ensure_one()
        params = self.env["ir.config_parameter"].sudo()
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
            raise UserError(
                _(
                    "Please configure the following accounts in "
                    "Settings > Sales > Commissions before commission "
                    "journal entries can be created: %(accounts)s",
                    accounts=", ".join(missing),
                )
            )

        return expense_account, accrual_account, payable_account

    # ------------------------------------------------------------------ #
    #  Accrual JE: Dr Commission Expense / Cr Commission Accrual         #
    # ------------------------------------------------------------------ #
    def _create_accrual_journal_entry(self):
        """Create the accrual JE for each record that doesn't have one yet.
        Called once the source invoice is posted and the commission
        amount is known. Idempotent: records already in 'accrued' or
        'payable' journal_state are skipped.
        """
        AccountMove = self.env["account.move"]

        for rec in self:
            if rec.journal_state != "pending" or rec.accrual_move_id:
                continue
            if not rec.achieved_amount:
                continue

            expense_account, accrual_account, _payable_account = (
                rec._get_commission_accounts()
            )

            journal = rec._get_commission_misc_journal()

            move = AccountMove.create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": rec._get_commission_entry_date(),
                "ref": _(
                    "Commission accrual - %(salesperson)s - %(ref)s",
                    salesperson=rec.user_id.name,
                    ref=rec.reference or rec.source_res_id,
                ),
                "line_ids": [
                    (0, 0, {
                        "name": _("Commission expense - %(ref)s", ref=rec.reference),
                        "account_id": expense_account.id,
                        "partner_id": rec.partner_id.id,
                        "debit": rec.achieved_amount,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "name": _("Commission accrual - %(ref)s", ref=rec.reference),
                        "account_id": accrual_account.id,
                        "partner_id": rec.partner_id.id,
                        "debit": 0.0,
                        "credit": rec.achieved_amount,
                    }),
                ],
            })
            move._post()

            rec.write({
                "accrual_move_id": move.id,
                "journal_state": "accrued",
            })

    # ------------------------------------------------------------------ #
    #  Payable JE: Dr Commission Accrual / Cr Salesperson Payable        #
    # ------------------------------------------------------------------ #
    def _create_payable_journal_entry(self):
        """Create the payable JE for each record whose source invoice has
        just become fully paid. Idempotent: records not in 'accrued'
        journal_state, or that already have a payable_move_id, are
        skipped.
        """
        AccountMove = self.env["account.move"]

        for rec in self:
            if rec.journal_state != "accrued" or rec.payable_move_id:
                continue
            if not rec.achieved_amount:
                continue

            _expense_account, accrual_account, payable_account = (
                rec._get_commission_accounts()
            )

            journal = rec._get_commission_misc_journal()

            move = AccountMove.create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": fields.Date.context_today(rec),
                "ref": _(
                    "Commission payable - %(salesperson)s - %(ref)s",
                    salesperson=rec.user_id.name,
                    ref=rec.reference or rec.source_res_id,
                ),
                "line_ids": [
                    (0, 0, {
                        "name": _("Commission accrual reversal - %(ref)s", ref=rec.reference),
                        "account_id": accrual_account.id,
                        "partner_id": rec.partner_id.id,
                        "debit": rec.achieved_amount,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "name": _("Commission payable - %(ref)s", ref=rec.reference),
                        "account_id": payable_account.id,
                        "partner_id": rec.partner_id.id,
                        "debit": 0.0,
                        "credit": rec.achieved_amount,
                    }),
                ],
            })
            move._post()

            rec.write({
                "payable_move_id": move.id,
                "journal_state": "payable",
            })

    def _get_commission_misc_journal(self):
        """Return the miscellaneous journal used for commission JEs."""
        self.ensure_one()
        company = self.company_id or self.env.company
        journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company.id),
        ], limit=1)
        if not journal:
            raise UserError(
                _("No miscellaneous journal found for company %(company)s.",
                  company=company.name)
            )
        return journal

    def _get_commission_entry_date(self):
        """Resolve the date to use for the accrual journal entry.

        Priority: the record's stored commission date, then the source
        invoice's own date, and only as a last resort today's date. This
        keeps the accrual JE aligned with the invoice period rather than
        defaulting to whenever the invoice happened to be posted.
        """
        self.ensure_one()
        if self.source_date:
            return self.source_date
        if self.source_invoice_id:
            return (
                self.source_invoice_id.invoice_date
                or self.source_invoice_id.date
            )
        return fields.Date.context_today(self)
