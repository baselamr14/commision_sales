from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CommissionReportWizard(models.TransientModel):
    _name = "sale.commission.report.wizard"
    _description = "Commission Report Wizard"

    date_from = fields.Date(
        string="Start Date",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string="End Date",
        required=True,
        default=fields.Date.today,
    )
    salesperson_id = fields.Many2one(
        "res.users",
        string="Salesperson",
    )
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
    )
    only_positive = fields.Boolean(
        string="Only Positive Commissions",
        default=True,
    )

    def _get_domain(self):
        self.ensure_one()

        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("Start Date cannot be greater than End Date."))

        domain = [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]

        if self.salesperson_id:
            domain.append(("user_id", "=", self.salesperson_id.id))

        if self.customer_id:
            domain.append(("partner_id", "=", self.customer_id.id))

        if self.only_positive:
            domain.append(("achieved", ">", 0))

        return domain

    def action_view_lines(self):
        self.ensure_one()
        domain = self._get_domain()

        return {
            "type": "ir.actions.act_window",
            "name": _("Commission Lines"),
            "res_model": "sale.commission.achievement.report",
            "view_mode": "list,pivot,graph",
            "target": "current",
            "domain": domain,
            "context": {
                "search_default_group_by_user_id": 1,
            },
        }

    def action_open_create_vendor_bill(self):
        self.ensure_one()
        domain = self._get_domain()

        lines = self.env["sale.commission.achievement.report"].search(domain)

        if not lines:
            raise UserError(_("No commission lines were found for the selected period."))

        users = lines.mapped("user_id")
        if len(users) != 1:
            raise UserError(_("Please filter the report to one salesperson before creating a vendor bill."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Create Vendor Bill"),
            "res_model": "sale.commission.create.bill.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "sale.commission.achievement.report",
                "active_ids": lines.ids,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        raise UserError(_("PDF report is the next step. First let us finish the base reporting flow."))

    def action_export_xlsx(self):
        self.ensure_one()
        raise UserError(_("XLSX export is the next step. First let us finish the base reporting flow."))
