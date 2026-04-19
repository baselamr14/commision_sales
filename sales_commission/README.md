# Sale Commission Module — Odoo 19 Enterprise

A full-featured sales commission module that calculates commissions automatically
when customer invoices are paid.

---

## Features

| Feature | Description |
|---|---|
| Auto-calculation on payment | Commission lines created when `account.move.payment_state` becomes `paid` or `in_payment` |
| Commission by payment | Flat percentage of total invoice amount |
| Commission by product | Rate applied only to matching invoice lines |
| Commission by category | Rate applied to products in matching categories |
| Commission by margin % | Triggers only when margin % >= threshold |
| Commission by margin amount | Rate on gross margin |
| Fixed amount | Fixed amount per invoice |
| Vendor bill creation | Wizard to group confirmed lines and create a vendor bill |
| Analysis view | List, Graph, Pivot views with filters by date range, type, salesperson |
| Print report | PDF report from any commission line selection |

---

## Installation

1. Copy the `sale_commission` folder to your Odoo `addons` directory.
2. Restart the Odoo server.
3. Go to **Settings → Apps → Update Apps List**.
4. Search for **Sales Commission** and click **Install**.

---

## Configuration

### 1. Create a Commission Rule

Go to **Sales → Commissions → Commission Rules → New**

| Field | Description |
|---|---|
| Salesperson | The internal user this rule belongs to |
| Commission Type | Select from 6 available types |
| Rate (%) | Percentage to apply (not used for Fixed type) |
| Fixed Amount | Used only for "Fixed Amount per Invoice" type |
| Products | Required when type = "By Product" |
| Product Categories | Required when type = "By Product Category" |
| Minimum Margin % | Threshold for margin-based types |
| Valid From / To | Optional date range for seasonal rules |

### 2. Commission Is Auto-Calculated

When a customer invoice is paid, the system:
- Looks up all active rules for the invoice's salesperson
- Checks date validity
- Runs the appropriate calculation
- Creates a `commission.line` in **Draft** state

### 3. Confirm Commission Lines

Go to **Sales → Commissions → Commission Lines**, select lines, and click **Confirm**
(or open each line and click the Confirm button).

### 4. Create Vendor Bill

Go to **Sales → Commissions → Create Commission Invoice**:
- Select the salesperson
- Choose date range
- Choose the service product and journal
- Click **Create Vendor Bill**

This groups all confirmed lines in the range into a single vendor bill and marks
the commission lines as **Invoiced**.

### 5. Analyze Commissions

Go to **Sales → Commissions → Commission Analysis** for graph, pivot, and list views.
Filter by date range, commission type, salesperson, or status.

---

## Commission Types Reference

### Percentage of Payment
```
commission = invoice.amount_total × (rate / 100)
```

### By Product
```
commission = sum(line.price_subtotal × rate/100
                 for line in invoice_lines
                 if line.product in rule.products)
```

### By Product Category
```
commission = sum(line.price_subtotal × rate/100
                 for line in invoice_lines
                 if line.product.category in rule.categories)
```

### Margin Percentage
```
margin = invoice.amount_untaxed - sum(product.standard_price × qty)
margin_pct = margin / invoice.amount_untaxed × 100
if margin_pct >= min_margin_pct:
    commission = margin × (rate / 100)
```

### Margin Amount
```
margin = invoice.amount_untaxed - sum(product.standard_price × qty)
if margin > 0:
    commission = margin × (rate / 100)
```

### Fixed Amount
```
commission = rule.fixed_amount
```

---

## Module Structure

```
sale_commission/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── commission_rule.py      # Core rule model with calculation logic
│   ├── commission_line.py      # Per-invoice commission record
│   ├── account_move.py         # Inherit: trigger on payment_state change
│   ├── sale_order.py           # Inherit: optional rule override on order
│   └── res_partner.py          # Inherit: link partner to rules
├── wizard/
│   ├── __init__.py
│   ├── commission_invoice_wizard.py       # Python logic
│   └── commission_invoice_wizard_views.xml
├── report/
│   ├── __init__.py
│   ├── commission_report.py               # SQL view for analysis
│   └── commission_report_template.xml     # QWeb PDF templates
├── views/
│   ├── commission_rule_views.xml
│   ├── commission_line_views.xml
│   ├── commission_analysis_views.xml
│   └── menus.xml
├── security/
│   └── ir.model.access.csv
├── data/
│   └── commission_data.xml                # Sequence + default product
└── README.md
```

---

## Access Rights

| Group | Rules | Lines | Analysis | Wizard |
|---|---|---|---|---|
| Sales / User | Read only | Read + Write own | Read | — |
| Sales / Manager | Full | Full | Full | Full |

---

## Notes for Developers

- **Duplicate prevention**: `UNIQUE(invoice_id, rule_id)` SQL constraint prevents double commission.
- **Multi-company**: `company_id` on both `commission.rule` and `commission.line`.
- **Multi-currency**: `currency_id` stored on each line from the source invoice.
- **Sequence**: Commission lines use the `commission.line` ir.sequence (`COM/YEAR/00001`).
- **Extending**: Override `_calculate_commission()` in `commission.rule` to add custom logic.
- **Triggering manually**: Call `move._compute_and_create_commissions()` on any `account.move` recordset.
