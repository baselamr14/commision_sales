from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    commission_expense_account_id = fields.Many2one(
        "account.account",
        related="company_id.commission_expense_account_id",
        readonly=False,
        string="Commission Expense Account",
    )
    commission_accrual_account_id = fields.Many2one(
        "account.account",
        related="company_id.commission_accrual_account_id",
        readonly=False,
        string="Commission Accrual Account",
    )
    commission_payable_account_id = fields.Many2one(
        "account.account",
        related="company_id.commission_payable_account_id",
        readonly=False,
        string="Salesperson Payable Account",
    )
