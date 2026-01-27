# Salaries App Design

## Overview

A standalone app for tracking employee salary payments, accessible under a new "Finances" category in the sidebar. Employees are existing User accounts in the system.

## Core Concepts

- **Base salary**: Default monthly amount for an employee (can be changed anytime)
- **Salary month**: Created only when recording payments (inherits base salary as expected amount, can be overridden)
- **Payments**: Multiple payments per month allowed (partial payments, advances, etc.)
- **Bonus**: Any overpayment is automatically marked as bonus (informational only, no carryover)

## Data Model

### EmployeeSalary
Links a User to their salary configuration.

| Field | Type | Description |
|-------|------|-------------|
| user | FK → User | The employee (unique) |
| base_salary | Decimal(10,2) | Default monthly salary |
| currency | CharField | USD, EUR, GBP |
| created_at | DateTime | Auto |
| updated_at | DateTime | Auto |

### SalaryMonth
A specific month's salary record for an employee.

| Field | Type | Description |
|-------|------|-------------|
| employee_salary | FK → EmployeeSalary | Parent record |
| year | Integer | e.g., 2025 |
| month | Integer | 1-12 |
| expected_amount | Decimal(10,2) | Defaults to base_salary, can override |
| created_at | DateTime | Auto |

**Computed properties:**
- `total_paid`: Sum of all payments
- `remaining`: expected_amount - total_paid (min 0)
- `bonus_amount`: total_paid - expected_amount (if positive)
- `status`: Unpaid / Partial / Paid / Bonus

**Constraints:**
- Unique together: (employee_salary, year, month)

### Payment
Individual payment transaction.

| Field | Type | Description |
|-------|------|-------------|
| salary_month | FK → SalaryMonth | Parent month |
| amount | Decimal(10,2) | Payment amount |
| payment_date | Date | When paid |
| payment_method | CharField | Cash, Bank Transfer, Check, Other |
| notes | TextField | Optional reference/notes |
| created_at | DateTime | Auto |

## Status Logic

| Status | Condition |
|--------|-----------|
| Unpaid | total_paid = 0 |
| Partial | 0 < total_paid < expected_amount |
| Paid | total_paid = expected_amount |
| Bonus | total_paid > expected_amount |

## User Interface

### Sidebar
- New "Finances" category below "My Tasks"
- Contains "Salaries" link with wallet/banknote icon
- Accessible to all logged-in users (no role restriction for now)

### Salaries List Page (`/salaries/`)
- Table of all employees with salary configurations
- Columns: Employee name, Base salary, Current month status
- Click row → Employee detail page
- "Add Employee" button for users without salary config

### Employee Salary Detail (`/salaries/<id>/`)
- Header: Employee name, base salary (inline editable), currency
- Month list (most recent first):
  - Month/Year (e.g., "January 2025")
  - Expected amount
  - Status badge (color-coded)
  - Transaction count (e.g., "2 payments")
  - Expandable to show payment details
- Current month highlighted
- "Add Month" and "Record Payment" buttons

### Record Payment Drawer
- Month selector (existing months or create new)
- Amount input
- Payment date (DD/MM/YYYY format)
- Payment method dropdown
- Notes textarea
- Submit creates payment and updates month status

### Add Month Drawer
- Year/Month selector
- Expected amount (pre-filled with base salary)
- Submit creates month entry

## URLs

| URL | View | Description |
|-----|------|-------------|
| `/salaries/` | salary_list | List all employee salaries |
| `/salaries/create/` | salary_create | Add salary config for user |
| `/salaries/<id>/` | salary_detail | Employee salary detail |
| `/salaries/<id>/update/` | salary_update | Update base salary (HTMX) |
| `/salaries/<id>/months/create/` | month_create | Add month (HTMX drawer) |
| `/salaries/<id>/payments/create/` | payment_create | Record payment (HTMX drawer) |
| `/salaries/payments/<id>/delete/` | payment_delete | Delete a payment (HTMX) |

## Technical Details

### Django App Structure
```
apps/salaries/
├── __init__.py
├── admin.py
├── apps.py
├── forms.py
├── models.py
├── services.py
├── urls.py
├── views.py
├── migrations/
└── tests/
    ├── __init__.py
    ├── test_models.py
    └── test_views.py
```

### Templates
```
templates/salaries/
├── salary_list.html
├── salary_detail.html
└── partials/
    ├── salary_row.html
    ├── month_item.html
    ├── payment_item.html
    ├── create_salary_drawer.html
    ├── create_month_drawer.html
    ├── create_payment_drawer.html
    └── base_salary_edit.html
```

### Frontend Stack
- HTMX for drawer interactions and inline edits
- Alpine.js for expandable month/payment lists
- Tailwind CSS (existing dark theme)
- Lucide icons

### Date Format
- Display: DD/MM/YYYY (European format)
- Django template filter: `{{ date|date:"d/m/Y" }}`
- Input: Native HTML5 date picker

### Currency Options
- USD ($)
- EUR (€)
- GBP (£)

## Access Control

Currently open to all authenticated users. Future enhancement could restrict to admin-only.

## Out of Scope (Future)

- Payment carryover/advances
- Salary history (tracking base salary changes over time)
- Reports/exports
- Multi-currency conversion
- Tax calculations
