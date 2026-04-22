from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleCommissionCreateBillWizard(models.TransientModel):
    _name = "sale.commission.create.bill.wizard"
    _description = "Create Commission Vendor Bill"

    salesperson_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        readonly=True,
    )

    date_from = fields.Date(string="From Date", readonly=True)
    date_to = fields.Date(string="To Date", readonly=True)

    bill_date = fields.Date(
        string="Bill Date",
        required=True,
        default=fields.Date.context_today,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Vendor Bills Journal",
        required=True,
        domain=[("type", "=", "purchase")],
        default=lambda self: self._default_purchase_journal(),
    )
    commission_product_id = fields.Many2one(
        "product.product",
        string="Commission Product",
        required=True,
    )

    line_ids = fields.One2many(
        "sale.commission.create.bill.wizard.line",
        "wizard_id",
        string="Commission Lines To Invoice",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        readonly=True,
    )
    total_amount = fields.Monetary(
        string="Total Commission",
        compute="_compute_total_amount",
        currency_field="currency_id",
    )

    @api.model
    def _default_purchase_journal(self):
        return self.env["account.journal"].search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )

    @api.depends("line_ids.selected", "line_ids.commission_amount")
    def _compute_total_amount(self):
        for wizard in self:
            wizard.total_amount = sum(
                wizard.line_ids.filtered("selected").mapped("commission_amount")
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        if self.env.context.get("active_model") != "sale.commission.achievement.report":
            raise UserError(_("This wizard must be opened from commission achievement lines."))

        active_ids = self.env.context.get("active_ids", [])
        if not active_ids:
            raise UserError(_("Please select at least one commission line."))

        lines = self.env["sale.commission.achievement.report"].browse(active_ids).exists()
        if not lines:
            raise UserError(_("Selected commission lines were not found."))

        users = lines.mapped("user_id")
        if len(users) != 1:
            raise UserError(_("Please select commission lines for one salesperson only."))

        salesperson = users[0]
        partner = salesperson.partner_id
        if not partner:
            raise UserError(_("The selected salesperson does not have a linked partner."))

        existing_maps = self.env["sale.commission.invoice.map"].search([
            ("user_id", "=", salesperson.id),
            ("plan_id", "in", lines.mapped("plan_id").ids),
            ("target_id", "in", lines.mapped("target_id").ids),
            ("source_model", "=", "account.move"),
            ("source_res_id", "in", lines.mapped("related_res_id").ids),
            ("state", "=", "invoiced"),
        ])

        already_invoiced_keys = {
            (m.plan_id.id, m.target_id.id, m.source_model, m.source_res_id)
            for m in existing_maps
        }

        wizard_lines = []
        kept_lines = self.env["sale.commission.achievement.report"]

        for line in lines:
            source_res_id = line.related_res_id.id if line.related_res_id else False
            key = (line.plan_id.id, line.target_id.id, line.related_res_model, source_res_id)

            if key in already_invoiced_keys:
                continue

            kept_lines |= line
            wizard_lines.append((0, 0, {
                "selected": True,
                "report_line_id": line.id,
                "target_id": line.target_id.id,
                "plan_id": line.plan_id.id,
                "source_model": line.related_res_model,
                "source_res_id": source_res_id,
                "source_invoice_id": source_res_id if line.related_res_model == "account.move" else False,
                "customer_id": line.partner_id.id,
                "date": line.date,
                "commission_amount": line.achieved,
                "currency_id": line.currency_id.id,
                "display_name": line.related_res_id.display_name if line.related_res_id else str(source_res_id),
            }))

        if not wizard_lines:
            raise UserError(_("All selected commission lines are already invoiced."))

        dates = kept_lines.mapped("date")
        res.update({
            "salesperson_id": salesperson.id,
            "partner_id": partner.id,
            "date_from": min(dates) if dates else False,
            "date_to": max(dates) if dates else False,
            "currency_id": kept_lines[:1].currency_id.id,
            "line_ids": wizard_lines,
        })
        return res

    def action_create_vendor_bill(self):
        self.ensure_one()

        selected_lines = self.line_ids.filtered("selected")
        if not selected_lines:
            raise UserError(_("Please select at least one commission line to invoice."))

        if any(line.commission_amount <= 0 for line in selected_lines):
            raise UserError(_("Selected lines must have positive commission amounts."))

        if not self.journal_id:
            raise UserError(_("Please choose a purchase journal."))

        if not self.commission_product_id:
            raise UserError(_("Please choose a commission product."))

        invoice_line_commands = []
        map_vals_list = []

        for line in selected_lines:
            description = _("Commission - %(ref)s", ref=line.display_name or line.source_res_id)

            invoice_line_commands.append((0, 0, {
                "product_id": self.commission_product_id.id,
                "name": description,
                "quantity": 1.0,
                "price_unit": line.commission_amount,
            }))

            map_vals_list.append({
                "user_id": self.salesperson_id.id,
                "partner_id": self.partner_id.id,
                "plan_id": line.plan_id.id,
                "target_id": line.target_id.id,
                "source_model": line.source_model,
                "source_res_id": line.source_res_id,
                "source_invoice_id": line.source_invoice_id.id if line.source_invoice_id else False,
                "source_date": line.date,
                "customer_id": line.customer_id.id,
                "achieved_amount": line.commission_amount,
                "currency_id": line.currency_id.id,
                "company_id": self.env.company.id,
                "state": "draft",
            })

        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_id.id,
            "invoice_date": self.bill_date,
            "journal_id": self.journal_id.id,
            "company_id": self.env.company.id,
            "invoice_line_ids": invoice_line_commands,
        })

        for index, vals in enumerate(map_vals_list):
            vals.update({
                "vendor_bill_id": bill.id,
                "vendor_bill_line_id": bill.invoice_line_ids[index].id if index < len(bill.invoice_line_ids) else False,
                "state": "invoiced",
            })
            self.env["sale.commission.invoice.map"].create(vals)

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": bill.id,
            "view_mode": "form",
            "target": "current",
        }


class SaleCommissionCreateBillWizardLine(models.TransientModel):
    _name = "sale.commission.create.bill.wizard.line"
    _description = "Create Commission Vendor Bill Line"

    wizard_id = fields.Many2one(
        "sale.commission.create.bill.wizard",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(default=True)

    report_line_id = fields.Integer(string="Report Line ID")
    target_id = fields.Many2one("sale.commission.plan.target", string="Target")
    plan_id = fields.Many2one("sale.commission.plan", string="Plan")

    source_model = fields.Char(string="Source Model")
    source_res_id = fields.Integer(string="Source Record ID")
    source_invoice_id = fields.Many2one("account.move", string="Invoice")

    customer_id = fields.Many2one("res.partner", string="Customer")
    date = fields.Date(string="Date")
    commission_amount = fields.Monetary(string="Commission Amount", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", string="Currency")
    display_name = fields.Char(string="Reference")