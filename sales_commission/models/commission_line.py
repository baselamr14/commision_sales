# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CommissionLine(models.Model):
    _name = 'commission.line'
    _description = 'Commission Line'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    rule_id = fields.Many2one(
        comodel_name='commission.rule',
        string='Commission Rule',
        required=True,
        ondelete='restrict',
    )
    salesperson_id = fields.Many2one(
        comodel_name='res.users',
        string='Salesperson',
        required=True,
        readonly=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    invoice_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        related='invoice_id.partner_id',
        store=True,
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        related='invoice_id.invoice_date',
        store=True,
    )
    date = fields.Date(
        string='Commission Date',
        required=True,
        default=fields.Date.today,
    )
    commission_type = fields.Selection(
        related='rule_id.commission_type',
        string='Commission Type',
        store=True,
    )
    base_amount = fields.Monetary(
        string='Base Amount',
        currency_field='currency_id',
        readonly=True,
        help='The amount used as base for commission calculation.',
    )
    commission_amount = fields.Monetary(
        string='Commission Amount',
        currency_field='currency_id',
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('invoiced', 'Invoiced'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        copy=False,
    )
    commission_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Commission Invoice',
        readonly=True,
        copy=False,
        help='The vendor bill created to pay this commission.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    note = fields.Text(string='Notes')

    _sql_constraints = [
        (
            'unique_invoice_rule',
            'unique(invoice_id, rule_id)',
            'A commission line already exists for this invoice and rule.'
        )
    ]
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('commission.line') or 'New'
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft commission lines can be confirmed.'))
            rec.state = 'confirmed'

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('confirmed',):
                raise UserError(_('Only confirmed commissions can be reset to draft.'))
            rec.state = 'draft'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'invoiced':
                raise UserError(_('Cannot cancel an already invoiced commission.'))
            rec.state = 'cancelled'

    def action_create_invoice(self):
        """Open the wizard to create a commission vendor bill."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Commission Invoice'),
            'res_model': 'commission.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_salesperson_id': self[0].salesperson_id.id if self else False,
                'active_ids': self.ids,
            },
        }

    def action_view_commission_invoice(self):
        self.ensure_one()
        if not self.commission_invoice_id:
            raise UserError(_('No commission invoice created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.commission_invoice_id.id,
            'view_mode': 'form',
        }

    def action_print_report(self):
        return self.env.ref('sales_commission.action_report_commission_lines').report_action(self)
