from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    commission_expense_account_id = fields.Many2one(
        "account.account",
        string="Commission Expense Account",
        help="Debited when a commission accrual journal entry is created "
        "(Dr Commission Expense / Cr Commission Accrual) right after the "
        "source invoice is posted and the commission is calculated.",
    )
    commission_accrual_account_id = fields.Many2one(
        "account.account",
        string="Commission Accrual Account",
        help="Liability account used to accrue commissions that have been "
        "earned but not yet paid out to the salesperson. Credited on "
        "accrual, debited when the commission becomes payable.",
    )
    commission_payable_account_id = fields.Many2one(
        "account.account",
        string="Salesperson Payable Account",
        help="Credited when the source invoice becomes fully paid "
        "(Dr Commission Accrual / Cr Salesperson Payable), representing "
        "the amount now actually owed to the salesperson.",
    )
