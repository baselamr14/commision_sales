from odoo import api, models


class SaleCommissionReport(models.Model):
    _inherit = "sale.commission.report"

    @api.model
    def _query(self):
        users = self.env.context.get('commission_user_ids', [])
        if users:
            users = self.env['res.users'].browse(users).exists()
        teams = self.env.context.get('commission_team_ids', [])
        if teams:
            teams = self.env['crm.team'].browse(teams).exists()

        achievement_view = self.env['sale.commission.achievement.report']._get_report_view()
        if not self.env['sale.commission.achievement.report']._is_materialized_view() and achievement_view:
            self.env.cr.execute(achievement_view)

        res = f"""
WITH {self.env['sale.commission.achievement.report']._get_currency_rate()},
commission_lines AS (
    SELECT ca.id,
           ca.target_id,
           ca.user_id,
           ca.team_id,
           ca.achieved * cr.rate AS achieved,
           ca.currency_id,
           ca.plan_company_id,
           ca.achievement_company_id,
           ca.plan_id,
           ca.related_res_model,
           ca.related_res_id,
           ca.date,
           ca.partner_id
      FROM sale_commission_achievement_report_view ca
 LEFT JOIN currency_rate cr
        ON cr.company_id = ca.achievement_company_id
 LEFT JOIN account_move am
        ON ca.related_res_model = 'account.move'
       AND am.id = ca.related_res_id
 LEFT JOIN sale_commission_plan_achievement scpa
        ON scpa.plan_id = ca.plan_id
     WHERE (
            ca.related_res_model != 'account.move'
            OR scpa.type != 'margin_paid'
            OR am.payment_state = 'paid'
     )
), achievement AS (
    SELECT
        (
            COALESCE(era.plan_id, 0) * 10^11 +
            COALESCE(u.user_id, 0) +
            10^5 * COALESCE(to_char(era.date_from, 'YYMMDD')::integer, 0)
        )::bigint AS id,
        era.id AS target_id,
        era.plan_id AS plan_id,
        u.user_id AS user_id,
        MAX(scp.company_id) AS company_id,
        SUM(achieved) AS achieved,
        CASE
            WHEN MAX(era.amount) > 0 THEN GREATEST(SUM(achieved), 0) / (MAX(era.amount) * cr.rate)
            ELSE 0
        END AS achieved_rate,
        MAX(era.amount) AS amount,
        MAX(era.payment_date) AS payment_date,
        MAX(scpf.id) AS forecast_id,
        MAX(scpf.amount) AS forecast,
        MAX(scpf.notes) AS notes
        FROM sale_commission_plan_target era
        LEFT JOIN sale_commission_plan_user u
               ON u.plan_id=era.plan_id
              AND COALESCE(u.date_from, era.date_from)<era.date_to
              AND COALESCE(u.date_to, era.date_to)>era.date_from
        LEFT JOIN commission_lines cl
               ON cl.plan_id = era.plan_id
              AND cl.date::date >= era.date_from
              AND cl.date::date <= era.date_to
              AND cl.user_id = u.user_id
    LEFT JOIN sale_commission_plan_target_forecast scpf
           ON (scpf.target_id = era.id AND u.user_id = scpf.user_id)
    LEFT JOIN sale_commission_plan scp ON scp.id = u.plan_id
    LEFT JOIN currency_rate cr ON cr.company_id = scp.company_id
   WHERE scp.active
     AND scp.state = 'approved'
    GROUP BY
        era.id,
        era.plan_id,
        u.user_id,
        scp.company_id,
        cr.rate
), target_com AS (
    SELECT
        amount * cr.rate AS before,
        target_rate AS rate_low,
        LEAD(amount) OVER (PARTITION BY plan_id ORDER BY target_rate) * cr.rate AS amount,
        LEAD(target_rate) OVER (PARTITION BY plan_id ORDER BY target_rate) AS rate_high,
        plan_id
    FROM sale_commission_plan_target_commission scpta
    JOIN sale_commission_plan scp ON scp.id = scpta.plan_id
    LEFT JOIN currency_rate cr ON cr.company_id = scp.company_id
    WHERE scp.type = 'target'
), achievement_target AS (
    SELECT
        min(a.id) as id,
        min(a.target_id) as target_id,
        a.plan_id,
        a.user_id,
        a.company_id,
        {self.env.company.currency_id.id} AS currency_id,
        MIN(a.forecast_id) as forecast_id,
        MIN(a.payment_date) as payment_date,
        SUM(a.achieved) AS achieved,
        CASE WHEN SUM(a.amount) > 0 THEN SUM(a.achieved) / (SUM(a.amount) * cr.rate) ELSE 0.0 END AS achieved_rate,
        SUM(a.amount) * cr.rate AS target_amount,
        SUM(a.forecast) * cr.rate AS forecast,
        MAX(a.notes) AS notes,
        COUNT(1) AS ct
    FROM achievement a
    LEFT JOIN currency_rate cr ON cr.company_id = a.company_id
    GROUP BY
        a.plan_id, a.user_id, a.company_id, cr.rate, a.payment_date
)
SELECT
    a.*,
    CASE
        WHEN tc.before IS NULL THEN a.achieved
        WHEN tc.rate_high IS NULL THEN tc.before * a.ct
        ELSE (tc.before + (tc.amount - tc.before) * (a.achieved_rate - tc.rate_low) / (tc.rate_high - tc.rate_low)) * a.ct
    END AS commission
 FROM achievement_target a
    LEFT JOIN target_com tc ON (
        tc.plan_id = a.plan_id AND
        tc.rate_low <= a.achieved_rate AND
        (tc.rate_high IS NULL OR tc.rate_high > a.achieved_rate)
    )
"""
        return res
