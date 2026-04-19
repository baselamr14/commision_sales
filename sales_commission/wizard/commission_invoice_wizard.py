# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CommissionInvoiceWizard(models.TransientModel):
    _name = 'commission.invoice.wizard'
    _description = 'Create Commission Invoice Wizard'

    salesperson_id = fields.Many2one(
        comodel_name='res.users',
        string='Salesperson',
        required=True,
        domain=[('share', '=', False)],
    )
    date_from = fields.Date(
        string='From Date',
        required=True,
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.today,
    )
    commission_line_ids = fields.Many2many(
        comodel_name='commission.line',
        string='Commission Lines',
        readonly=True,
    )
    total_commission = fields.Monetary(
        string='Total Commission',
        compute='_compute_total_commission',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Commission Product',
        required=True,
        domain=[('type', '=', 'service')],
        help='Service product used as the invoice line for commission vendor bill.',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Vendor Bills Journal',
        domain=[('type', '=', 'purchase')],
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'purchase'), ('company_id', '=', self.env.company.id)], limit=1
        ),
    )

    @api.depends('commission_line_ids', 'commission_line_ids.commission_amount')
    def _compute_total_commission(self):
        for rec in self:
            rec.total_commission = sum(rec.commission_line_ids.mapped('commission_amount'))

    @api.onchange('salesperson_id', 'date_from', 'date_to')
    def _onchange_filters(self):
        if self.salesperson_id and self.date_from and self.date_to:
            lines = self.env['commission.line'].search([
                ('salesperson_id', '=', self.salesperson_id.id),
                ('state', '=', 'confirmed'),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('commission_invoice_id', '=', False),
            ])
            self.commission_line_ids = [(6, 0, lines.ids)]
        else:
            self.commission_line_ids = [(5,)]

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_('From Date must be before To Date.'))

    def action_create_invoice(self):
        self.ensure_one()

        # Refresh lines
        lines = self.env['commission.line'].search([
            ('salesperson_id', '=', self.salesperson_id.id),
            ('state', '=', 'confirmed'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('commission_invoice_id', '=', False),
        ])

        if not lines:
            raise UserError(_(
                'No confirmed commission lines found for %s between %s and %s.',
                self.salesperson_id.name,
                self.date_from,
                self.date_to,
            ))

        total = sum(lines.mapped('commission_amount'))
        partner = self.salesperson_id.partner_id

        # Build invoice line description
        description_lines = []
        for line in lines:
            description_lines.append(
                f"  • {line.invoice_id.name} ({line.date}): "
                f"{line.env['res.currency'].browse(line.currency_id.id).symbol}"
                f"{line.commission_amount:.2f} [{line.rule_id.name}]"
            )
        description = _('Commission payment for %s\n%s to %s\n\n%s') % (
            self.salesperson_id.name,
            self.date_from,
            self.date_to,
            '\n'.join(description_lines),
        )

        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.today(),
            'journal_id': self.journal_id.id if self.journal_id else False,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'name': description,
                'quantity': 1,
                'price_unit': total,
            })],
            'narration': _(
                'Auto-generated commission invoice for %s (%s – %s)',
                self.salesperson_id.name, self.date_from, self.date_to
            ),
        }

        bill = self.env['account.move'].create(bill_vals)

        # Update commission lines
        lines.write({
            'state': 'invoiced',
            'commission_invoice_id': bill.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Commission Invoice'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }
