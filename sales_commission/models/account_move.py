# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    commission_line_ids = fields.One2many(
        comodel_name='commission.line',
        inverse_name='invoice_id',
        string='Commission Lines',
        copy=False,
    )
    commission_count = fields.Integer(
        string='Commissions',
        compute='_compute_commission_count',
    )

    @api.depends('commission_line_ids')
    def _compute_commission_count(self):
        for move in self:
            move.commission_count = len(move.commission_line_ids)

    def _get_commission_rules_for_salesperson(self, salesperson, date):
        rules = self.env['commission.rule'].search([
            ('salesperson_id', '=', salesperson.id),
            ('active', '=', True),
        ])
        return rules.filtered(lambda r: r._is_valid_on_date(date))

    def _compute_and_create_commissions(self):
        CommissionLine = self.env['commission.line']
        _logger.info('COMMISSION >>> _compute_and_create_commissions on %s moves', len(self))
        for move in self:
            _logger.info('COMMISSION >>> move=%s type=%s payment_state=%s',
                         move.name, move.move_type, move.payment_state)
            if move.move_type != 'out_invoice':
                continue
            if move.payment_state != 'paid':
                    _logger.info('COMMISSION >>> skipped - payment_state=%s', move.payment_state)
                    continue

            salesperson = move.invoice_user_id
            if not salesperson:
                _logger.warning('COMMISSION >>> no salesperson on %s', move.name)
                continue
            date = move.invoice_date or fields.Date.today()
            rules = self._get_commission_rules_for_salesperson(salesperson, date)
            _logger.info('COMMISSION >>> rules for %s: %s', salesperson.name, rules.mapped('name'))
            if not rules:
                all_rules = self.env['commission.rule'].search([])
                _logger.warning('COMMISSION >>> no rules found. All rules in DB: %s',
                    [(r.name, r.salesperson_id.name, r.active) for r in all_rules])
                continue
            for rule in rules:
                if CommissionLine.search([('invoice_id','=',move.id),('rule_id','=',rule.id)], limit=1):
                    _logger.info('COMMISSION >>> already exists for rule %s', rule.name)
                    continue
                amount = rule._calculate_commission(move)
                _logger.info('COMMISSION >>> amount for rule %s = %s', rule.name, amount)
                if amount <= 0:
                    continue
                try:
                    line = CommissionLine.create({
                        'rule_id': rule.id,
                        'salesperson_id': salesperson.id,
                        'invoice_id': move.id,
                        'base_amount': move.amount_total,
                        'commission_amount': amount,
                        'date': date,
                        'currency_id': move.currency_id.id,
                        'state': 'draft',
                    })
                    _logger.info('COMMISSION >>> CREATED id=%s invoice=%s amount=%s',
                                 line.id, move.name, amount)
                except Exception as e:
                    _logger.error('COMMISSION >>> FAILED to create: %s', str(e))

    def action_view_commissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Commissions'),
            'res_model': 'commission.line',
            'view_mode': 'list,form',
            'domain': [('invoice_id', '=', self.id)],
            'context': {'default_invoice_id': self.id},
        }


class AccountMoveLine(models.Model):
    """
    Hook into reconciliation at the move line level.
    In Odoo 19, full_reconcile_id is set on move lines when payment
    is fully reconciled with an invoice. This is the lowest-level
    hook that fires regardless of which payment path is used.
    """
    _inherit = 'account.move.line'

    # def reconcile(self):
    #     _logger.info('COMMISSION >>> AccountMoveLine.reconcile called, lines: %s', self.ids)
    #     res = super().reconcile()
    #     # After reconciliation, check if any customer invoices are now paid
    #     invoice_moves = self.mapped('move_id').filtered(
    #         lambda m: m.move_type == 'out_invoice'
    #     )
    #     _logger.info('COMMISSION >>> invoice moves after reconcile: %s',
    #                  [(m.name, m.payment_state) for m in invoice_moves])
    #     if invoice_moves:
    #         invoice_moves.invalidate_recordset(['payment_state'])
    #         invoice_moves._compute_and_create_commissions()
    #     return res

    def reconcile(self):
        _logger.info('COMMISSION >>> AccountMoveLine.reconcile called, lines: %s', self.ids)
        res = super().reconcile()

        invoice_moves = self.mapped('move_id').exists().filtered(
            lambda m: m.move_type == 'out_invoice'
        )

        _logger.info(
            'COMMISSION >>> invoice moves after reconcile: %s',
            [(m.id, m.name, m.payment_state) for m in invoice_moves]
        )

        if invoice_moves:
            invoice_moves.invalidate_recordset(['payment_state'])
            invoice_moves = invoice_moves.exists()
            if invoice_moves:
                invoice_moves._compute_and_create_commissions()

        return res


class AccountPaymentRegister(models.TransientModel):
    """
    Direct hook on the payment register wizard as a belt-and-suspenders
    fallback in case the move line reconcile hook misses anything.
    """
    _inherit = 'account.payment.register'

    # def action_create_payments(self):
    #     _logger.info('COMMISSION >>> action_create_payments called, active_ids=%s',
    #                  self._context.get('active_ids'))
    #     # Get invoice moves BEFORE payment creation
    #     invoice_ids = self._context.get('active_ids', [])
    #     res = super().action_create_payments()
    #     # Re-fetch invoices and trigger commission
    #     if invoice_ids:
    #         moves = self.env['account.move'].browse(invoice_ids)
    #         moves.invalidate_recordset(['payment_state'])
    #         _logger.info('COMMISSION >>> post payment, payment_states: %s',
    #                      [(m.name, m.payment_state) for m in moves])
    #         moves._compute_and_create_commissions()
    #     return res
    def action_create_payments(self):
        _logger.info(
            'COMMISSION >>> action_create_payments called, active_ids=%s',
            self._context.get('active_ids')
        )

        invoice_ids = self._context.get('active_ids', [])
        res = super().action_create_payments()

        try:
            if invoice_ids:
                moves = self.env['account.move'].browse(invoice_ids).exists()
                if moves:
                    moves.invalidate_recordset(['payment_state'])
                    paid_moves = moves.filtered(
                        lambda m: m.move_type == 'out_invoice' and m.payment_state == 'paid'
                    )
                    _logger.info(
                        'COMMISSION >>> post payment, paid invoice states: %s',
                        [(m.id, m.name, m.payment_state) for m in paid_moves]
                    )
                    if paid_moves:
                        paid_moves._compute_and_create_commissions()
        except Exception:
            _logger.exception('COMMISSION >>> post-payment commission hook failed')

        return res
