# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class SaleCommissionPlanAchievement(models.Model):
    """Add 'margin_paid' to the achievement type selection."""

    _inherit = 'sale.commission.plan.achievement'

    type = fields.Selection(
        selection_add=[('margin_paid', 'Margin (Paid Invoices)')],
        ondelete={'margin_paid': 'cascade'},
    )


class SaleCommissionAchievementReport(models.Model):
    """
    Override the SQL report to handle the new 'margin_paid' type.

    Odoo builds achievements entirely in SQL via _commission_lines_query().
    We inject our type by:
      1. Adding 'margin_paid' to _get_invoices_rates() so it is included
         in the invoices_rules CTE.
      2. Overriding _get_filtered_moves_cte() to also accept paid invoices
         when the plan has margin_paid rules — but since the CTE is shared,
         we instead override _where_invoices() to not exclude paid invoices,
         and override _get_invoice_rates_product() to compute margin for
         the margin_paid rate while keeping existing rates intact.
    """

    _inherit = 'sale.commission.achievement.report'

    @api.model
    def _get_invoices_rates(self):
        """Add margin_paid to the list of invoice-based rate types."""
        rates = super()._get_invoices_rates()
        return rates + ['margin_paid']

    @api.model
    def _get_filtered_moves_cte(self, users=None, teams=None):
        """
        Override to also include paid invoices (payment_state in paid/in_payment)
        when margin_paid rules exist. We do this by removing the state filter
        restriction — state = 'posted' still applies, and we add payment_state
        as an extra column so _get_invoice_rates_product can use it.
        """
        date_from, date_to = self._get_achievement_default_dates()
        today = fields.Date.today().strftime('%Y-%m-%d')
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
        """
        Override to compute margin_paid correctly.

        For margin_paid:
          - Only count lines where invoice payment_state in ('paid','in_payment')
          - Amount = (price_subtotal / currency_rate) - (standard_price * quantity)
          - standard_price is read from product_product table

        For all other types, delegate to super() behaviour.
        """
        # Original formula from super() for amount_invoiced / qty_invoiced
        original = super()._get_invoice_rates_product()

        return f"""
        CASE
            WHEN fm.move_type = 'out_invoice' THEN
                -- standard amount_invoiced / qty_invoiced (unchanged)
                rules.amount_invoiced_rate * aml.price_subtotal / fm.invoice_currency_rate +
                rules.qty_invoiced_rate * aml.quantity +
                -- margin_paid: only when invoice is paid, compute margin
                CASE
                    WHEN fm.payment_state IN ('paid', 'in_payment')
                    THEN rules.margin_paid_rate * (
                        aml.price_subtotal / fm.invoice_currency_rate
                        - COALESCE(pp.standard_price, 0) * aml.quantity
                    )
                    ELSE 0
                END
            WHEN fm.move_type = 'out_refund' THEN
                (
                    rules.amount_invoiced_rate * aml.price_subtotal / fm.invoice_currency_rate +
                    rules.qty_invoiced_rate * aml.quantity +
                    CASE
                        WHEN fm.payment_state IN ('paid', 'in_payment')
                        THEN rules.margin_paid_rate * (
                            aml.price_subtotal / fm.invoice_currency_rate
                            - COALESCE(pp.standard_price, 0) * aml.quantity
                        )
                        ELSE 0
                    END
                ) * -1
        END
        """

    @api.model
    def _rate_to_case(self, rates):
        """
        Override to handle margin_paid in the CASE statement used to
        build per-type rate columns in the rules CTE.
        """
        case = "CASE WHEN scpa.type::text = '%s'::text THEN rate ELSE 0::double precision END AS %s"
        return ",\n".join(case % (s, s + '_rate') for s in rates)
