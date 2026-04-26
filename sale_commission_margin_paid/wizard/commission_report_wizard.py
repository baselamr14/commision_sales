from odoo import api, fields, models, _
from odoo.exceptions import UserError

import io
import base64
import xlsxwriter


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
    customer_ids = fields.Many2many(
        "res.partner",
        string="Customers",
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

        if self.customer_ids:
            domain.append(("partner_id", "in", self.customer_ids.ids))

        if self.only_positive:
            domain.append(("achieved", ">", 0))

        return domain

    def _get_report_lines(self):
        self.ensure_one()
        return self.env["sale.commission.achievement.report"].search(
            self._get_domain(),
            order="date asc, user_id asc, id asc",
        )

    def _prepare_report_data(self):
        self.ensure_one()
        lines = self._get_report_lines()

        if not lines:
            raise UserError(_("No commission lines were found for the selected filters."))

        total_amount = sum(lines.mapped("achieved"))

        return {
            "wizard_id": self.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "salesperson_name": self.salesperson_id.name or "",
            "customer_names": ", ".join(self.customer_ids.mapped("name")) if self.customer_ids else "",
            "only_positive": self.only_positive,
            "total_amount": total_amount,
            "line_ids": lines.ids,
        }

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
        lines = self._get_report_lines()

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
        data = self._prepare_report_data()
        return self.env.ref(
            "sale_commission_margin_paid.action_commission_report_pdf"
        ).report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._get_report_lines()

        if not lines:
            raise UserError(_("No commission lines were found for the selected filters."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Commission Report")

        title_format = workbook.add_format({
            "bold": True,
            "font_size": 14,
        })
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#D9EAF7",
            "border": 1,
        })
        cell_format = workbook.add_format({
            "border": 1,
        })
        date_format = workbook.add_format({
            "border": 1,
            "num_format": "yyyy-mm-dd",
        })
        amount_format = workbook.add_format({
            "border": 1,
            "num_format": "#,##0.00",
        })

        row = 0
        sheet.write(row, 0, "Commission Report", title_format)
        row += 2

        sheet.write(row, 0, "Start Date", header_format)
        sheet.write(row, 1, str(self.date_from or ""), cell_format)
        sheet.write(row, 2, "End Date", header_format)
        sheet.write(row, 3, str(self.date_to or ""), cell_format)
        row += 1

        sheet.write(row, 0, "Salesperson", header_format)
        sheet.write(row, 1, self.salesperson_id.name or "", cell_format)
        sheet.write(row, 2, "Customers", header_format)
        sheet.write(
            row,
            3,
            ", ".join(self.customer_ids.mapped("name")) if self.customer_ids else "",
            cell_format,
        )
        row += 2

        headers = [
            "Date",
            "Salesperson",
            "Customer",
            "Target Name",
            "Achieved",
            "Currency",
        ]

        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        row += 1
        total_amount = 0.0

        for line in lines:
            sheet.write(row, 0, str(line.date or ""), date_format)
            sheet.write(row, 1, line.user_id.name or "", cell_format)
            sheet.write(row, 2, line.partner_id.name or "", cell_format)
            sheet.write(row, 3, line.target_id.display_name or "", cell_format)
            sheet.write_number(row, 4, line.achieved or 0.0, amount_format)
            sheet.write(row, 5, line.currency_id.name or "", cell_format)

            total_amount += line.achieved or 0.0
            row += 1

        sheet.write(row, 3, "Total", header_format)
        sheet.write_number(row, 4, total_amount, amount_format)

        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 22)
        sheet.set_column(2, 2, 24)
        sheet.set_column(3, 3, 24)
        sheet.set_column(4, 4, 14)
        sheet.set_column(5, 5, 12)

        workbook.close()
        output.seek(0)

        file_name = "commission_report_%s_%s.xlsx" % (
            self.date_from or "",
            self.date_to or "",
        )

        attachment = self.env["ir.attachment"].create({
            "name": file_name,
            "type": "binary",
            "datas": base64.b64encode(output.read()),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
# from odoo import api, fields, models, _
# from odoo.exceptions import UserError

# import io
# import base64
# import xlsxwriter


# class CommissionReportWizard(models.TransientModel):
#     _name = "sale.commission.report.wizard"
#     _description = "Commission Report Wizard"

#     date_from = fields.Date(
#         string="Start Date",
#         required=True,
#         default=lambda self: fields.Date.today().replace(day=1),
#     )
#     date_to = fields.Date(
#         string="End Date",
#         required=True,
#         default=fields.Date.today,
#     )
#     salesperson_id = fields.Many2one(
#         "res.users",
#         string="Salesperson",
#     )
#     customer_id = fields.Many2one(
#         "res.partner",
#         string="Customer",
#     )
#     only_positive = fields.Boolean(
#         string="Only Positive Commissions",
#         default=True,
#     )

#     def _get_domain(self):
#         self.ensure_one()

#         if self.date_from and self.date_to and self.date_from > self.date_to:
#             raise UserError(_("Start Date cannot be greater than End Date."))

#         domain = [
#             ("date", ">=", self.date_from),
#             ("date", "<=", self.date_to),
#         ]

#         if self.salesperson_id:
#             domain.append(("user_id", "=", self.salesperson_id.id))

#         if self.customer_id:
#             domain.append(("partner_id", "=", self.customer_id.id))

#         if self.only_positive:
#             domain.append(("achieved", ">", 0))

#         return domain

#     def _get_report_lines(self):
#         self.ensure_one()
#         return self.env["sale.commission.achievement.report"].search(
#             self._get_domain(),
#             order="date asc, user_id asc, id asc",
#         )

#     def _prepare_report_data(self):
#         self.ensure_one()
#         lines = self._get_report_lines()

#         if not lines:
#             raise UserError(_("No commission lines were found for the selected filters."))

#         total_amount = sum(lines.mapped("achieved"))

#         return {
#             "wizard_id": self.id,
#             "date_from": self.date_from,
#             "date_to": self.date_to,
#             "salesperson_name": self.salesperson_id.name or "",
#             "customer_name": self.customer_id.name or "",
#             "only_positive": self.only_positive,
#             "total_amount": total_amount,
#             "line_ids": lines.ids,
#         }

#     def action_view_lines(self):
#         self.ensure_one()
#         domain = self._get_domain()

#         return {
#             "type": "ir.actions.act_window",
#             "name": _("Commission Lines"),
#             "res_model": "sale.commission.achievement.report",
#             "view_mode": "list,pivot,graph",
#             "target": "current",
#             "domain": domain,
#             "context": {
#                 "search_default_group_by_user_id": 1,
#             },
#         }

#     def action_open_create_vendor_bill(self):
#         self.ensure_one()
#         lines = self._get_report_lines()

#         if not lines:
#             raise UserError(_("No commission lines were found for the selected period."))

#         users = lines.mapped("user_id")
#         if len(users) != 1:
#             raise UserError(_("Please filter the report to one salesperson before creating a vendor bill."))

#         return {
#             "type": "ir.actions.act_window",
#             "name": _("Create Vendor Bill"),
#             "res_model": "sale.commission.create.bill.wizard",
#             "view_mode": "form",
#             "target": "new",
#             "context": {
#                 "active_model": "sale.commission.achievement.report",
#                 "active_ids": lines.ids,
#             },
#         }

#     def action_print_pdf(self):
#         self.ensure_one()
#         data = self._prepare_report_data()
#         return self.env.ref(
#             "sale_commission_margin_paid.action_commission_report_pdf"
#         ).report_action(self, data=data)

#     def action_export_xlsx(self):
#         self.ensure_one()
#         lines = self._get_report_lines()

#         if not lines:
#             raise UserError(_("No commission lines were found for the selected filters."))

#         output = io.BytesIO()
#         workbook = xlsxwriter.Workbook(output, {"in_memory": True})
#         sheet = workbook.add_worksheet("Commission Report")

#         title_format = workbook.add_format({
#             "bold": True,
#             "font_size": 14,
#         })
#         header_format = workbook.add_format({
#             "bold": True,
#             "bg_color": "#D9EAF7",
#             "border": 1,
#         })
#         cell_format = workbook.add_format({
#             "border": 1,
#         })
#         date_format = workbook.add_format({
#             "border": 1,
#             "num_format": "yyyy-mm-dd",
#         })
#         amount_format = workbook.add_format({
#             "border": 1,
#             "num_format": "#,##0.00",
#         })

#         row = 0
#         sheet.write(row, 0, "Commission Report", title_format)
#         row += 2

#         sheet.write(row, 0, "Start Date", header_format)
#         sheet.write(row, 1, str(self.date_from or ""), cell_format)
#         sheet.write(row, 2, "End Date", header_format)
#         sheet.write(row, 3, str(self.date_to or ""), cell_format)
#         row += 1

#         sheet.write(row, 0, "Salesperson", header_format)
#         sheet.write(row, 1, self.salesperson_id.name or "", cell_format)
#         sheet.write(row, 2, "Customer", header_format)
#         sheet.write(row, 3, self.customer_id.name or "", cell_format)
#         row += 2

#         headers = [
#             "Date",
#             "Salesperson",
#             "Customer",
#             "Target Name",
#             "Achieved",
#             "Currency",
#         ]

#         for col, header in enumerate(headers):
#             sheet.write(row, col, header, header_format)

#         row += 1
#         total_amount = 0.0

#         for line in lines:
#             sheet.write(row, 0, str(line.date or ""), date_format)
#             sheet.write(row, 1, line.user_id.name or "", cell_format)
#             sheet.write(row, 2, line.partner_id.name or "", cell_format)
#             sheet.write(row, 3, line.target_id.display_name or "", cell_format)
#             sheet.write_number(row, 4, line.achieved or 0.0, amount_format)
#             sheet.write(row, 5, line.currency_id.name or "", cell_format)

#             total_amount += line.achieved or 0.0
#             row += 1

#         sheet.write(row, 3, "Total", header_format)
#         sheet.write_number(row, 4, total_amount, amount_format)

#         sheet.set_column(0, 0, 14)
#         sheet.set_column(1, 1, 22)
#         sheet.set_column(2, 2, 24)
#         sheet.set_column(3, 3, 24)
#         sheet.set_column(4, 4, 14)
#         sheet.set_column(5, 5, 12)

#         workbook.close()
#         output.seek(0)

#         file_name = "commission_report_%s_%s.xlsx" % (
#             self.date_from or "",
#             self.date_to or "",
#         )

#         attachment = self.env["ir.attachment"].create({
#             "name": file_name,
#             "type": "binary",
#             "datas": base64.b64encode(output.read()),
#             "res_model": self._name,
#             "res_id": self.id,
#             "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#         })

#         return {
#             "type": "ir.actions.act_url",
#             "url": "/web/content/%s?download=true" % attachment.id,
#             "target": "self",
#         }
# # from odoo import api, fields, models, _
# # from odoo.exceptions import UserError

# # import io
# # import base64
# # import xlsxwriter


# # class CommissionReportWizard(models.TransientModel):
# #     _name = "sale.commission.report.wizard"
# #     _description = "Commission Report Wizard"

# #     date_from = fields.Date(
# #         string="Start Date",
# #         required=True,
# #         default=lambda self: fields.Date.today().replace(day=1),
# #     )
# #     date_to = fields.Date(
# #         string="End Date",
# #         required=True,
# #         default=fields.Date.today,
# #     )
# #     salesperson_id = fields.Many2one(
# #         "res.users",
# #         string="Salesperson",
# #     )
# #     customer_id = fields.Many2one(
# #         "res.partner",
# #         string="Customer",
# #     )
# #     only_positive = fields.Boolean(
# #         string="Only Positive Commissions",
# #         default=True,
# #     )

# #     def _get_domain(self):
# #         self.ensure_one()

# #         if self.date_from and self.date_to and self.date_from > self.date_to:
# #             raise UserError(_("Start Date cannot be greater than End Date."))

# #         domain = [
# #             ("date", ">=", self.date_from),
# #             ("date", "<=", self.date_to),
# #         ]

# #         if self.salesperson_id:
# #             domain.append(("user_id", "=", self.salesperson_id.id))

# #         if self.customer_id:
# #             domain.append(("partner_id", "=", self.customer_id.id))

# #         if self.only_positive:
# #             domain.append(("achieved", ">", 0))

# #         return domain

# #     def _get_report_lines(self):
# #         self.ensure_one()
# #         return self.env["sale.commission.achievement.report"].search(
# #             self._get_domain(),
# #             order="date asc, user_id asc, id asc",
# #         )

# #     def _prepare_report_data(self):
# #         self.ensure_one()
# #         lines = self._get_report_lines()

# #         if not lines:
# #             raise UserError(_("No commission lines were found for the selected filters."))

# #         total_amount = sum(lines.mapped("achieved"))

# #         return {
# #             "wizard_id": self.id,
# #             "date_from": self.date_from,
# #             "date_to": self.date_to,
# #             "salesperson_name": self.salesperson_id.name or "",
# #             "customer_name": self.customer_id.name or "",
# #             "only_positive": self.only_positive,
# #             "total_amount": total_amount,
# #             "line_ids": lines.ids,
# #         }

# #     def action_view_lines(self):
# #         self.ensure_one()
# #         domain = self._get_domain()

# #         return {
# #             "type": "ir.actions.act_window",
# #             "name": _("Commission Lines"),
# #             "res_model": "sale.commission.achievement.report",
# #             "view_mode": "list,pivot,graph",
# #             "target": "current",
# #             "domain": domain,
# #             "context": {
# #                 "search_default_group_by_user_id": 1,
# #             },
# #         }

# #     def action_open_create_vendor_bill(self):
# #         self.ensure_one()
# #         lines = self._get_report_lines()

# #         if not lines:
# #             raise UserError(_("No commission lines were found for the selected period."))

# #         users = lines.mapped("user_id")
# #         if len(users) != 1:
# #             raise UserError(_("Please filter the report to one salesperson before creating a vendor bill."))

# #         return {
# #             "type": "ir.actions.act_window",
# #             "name": _("Create Vendor Bill"),
# #             "res_model": "sale.commission.create.bill.wizard",
# #             "view_mode": "form",
# #             "target": "new",
# #             "context": {
# #                 "active_model": "sale.commission.achievement.report",
# #                 "active_ids": lines.ids,
# #             },
# #         }

# #     def action_print_pdf(self):
# #         self.ensure_one()
# #         data = self._prepare_report_data()
# #         return self.env.ref(
# #             "sale_commission_margin_paid.action_commission_report_pdf"
# #         ).report_action(self, data=data)

# #     def action_export_xlsx(self):
# #         self.ensure_one()
# #         lines = self._get_report_lines()

# #         if not lines:
# #             raise UserError(_("No commission lines were found for the selected filters."))

# #         output = io.BytesIO()
# #         workbook = xlsxwriter.Workbook(output, {"in_memory": True})
# #         sheet = workbook.add_worksheet("Commission Report")

# #         title_format = workbook.add_format({
# #             "bold": True,
# #             "font_size": 14,
# #         })
# #         header_format = workbook.add_format({
# #             "bold": True,
# #             "bg_color": "#D9EAF7",
# #             "border": 1,
# #         })
# #         cell_format = workbook.add_format({
# #             "border": 1,
# #         })
# #         date_format = workbook.add_format({
# #             "border": 1,
# #             "num_format": "yyyy-mm-dd",
# #         })
# #         amount_format = workbook.add_format({
# #             "border": 1,
# #             "num_format": "#,##0.00",
# #         })

# #         row = 0
# #         sheet.write(row, 0, "Commission Report", title_format)
# #         row += 2

# #         sheet.write(row, 0, "Start Date", header_format)
# #         sheet.write(row, 1, str(self.date_from or ""), cell_format)
# #         sheet.write(row, 2, "End Date", header_format)
# #         sheet.write(row, 3, str(self.date_to or ""), cell_format)
# #         row += 1

# #         sheet.write(row, 0, "Salesperson", header_format)
# #         sheet.write(row, 1, self.salesperson_id.name or "", cell_format)
# #         sheet.write(row, 2, "Customer", header_format)
# #         sheet.write(row, 3, self.customer_id.name or "", cell_format)
# #         row += 2

# #         headers = [
# #             "Date",
# #             "Salesperson",
# #             "Source",
# #             "Customer",
# #             "Target",
# #             "Target Name",
# #             "Achieved",
# #             "Currency",
# #         ]

# #         for col, header in enumerate(headers):
# #             sheet.write(row, col, header, header_format)

# #         row += 1
# #         total_amount = 0.0

# #         for line in lines:
# #             sheet.write(row, 0, str(line.date or ""), date_format)
# #             sheet.write(row, 1, line.user_id.name or "", cell_format)
# #             sheet.write(row, 2, str(line.related_res_id or ""), cell_format)
# #             sheet.write(row, 3, line.partner_id.name or "", cell_format)
# #             sheet.write(row, 4, line.target_id.id or 0, cell_format)
# #             sheet.write(row, 5, line.target_id.display_name or "", cell_format)
# #             sheet.write_number(row, 6, line.achieved or 0.0, amount_format)
# #             sheet.write(row, 7, line.currency_id.name or "", cell_format)

# #             total_amount += line.achieved or 0.0
# #             row += 1

# #         sheet.write(row, 5, "Total", header_format)
# #         sheet.write_number(row, 6, total_amount, amount_format)

# #         sheet.set_column(0, 0, 14)
# #         sheet.set_column(1, 1, 22)
# #         sheet.set_column(2, 2, 28)
# #         sheet.set_column(3, 3, 24)
# #         sheet.set_column(4, 4, 14)
# #         sheet.set_column(5, 5, 24)
# #         sheet.set_column(6, 6, 14)
# #         sheet.set_column(7, 7, 12)

# #         workbook.close()
# #         output.seek(0)

# #         file_name = "commission_report_%s_%s.xlsx" % (
# #             self.date_from or "",
# #             self.date_to or "",
# #         )

# #         attachment = self.env["ir.attachment"].create({
# #             "name": file_name,
# #             "type": "binary",
# #             "datas": base64.b64encode(output.read()),
# #             "res_model": self._name,
# #             "res_id": self.id,
# #             "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
# #         })

# #         return {
# #             "type": "ir.actions.act_url",
# #             "url": "/web/content/%s?download=true" % attachment.id,
# #             "target": "self",
# #         }
