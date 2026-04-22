import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleCommissionPlanAchievement(models.Model):
    """
    Adds achievement type 'margin_paid':
    commission = (price_subtotal - cost) * rate
    for invoices where payment_state in ('paid', 'in_payment').
    """

    _inherit = 'sale.commission.plan.achievement'

    type = fields.Selection(
        selection_add=[('margin_paid', 'Margin (Paid Invoices)')],
        ondelete={'margin_paid': 'cascade'},
    )

    def _compute_margin_paid(self, user, date_from, date_to):
        """Core logic: sum margin on paid invoices for this achievement line."""
        self.ensure_one()
        domain = [
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('move_id.state', '=', 'posted'),
            ('move_id.payment_state', 'in', ('paid', 'in_payment')),
            ('move_id.invoice_user_id', '=', user.id),
            ('move_id.invoice_date', '>=', date_from),
            ('move_id.invoice_date', '<=', date_to),
            ('display_type', '=', False),
            ('product_id', '!=', False),
        ]
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        elif self.product_category_id:
            domain.append(
                ('product_id.categ_id', 'child_of', self.product_category_id.id)
            )

        lines = self.env['account.move.line'].search(domain)
        _logger.info(
            '[margin_paid] user=%s from=%s to=%s invoice_lines_found=%s',
            user.name, date_from, date_to, len(lines),
        )

        if not lines:
            return 0.0

        company_currency = self.env.company.currency_id
        total = 0.0
        for line in lines:
            subtotal = line.move_id.currency_id._convert(
                line.price_subtotal,
                company_currency,
                self.env.company,
                line.move_id.invoice_date or fields.Date.today(),
            )
            cost = line.product_id.standard_price * line.quantity
            total += subtotal - cost

        _logger.info('[margin_paid] raw_margin=%s', total)
        return total

    def _get_achieved_amount(self, user, date_from, date_to):
        """Hook A - Odoo 19 method name."""
        self.ensure_one()
        if self.type != 'margin_paid':
            return super()._get_achieved_amount(user, date_from, date_to)
        return self._compute_margin_paid(user, date_from, date_to)

    def _get_achievement(self, user, date_from, date_to):
        """Hook B - alternative method name in some builds."""
        self.ensure_one()
        if self.type != 'margin_paid':
            return super()._get_achievement(user, date_from, date_to)
        return self._compute_margin_paid(user, date_from, date_to)


class SaleCommissionPlan(models.Model):
    """
    Safety net: override the plan-level achievement aggregator so that
    even if Odoo's dispatcher does not call our hooks,
    'margin_paid' lines are still handled.
    """

    _inherit = 'sale.commission.plan'

    def _get_achievements_by_user(self, user, date_from, date_to):
        custom_lines = self.achievement_ids.filtered(
            lambda a: a.type == 'margin_paid'
        )
        if not custom_lines:
            return super()._get_achievements_by_user(user, date_from, date_to)

        standard_lines = self.achievement_ids - custom_lines

        result = 0.0
        if standard_lines:
            self_copy = self.with_context()
            self_copy.achievement_ids = standard_lines
            result = super(SaleCommissionPlan, self_copy)._get_achievements_by_user(
                user, date_from, date_to
            )

        for line in custom_lines:
            margin = line._compute_margin_paid(user, date_from, date_to)
            commission = margin * line.rate
            _logger.info(
                '[margin_paid] plan=%s rate=%s margin=%s commission=%s',
                self.name, line.rate, margin, commission,
            )
            result += commission

        return result
