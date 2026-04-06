from odoo import fields, models


class SaleReport(models.Model):
    _inherit = "sale.report"

    purchase_cost = fields.Float(
        string="Avg. Cost Price",
        readonly=True,
        aggregator="avg",
    )

    cost_total = fields.Float(
        string="Total Cost",
        readonly=True,
        aggregator="sum",
    )

    profit_amount = fields.Float(
        string="Profit",
        readonly=True,
        aggregator="sum",
    )

    commission_amount = fields.Float(
        string="Commission Amount",
        readonly=True,
        aggregator="sum",
    )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()

        res["purchase_cost"] = "AVG(l.purchase_cost)"
        res["cost_total"] = "SUM(l.purchase_cost * l.product_uom_qty)"
        res["profit_amount"] = "SUM(l.price_subtotal - (l.purchase_cost * l.product_uom_qty))"
        res["commission_amount"] = """
            SUM(
                CASE
                    WHEN (l.price_subtotal - (l.purchase_cost * l.product_uom_qty)) > 0
                    THEN ((l.price_subtotal - (l.purchase_cost * l.product_uom_qty)) * l.commission_percent / 100.0)
                    ELSE 0
                END
            )
        """
        return res