from odoo import api, fields, models


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