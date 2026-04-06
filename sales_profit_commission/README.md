# Sales Profit Commission for Odoo 19

## What this module does
This module adds profit-based commission fields to sale order lines.

### Formula
- Profit = `price_subtotal - (purchase_cost × quantity)`
- Commission = `max(profit, 0) × commission_percent / 100`

### Added fields on sale order line
- **Cost Price** (`purchase_cost`)
- **Commission %** (`commission_percent`)
- **Profit** (`profit_amount`)
- **Commission Amount** (`commission_amount`)

### Added field on sale order
- **Total Commission** (`total_commission`)

## Installation
1. Copy the module folder `sales_profit_commission` into your custom addons path.
2. Restart Odoo.
3. Upgrade Apps list.
4. Search for **Sales Profit Commission**.
5. Install the module.

## Notes
- The line cost is automatically filled from the product cost (`standard_price`) when a product is selected.
- The commission percentage is editable on every sales order line.
- Commission is calculated on **untaxed** profit using `price_subtotal`.
- Negative profit does not generate negative commission.

## Example
- Cost Price = 150
- Sale Price = 200
- Quantity = 1
- Commission % = 10
- Profit = 50
- Commission = 5

## Future improvements you can add later
- Default commission percentage per salesperson
- Lock fields after order confirmation
- Generate commission entries for payroll/accounting
- Add commission reporting by salesperson
