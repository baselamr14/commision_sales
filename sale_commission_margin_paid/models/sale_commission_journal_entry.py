from odoo import fields, models


class SaleCommissionJournalEntry(models.Model):
    """Append-only ledger of every commission journal entry.

    Each row records ONE posted journal entry (accrual or payable) created
    for a commission record. Rows are never mutated once created -- every
    accounting event (posting, partial payment, refund) adds a new row.
    This mirrors accounting itself (you post reversing entries, you never
    edit a posted one) and gives a full audit trail.
    """

    _name = "sale.commission.journal.entry"
    _description = "Commission Journal Entry Ledger"
    _order = "id desc"

    map_id = fields.Many2one(
        "sale.commission.invoice.map",
        string="Commission Record",
        required=True,
        ondelete="cascade",
        index=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        required=True,
        readonly=True,
        index=True,
    )
    entry_type = fields.Selection(
        [
            ("accrual", "Accrual"),
            ("payable", "Payable"),
        ],
        string="Entry Type",
        required=True,
        readonly=True,
        index=True,
        help="Accrual: booked when the source document is posted "
        "(Dr/Cr Expense vs Accrual).\n"
        "Payable: booked as cash is collected/refunded "
        "(Dr/Cr Accrual vs Payable).",
    )
    amount = fields.Monetary(
        string="Amount",
        readonly=True,
        help="Commission amount booked by this journal entry. Signed: "
        "positive for an invoice's commission, negative for a credit "
        "note's reversal.",
    )
    paid_fraction_at_posting = fields.Float(
        string="Paid Fraction at Posting",
        readonly=True,
        digits=(16, 6),
        help="For payable entries: the cumulative paid fraction of the "
        "source document at the moment this entry was booked. Used to "
        "compute the incremental delta on the next payment.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="map_id.currency_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="map_id.company_id",
        store=True,
        readonly=True,
    )
