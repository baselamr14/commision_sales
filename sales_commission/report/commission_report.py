# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class CommissionReport(models.Model):
    _name = 'commission.report'
    _description = 'Commission Analysis Report'
    _auto = False
    _rec_name = 'salesperson_id'
    _order = 'date desc'

    salesperson_id = fields.Many2one(
        comodel_name='res.users',
        string='Salesperson',
        readonly=True,
    )
    salesperson_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Salesperson (Partner)',
        readonly=True,
    )
    rule_id = fields.Many2one(
        comodel_name='commission.rule',
        string='Commission Rule',
        readonly=True,
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
        readonly=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        readonly=True,
    )
    invoice_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        readonly=True,
    )
    date = fields.Date(
        string='Commission Date',
        readonly=True,
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        readonly=True,
    )
    base_amount = fields.Float(
        string='Base Amount',
        readonly=True,
    )
    commission_amount = fields.Float(
        string='Commission Amount',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('invoiced', 'Invoiced'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        readonly=True,
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW commission_report AS (
                SELECT
                    cl.id                           AS id,
                    cl.salesperson_id               AS salesperson_id,
                    rp.id                           AS salesperson_partner_id,
                    cl.rule_id                      AS rule_id,
                    cr.commission_type              AS commission_type,
                    cl.invoice_id                   AS invoice_id,
                    am.partner_id                   AS invoice_partner_id,
                    cl.date                         AS date,
                    am.invoice_date                 AS invoice_date,
                    cl.base_amount                  AS base_amount,
                    cl.commission_amount            AS commission_amount,
                    cl.state                        AS state,
                    cl.company_id                   AS company_id,
                    cl.currency_id                  AS currency_id
                FROM commission_line cl
                JOIN commission_rule cr  ON cr.id = cl.rule_id
                JOIN account_move am     ON am.id = cl.invoice_id
                JOIN res_users ru        ON ru.id = cl.salesperson_id
                JOIN res_partner rp      ON rp.id = ru.partner_id
            )
        """)
