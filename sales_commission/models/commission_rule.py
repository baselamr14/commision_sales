# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CommissionRule(models.Model):
    _name = 'commission.rule'
    _description = 'Commission Rule'
    _order = 'sequence, id'

    name = fields.Char(
        string='Rule Name',
        required=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    salesperson_id = fields.Many2one(
        comodel_name='res.users',
        string='Salesperson',
        required=True,
        domain=[('share', '=', False)],
    )
    commission_type = fields.Selection(
        selection=[
            ('payment', 'Percentage of Payment'),
            ('product', 'By Product'),
            ('category', 'By Product Category'),
            ('margin_pct', 'Margin Percentage'),
            ('margin_amount', 'Margin Amount'),
            ('fixed', 'Fixed Amount per Invoice'),
        ],
        string='Commission Type',
        required=True,
        default='payment',
    )
    rate = fields.Float(
        string='Commission Rate (%)',
        digits=(5, 4),
        help='Commission percentage applied to the base amount.',
    )
    fixed_amount = fields.Monetary(
        string='Fixed Amount',
        currency_field='currency_id',
        help='Fixed commission amount per invoice (used when type is Fixed Amount).',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='commission_rule_product_rel',
        column1='rule_id',
        column2='product_id',
        string='Products',
        help='Commission applies only to these products.',
    )
    product_category_ids = fields.Many2many(
        comodel_name='product.category',
        relation='commission_rule_category_rel',
        column1='rule_id',
        column2='category_id',
        string='Product Categories',
        help='Commission applies only to products in these categories.',
    )
    min_margin_pct = fields.Float(
        string='Minimum Margin %',
        digits=(5, 2),
        help='Minimum margin percentage required to trigger this commission rule.',
    )
    apply_on = fields.Selection(
        selection=[
            ('all', 'All Invoices'),
            ('sale', 'Sale Orders Only'),
        ],
        string='Apply On',
        default='all',
    )
    date_from = fields.Date(
        string='Valid From',
    )
    date_to = fields.Date(
        string='Valid To',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    note = fields.Text(
        string='Notes',
    )
    commission_line_ids = fields.One2many(
        comodel_name='commission.line',
        inverse_name='rule_id',
        string='Commission Lines',
    )
    line_count = fields.Integer(
        string='Lines',
        compute='_compute_line_count',
    )

    @api.depends('commission_line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.commission_line_ids)

    @api.constrains('rate')
    def _check_rate(self):
        for rec in self:
            if rec.commission_type != 'fixed' and rec.rate < 0:
                raise ValidationError(_('Commission rate cannot be negative.'))
            if rec.commission_type in ('payment', 'product', 'category') and rec.rate > 100:
                raise ValidationError(_('Commission rate cannot exceed 100%.'))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('Valid From date must be before Valid To date.'))

    def _is_valid_on_date(self, date):
        """Check whether this rule is valid on a given date."""
        self.ensure_one()
        if self.date_from and date < self.date_from:
            return False
        if self.date_to and date > self.date_to:
            return False
        return True

    def _calculate_commission(self, invoice):
        """
        Calculate commission amount for the given invoice.
        Returns a float representing the commission amount.
        """
        self.ensure_one()
        amount = 0.0

        if self.commission_type == 'payment':
            # Percentage of total invoice amount paid
            amount = invoice.amount_total * (self.rate / 100.0)

        elif self.commission_type == 'product':
            # Commission per product line if product matches
            for line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')
            ):
                if line.product_id and line.product_id in self.product_ids:
                    amount += line.price_subtotal * (self.rate / 100.0)

        elif self.commission_type == 'category':
            # Commission per product line if product category matches
            for line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')
            ):
                if line.product_id and line.product_id.categ_id in self.product_category_ids:
                    amount += line.price_subtotal * (self.rate / 100.0)

        elif self.commission_type == 'margin_pct':
            # Commission based on margin percentage
            total_cost = sum(
                (line.product_id.standard_price * line.quantity)
                for line in invoice.invoice_line_ids.filtered(
                    lambda l: l.display_type not in ('line_section', 'line_note') and l.product_id
                )
            )
            total_revenue = invoice.amount_untaxed
            if total_revenue > 0:
                margin = total_revenue - total_cost
                margin_pct = (margin / total_revenue) * 100.0
                if margin_pct >= self.min_margin_pct:
                    amount = margin * (self.rate / 100.0)

        elif self.commission_type == 'margin_amount':
            # Commission on raw margin amount
            total_cost = sum(
                (line.product_id.standard_price * line.quantity)
                for line in invoice.invoice_line_ids.filtered(
                    lambda l: l.display_type not in ('line_section', 'line_note') and l.product_id
                )
            )
            margin = invoice.amount_untaxed - total_cost
            if margin > 0:
                amount = margin * (self.rate / 100.0)

        elif self.commission_type == 'fixed':
            amount = self.fixed_amount

        return amount

    def action_view_commission_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Commission Lines'),
            'res_model': 'commission.line',
            'view_mode': 'list,form',
            'domain': [('rule_id', '=', self.id)],
            'context': {'default_rule_id': self.id},
        }
