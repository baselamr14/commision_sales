from odoo import api, fields, models


class SaleCommissionPlanAchievement(models.Model):
    """
    Extends the commission plan achievement model to add a new type:
    'margin_paid' — commission is calculated on the profit margin
    (price_subtotal - cost) of invoice lines whose invoice is fully PAID,
    i.e. account.move.payment_state in ('paid', 'in_payment').

    The existing 'margin' type in Odoo uses posted invoices only.
    This new type filters further to only count paid invoices.
    """

    _inherit = 'sale.commission.plan.achievement'

    # -----------------------------------------------------------------
    # Override the 'type' selection field to inject the new option.
    # We use selection_add so all existing options remain intact.
    # -----------------------------------------------------------------
    type = fields.Selection(
        selection_add=[('margin_paid', 'Margin (Paid Invoices)')],
        ondelete={'margin_paid': 'cascade'},
    )

    # -----------------------------------------------------------------
    # Override the method that Odoo core uses to compute the achieved
    # amount for a given user/period.  The method signature follows
    # the pattern used in sale_commission/models/sale_commission_plan.py
    #
    # Odoo core iterates over achievement lines and calls:
    #     achievement._get_achieved_amount(user, date_from, date_to)
    # for each line, then sums the results.
    #
    # We call super() for every type we did NOT add, so we never break
    # any existing logic.
    # -----------------------------------------------------------------
    def _get_achieved_amount(self, user, date_from, date_to):
        """
        Return the total achieved amount for *this* achievement line,
        for the given user and date range.

        For type == 'margin_paid':
            Sum of (price_subtotal - (quantity * cost_price)) across all
            invoice lines where:
              - move_type in ('out_invoice', 'out_refund')
              - move.state == 'posted'                    (confirmed)
              - move.payment_state in ('paid','in_payment') (actually paid)
              - move.invoice_user_id == user              (salesperson)
              - move.invoice_date between date_from and date_to
              - product matches self.product_id / self.product_category_id
                (if set — otherwise all products)

        For all other types, delegate to the parent implementation.
        """
        self.ensure_one()

        if self.type != 'margin_paid':
            return super()._get_achieved_amount(user, date_from, date_to)

        # ------------------------------------------------------------------
        # Build domain for account.move.line
        # ------------------------------------------------------------------
        domain = [
            # Only customer invoices and credit notes
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            # Invoice must be posted (confirmed)
            ('move_id.state', '=', 'posted'),
            # Invoice must be paid (fully or in process of payment)
            ('move_id.payment_state', 'in', ('paid', 'in_payment')),
            # Belongs to the salesperson
            ('move_id.invoice_user_id', '=', user.id),
            # Within the commission period
            ('move_id.invoice_date', '>=', date_from),
            ('move_id.invoice_date', '<=', date_to),
            # Only product lines (exclude notes, sections, taxes, etc.)
            ('display_type', '=', False),
            ('product_id', '!=', False),
        ]

        # Optional: filter by a specific product
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        # Optional: filter by product category
        elif self.product_category_id:
            # We match against the product's internal category (categ_id)
            domain.append(
                ('product_id.categ_id', 'child_of', self.product_category_id.id)
            )

        invoice_lines = self.env['account.move.line'].search(domain)

        if not invoice_lines:
            return 0.0

        # ------------------------------------------------------------------
        # Margin = price_subtotal - (quantity * cost_price)
        # We read cost from product.product.standard_price at the time of
        # calculation (same approach Odoo core uses for the 'margin' type).
        #
        # For credit notes the quantity is negative, so the margin is
        # automatically subtracted — matching Odoo's standard behaviour.
        # ------------------------------------------------------------------
        total_margin = 0.0
        company_currency = self.env.company.currency_id

        for line in invoice_lines:
            # price_subtotal is already in the company currency when
            # the invoice currency equals the company currency.
            # For multi-currency invoices we convert explicitly.
            subtotal = line.move_id.currency_id._convert(
                line.price_subtotal,
                company_currency,
                self.env.company,
                line.move_id.invoice_date or fields.Date.today(),
            )

            # Cost = standard_price × qty (standard_price is in company currency)
            cost = line.product_id.standard_price * line.quantity

            margin = subtotal - cost
            total_margin += margin

        # Apply the commission rate defined on this achievement line.
        # The 'rate' field holds a factor, e.g. 0.05 = 5 %.
        # (Odoo core multiplies by rate inside the plan-level loop, but
        # to be consistent with how the existing 'margin' type works we
        # return the raw margin here and let the plan apply the rate.)
        return total_margin
