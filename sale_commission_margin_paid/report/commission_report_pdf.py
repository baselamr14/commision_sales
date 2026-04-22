from odoo import api, models


class ReportCommissionReportPdf(models.AbstractModel):
    _name = "report.sale_commission_margin_paid.report_commission_report_pdf"
    _description = "Commission Report PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["sale.commission.report.wizard"].browse(docids)
        wizard.ensure_one()

        line_ids = (data or {}).get("line_ids", [])
        lines = self.env["sale.commission.achievement.report"].browse(line_ids)

        return {
            "doc_ids": docids,
            "doc_model": "sale.commission.report.wizard",
            "docs": wizard,
            "data": data or {},
            "lines": lines,
        }
