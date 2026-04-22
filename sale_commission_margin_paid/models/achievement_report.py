import logging
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleCommissionPlanAchievement(models.Model):
    _inherit = "sale.commission.plan.achievement"

    type = fields.Selection(
        selection_add=[("margin_paid", "Margin (Paid Invoices)")],
        ondelete={"margin_paid": "cascade"},
    )


class SaleCommissionAchievementReport(models.Model):
    _inherit = "sale.commission.achievement.report"

    @api.model
    def _get_invoices_rates(self):
        _logger.warning("CUSTOM _get_invoices_rates CALLED")
        rates = super()._get_invoices_rates()
        return rates + ["margin_paid"]

    @api.model
    def _get_filtered_moves_cte(self, users=None, teams=None):
        _logger.warning("CUSTOM _get_filtered_moves_cte CALLED")
        date_from, date_to = self._get_achievement_default_dates()
        today = fields.Date.today().strftime("%Y-%m-%d")
        date_from_str = date_from and datetime.strftime(date_from, "%Y-%m-%d")
        date_from_condition = f"""AND date >= '{date_from_str}'""" if date_from_str else ""
        query = f"""
        filtered_moves AS (
            SELECT
                    account_move.id::bigint,
                    account_move.team_id,
                    account_move.move_type,
                    account_move.state,
                    account_move.payment_state,
                    account_move.invoice_currency_rate,
                    account_move.company_id,
                    account_move.currency_id,
                    account_move.invoice_user_id,
                    account_move.date,
                    account_move.partner_id
              FROM account_move
             WHERE account_move.move_type IN ('out_invoice', 'out_refund')
               AND state = 'posted'
             {'AND invoice_user_id in (%s)' % ','.join(str(i) for i in users.ids) if users else ''}
             {'AND team_id in (%s)' % ','.join(str(i) for i in teams.ids) if teams else ''}
               {date_from_condition}
               AND date <= '{datetime.strftime(date_to, "%Y-%m-%d") if date_to else today}'
        )
        """
        return query

    @api.model
    def _get_invoice_rates_product(self):
        _logger.warning("CUSTOM _get_invoice_rates_product CALLED")
        return """
        CASE
            WHEN fm.move_type = 'out_invoice' THEN
                rules.amount_invoiced_rate * aml.price_subtotal / fm.invoice_currency_rate +
                rules.qty_invoiced_rate * aml.quantity +
                CASE
                    WHEN fm.payment_state = 'paid' THEN
                        rules.margin_paid_rate * (
                            aml.price_subtotal
                            - (
                                aml.quantity
                                * COALESCE((pp.standard_price ->> fm.company_id::text)::numeric, 0.0)
                            )
                        ) / fm.invoice_currency_rate
                    ELSE 0
                END
            WHEN fm.move_type = 'out_refund' THEN
                (
                    rules.amount_invoiced_rate * aml.price_subtotal / fm.invoice_currency_rate +
                    rules.qty_invoiced_rate * aml.quantity +
                    CASE
                        WHEN fm.payment_state = 'paid' THEN
                            rules.margin_paid_rate * (
                                aml.price_subtotal
                                - (
                                    aml.quantity
                                    * COALESCE((pp.standard_price ->> fm.company_id::text)::numeric, 0.0)
                                )
                            ) / fm.invoice_currency_rate
                        ELSE 0
                    END
                ) * -1
        END
        """

    @api.model
    def _invoices_lines(self, users=None, teams=None):
        _logger.warning("CUSTOM _invoices_lines CALLED")
        return f"""
{self._get_filtered_moves_cte(users=users, teams=teams)},
invoices_rules AS (
    SELECT
        scpa.id::bigint,
        COALESCE(scpu.date_from, scp.date_from) AS date_from,
        COALESCE(scpu.date_to, scp.date_to) AS date_to,
        scpu.user_id AS user_id,
        scp.team_id AS team_id,
        scp.id AS plan_id,
        scpa.product_id,
        scpa.product_categ_id,
        scp.company_id,
        scp.currency_id AS currency_id,
        scp.user_type::text = 'team'::text AS team_rule,
        {self._rate_to_case(self._get_invoices_rates())}
        {self._select_rules()}
    FROM sale_commission_plan_achievement scpa
    JOIN sale_commission_plan scp ON scp.id = scpa.plan_id
    JOIN sale_commission_plan_user scpu ON scpa.plan_id = scpu.plan_id
    WHERE scp.active
      AND scp.state::text = 'approved'::text
      AND scpa.type::text IN ({','.join("'%s'::character varying" % r for r in self._get_invoices_rates())})
    {'AND scpu.user_id in (%s)' % ','.join(str(i) for i in users.ids) if users else ''}
),
invoice_commission_lines_team AS (
    SELECT
       (MAX(aml.id)::bigint << 20) | max(rules.id)::bigint << 10 | rules.user_id << 10 as id,
       {self._select_invoices()}
    FROM invoices_rules rules
         {self._join_invoices(join_type='team')}
    WHERE {self._where_invoices()}
      AND rules.team_rule
      AND fm.team_id = rules.team_id
    {'AND fm.team_id in (%s)' % ','.join(str(i) for i in teams.ids) if teams else ''}
      AND fm.date BETWEEN rules.date_from AND rules.date_to
      AND (rules.product_id IS NULL OR rules.product_id = aml.product_id)
      AND (rules.product_categ_id IS NULL OR rules.product_categ_id = pt.categ_id)
      AND (
            rules.margin_paid_rate = 0
            OR fm.payment_state = 'paid'
          )
    GROUP BY
        fm.id,
        rules.plan_id,
        rules.user_id
),
invoice_commission_lines_user AS (
    SELECT
       row_number() over(order by fm.id, rules.plan_id, rules.user_id) as id,
       {self._select_invoices()}
    FROM invoices_rules rules
         {self._join_invoices(join_type='user')}
    WHERE {self._where_invoices()}
      AND NOT rules.team_rule
      AND fm.invoice_user_id = rules.user_id
    {'AND fm.invoice_user_id in (%s)' % ','.join(str(i) for i in users.ids) if users else ''}
      AND fm.date BETWEEN rules.date_from AND rules.date_to
      AND (rules.product_id IS NULL OR rules.product_id = aml.product_id)
      AND (rules.product_categ_id IS NULL OR rules.product_categ_id = pt.categ_id)
      AND (
            rules.margin_paid_rate = 0
            OR fm.payment_state = 'paid'
          )
    GROUP BY
        fm.id,
        rules.plan_id,
        rules.user_id
),
invoice_commission_lines AS (
    (
        SELECT invoice_commission_lines_team.id * 10 + 1 as id,
               invoice_commission_lines_team.user_id,
               invoice_commission_lines_team.team_id,
               invoice_commission_lines_team.plan_id,
               invoice_commission_lines_team.achieved,
               invoice_commission_lines_team.currency_id,
               invoice_commission_lines_team.date,
               invoice_commission_lines_team.plan_company_id,
               invoice_commission_lines_team.achievement_company_id,
               invoice_commission_lines_team.related_res_id,
               invoice_commission_lines_team.partner_id,
               'account.move' AS related_res_model
          FROM invoice_commission_lines_team
    )
    UNION ALL
    (
        SELECT invoice_commission_lines_user.id * 10 + 2 as id,
               invoice_commission_lines_user.user_id,
               invoice_commission_lines_user.team_id,
               invoice_commission_lines_user.plan_id,
               invoice_commission_lines_user.achieved,
               invoice_commission_lines_user.currency_id,
               invoice_commission_lines_user.date,
               invoice_commission_lines_user.plan_company_id,
               invoice_commission_lines_user.achievement_company_id,
               invoice_commission_lines_user.related_res_id,
               invoice_commission_lines_user.partner_id,
               'account.move' AS related_res_model
          FROM invoice_commission_lines_user
    )
)""", "invoice_commission_lines"
