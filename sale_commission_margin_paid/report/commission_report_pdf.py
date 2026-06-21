from odoo import api, models


class ReportCommissionReportPdf(models.AbstractModel):
    _name = "report.sale_commission_margin_paid.report_commission_report_pdf"
    _description = "Commission Report PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}

        wizard_id = data.get("wizard_id")
        if wizard_id:
            wizard = self.env["sale.commission.report.wizard"].browse(wizard_id)
        else:
            wizard = self.env["sale.commission.report.wizard"].browse(docids[:1])

        lines = self.env["sale.commission.achievement.report"].browse(
            data.get("line_ids", [])
        )

        return {
            "doc_ids": wizard.ids,
            "doc_model": "sale.commission.report.wizard",
            "docs": wizard,
            "lines": lines,
        }
