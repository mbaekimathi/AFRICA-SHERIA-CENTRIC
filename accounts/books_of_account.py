"""
Live books of account built from Finance & Billing money movements.

There is no formal double-entry journal table yet. Each book is assembled from
invoices, client credits, company ledger topups/payments, payroll, and advances.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum
from django.utils import timezone

from .models import (
    Client,
    CompanyAccountTopup,
    CompanyExpenseAccount,
    CompanyExpensePayment,
    EmployeeAdvance,
    Invoice,
    PayrollPayment,
    PayrollRun,
)

ZERO = Decimal("0.00")
ENTRY_LIMIT = 250

BOOK_LEADS = {
    "cash-book": (
        "Receipts and payments across company accounts that accept cash, "
        "including the Petty Cash Book."
    ),
    "bank-book": (
        "Bank and transfer movements on company accounts that hold bank details "
        "or accept bank transfer / cheque."
    ),
    "sales-day-book": (
        "Daily record of invoices raised for clients (sales / fees day book)."
    ),
    "purchases-day-book": (
        "Daily record of firm expense payments (purchases / expenses day book)."
    ),
    "journal-proper": (
        "Adjusting and transfer entries synthesised from inter-account topups, "
        "advance recoveries, and payroll statutory deductions."
    ),
    "sales-ledger": (
        "Accounts receivable by client — invoices, receipts, balances, and credit."
    ),
    "purchases-ledger": (
        "Expense and payroll outflows grouped by expense type (creditor categories)."
    ),
    "general-ledger": (
        "Control and cash accounts with live balances from company ledgers, "
        "client AR, advances, and unpaid payroll."
    ),
    "trial-balance": (
        "Snapshot of account balances from live finance data. "
        "Not a closed double-entry trial balance."
    ),
}


def _q(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _money(value) -> Decimal:
    return _q(value)


def _account_methods(account: CompanyExpenseAccount) -> set[str]:
    methods = account.payment_methods or []
    if isinstance(methods, str):
        return {methods}
    return {str(m) for m in methods}


def _is_cash_account(account: CompanyExpenseAccount) -> bool:
    methods = _account_methods(account)
    if CompanyExpenseAccount.PaymentMethod.CASH in methods:
        return True
    return account.system_key == CompanyExpenseAccount.SYSTEM_PETTY_CASH_BOOK


def _is_bank_account(account: CompanyExpenseAccount) -> bool:
    methods = _account_methods(account)
    if methods & {
        CompanyExpenseAccount.PaymentMethod.BANK_TRANSFER,
        CompanyExpenseAccount.PaymentMethod.CHEQUE,
        CompanyExpenseAccount.PaymentMethod.MPESA,
    }:
        return True
    bank_name = (account.bank_name or "").strip().lower()
    if bank_name and bank_name != "system ledger":
        return True
    return account.system_key == CompanyExpenseAccount.SYSTEM_MAIN_CLIENT_ACCOUNTS


def _sorted_accounts(accounts: Iterable[CompanyExpenseAccount]) -> list:
    return sorted(accounts, key=lambda a: (a.name or "").lower())


def _metrics(*pairs):
    return [{"label": label, "value": value} for label, value in pairs]


def _cash_or_bank_book(*, book_slug: str):
    CompanyExpenseAccount.ensure_default_accounts()
    all_accounts = list(CompanyExpenseAccount.objects.all())
    if book_slug == "cash-book":
        scoped = [a for a in all_accounts if _is_cash_account(a)]
        if not scoped:
            scoped = all_accounts
        lead = BOOK_LEADS["cash-book"]
        title = "Cash Book"
    else:
        scoped = [a for a in all_accounts if _is_bank_account(a)]
        if not scoped:
            scoped = [
                a
                for a in all_accounts
                if a.system_key != CompanyExpenseAccount.SYSTEM_PETTY_CASH_BOOK
            ]
        lead = BOOK_LEADS["bank-book"]
        title = "Bank Book"

    account_ids = [a.pk for a in scoped]
    topups = list(
        CompanyAccountTopup.objects.filter(account_id__in=account_ids)
        .select_related(
            "account",
            "source_client",
            "source_company_account",
            "created_by",
        )
        .order_by("created_at", "id")[:ENTRY_LIMIT]
    )
    payments = list(
        CompanyExpensePayment.objects.filter(account_id__in=account_ids)
        .select_related("account", "employee", "created_by")
        .order_by("created_at", "id")[:ENTRY_LIMIT]
    )

    entries = []
    for row in topups:
        entries.append(
            {
                "when": row.created_at,
                "account": row.account.name,
                "particulars": f"{row.account.name} — {row.source_display}",
                "ref": f"CB/{row.pk}" if book_slug == "cash-book" else f"BB/{row.pk}",
                "debit": _money(row.amount),
                "credit": ZERO,
            }
        )
    for row in payments:
        entries.append(
            {
                "when": row.created_at,
                "account": row.account.name,
                "particulars": (
                    f"{row.account.name} — {row.get_expense_type_display()}: "
                    f"{row.description}"
                ),
                "ref": f"CB/{row.pk}" if book_slug == "cash-book" else f"BB/{row.pk}",
                "debit": ZERO,
                "credit": _money(row.amount),
            }
        )
    entries.sort(key=lambda e: (e["when"], e["ref"]))

    running = ZERO
    for index, entry in enumerate(entries, start=1):
        running += entry["debit"] - entry["credit"]
        entry["folio"] = index
        entry["balance"] = running
        entry["balance_side"] = "Dr" if running >= 0 else "Cr"

    total_debit = sum((e["debit"] for e in entries), ZERO)
    total_credit = sum((e["credit"] for e in entries), ZERO)
    book_balance = sum((_money(a.balance) for a in scoped), ZERO)

    return {
        "book_slug": book_slug,
        "book_kind": "cash_bank",
        "book_title": title,
        "book_lead": lead,
        "columns": ("date", "particulars", "folio", "debit", "credit", "balance"),
        "metrics": _metrics(
            ("Accounts", str(len(scoped))),
            ("Closing balance", f"KES {book_balance:,.2f}"),
            ("Total receipts (Dr)", f"KES {total_debit:,.2f}"),
            ("Total payments (Cr)", f"KES {total_credit:,.2f}"),
        ),
        "accounts": [
            {
                "name": a.name,
                "meta": f"{a.bank_name} · {a.bank_account_number}",
                "balance": _money(a.balance),
                "methods": a.payment_method_labels,
                "is_default": a.is_system_default,
            }
            for a in _sorted_accounts(scoped)
        ],
        "entries": entries[:ENTRY_LIMIT],
        "totals": {
            "debit": total_debit,
            "credit": total_credit,
            "balance": running if entries else book_balance,
        },
        "entry_count": len(entries),
        "empty_title": "No movements yet",
        "empty_copy": (
            "Topups and expense payments on matching company accounts "
            "will appear here."
        ),
    }


def _sales_day_book():
    invoices = list(
        Invoice.objects.exclude(status=Invoice.Status.CANCELLED)
        .select_related("client", "created_by")
        .order_by("issue_date", "created_at", "id")[:ENTRY_LIMIT]
    )
    total = sum((_money(inv.total_amount) for inv in invoices), ZERO)
    tax_total = sum((_money(inv.tax_amount) for inv in invoices), ZERO)
    net_total = sum((_money(inv.amount) for inv in invoices), ZERO)
    entries = []
    for index, inv in enumerate(invoices, start=1):
        entries.append(
            {
                "when": inv.issue_date,
                "folio": index,
                "ref": inv.invoice_number,
                "account": inv.client.get_full_name(),
                "particulars": inv.description,
                "net": _money(inv.amount),
                "tax": _money(inv.tax_amount),
                "amount": _money(inv.total_amount),
                "status": inv.get_status_display(),
            }
        )
    return {
        "book_slug": "sales-day-book",
        "book_kind": "sales_day",
        "book_title": "Sales Day Book",
        "book_lead": BOOK_LEADS["sales-day-book"],
        "metrics": _metrics(
            ("Invoices", str(len(invoices))),
            ("Net", f"KES {net_total:,.2f}"),
            ("Tax", f"KES {tax_total:,.2f}"),
            ("Total", f"KES {total:,.2f}"),
        ),
        "entries": entries,
        "totals": {"net": net_total, "tax": tax_total, "amount": total},
        "entry_count": len(entries),
        "empty_title": "No invoices yet",
        "empty_copy": (
            "Generated invoices from Client Accounts → Invoicing appear here."
        ),
    }


def _purchases_day_book():
    payments = list(
        CompanyExpensePayment.objects.select_related(
            "account", "employee", "created_by"
        ).order_by("created_at", "id")[:ENTRY_LIMIT]
    )
    total = sum((_money(p.amount) for p in payments), ZERO)
    entries = []
    for index, row in enumerate(payments, start=1):
        entries.append(
            {
                "when": row.created_at,
                "folio": index,
                "ref": f"PD/{row.pk}",
                "account": row.account.name,
                "particulars": row.description,
                "category": row.get_expense_type_display(),
                "employee": (
                    row.employee.get_full_name() if row.employee_id else "—"
                ),
                "amount": _money(row.amount),
            }
        )
    return {
        "book_slug": "purchases-day-book",
        "book_kind": "purchases_day",
        "book_title": "Purchases Day Book",
        "book_lead": BOOK_LEADS["purchases-day-book"],
        "metrics": _metrics(
            ("Entries", str(len(payments))),
            ("Total", f"KES {total:,.2f}"),
        ),
        "entries": entries,
        "totals": {"amount": total},
        "entry_count": len(entries),
        "empty_title": "No expense payments yet",
        "empty_copy": (
            "Company account expense payments and approved petty cash claims "
            "appear here."
        ),
    }


def _journal_proper():
    raw = []

    transfers = (
        CompanyAccountTopup.objects.filter(
            source_type=CompanyAccountTopup.SourceType.COMPANY_ACCOUNT
        )
        .select_related("account", "source_company_account", "created_by")
        .order_by("created_at", "id")[:120]
    )
    for row in transfers:
        source_name = (
            row.source_company_account.name
            if row.source_company_account_id
            else "Company account"
        )
        amount = _money(row.amount)
        raw.append(
            {
                "when": row.created_at,
                "ref": f"J/{row.pk}",
                "narration": f"Being transfer of funds between company accounts",
                "lines": [
                    {
                        "particulars": row.account.name,
                        "side": "Dr",
                        "debit": amount,
                        "credit": ZERO,
                    },
                    {
                        "particulars": f"    {source_name}",
                        "side": "Cr",
                        "debit": ZERO,
                        "credit": amount,
                    },
                ],
                "amount": amount,
            }
        )

    recovered = (
        EmployeeAdvance.objects.filter(status=EmployeeAdvance.Status.RECOVERED)
        .select_related("employee", "payroll_run", "recorded_by")
        .order_by("recovered_at", "id")[:80]
    )
    for row in recovered:
        when = row.recovered_at or row.created_at
        amount = _money(row.amount)
        name = row.employee.get_full_name()
        raw.append(
            {
                "when": when,
                "ref": f"J/ADV/{row.pk}",
                "narration": f"Being recovery of salary advance — {name}",
                "lines": [
                    {
                        "particulars": "Payroll / net pay",
                        "side": "Dr",
                        "debit": amount,
                        "credit": ZERO,
                    },
                    {
                        "particulars": "    Employee advances",
                        "side": "Cr",
                        "debit": ZERO,
                        "credit": amount,
                    },
                ],
                "amount": amount,
            }
        )

    paid_runs = (
        PayrollRun.objects.filter(status=PayrollRun.Status.PAID)
        .select_related("employee")
        .order_by("updated_at", "id")[:80]
    )
    for run in paid_runs:
        statutory = _money(
            (run.nssf_employee_amount or 0)
            + (run.shif_amount or 0)
            + (run.housing_levy_employee_amount or 0)
            + (run.paye_amount or 0)
        )
        if statutory <= 0:
            continue
        name = run.employee.get_full_name()
        raw.append(
            {
                "when": run.updated_at or run.created_at,
                "ref": f"J/PAY/{run.pk}",
                "narration": (
                    f"Being statutory deductions — {name} "
                    f"({run.pay_period_start}–{run.pay_period_end})"
                ),
                "lines": [
                    {
                        "particulars": "Salaries expense",
                        "side": "Dr",
                        "debit": statutory,
                        "credit": ZERO,
                    },
                    {
                        "particulars": "    Statutory liabilities",
                        "side": "Cr",
                        "debit": ZERO,
                        "credit": statutory,
                    },
                ],
                "amount": statutory,
            }
        )

    raw.sort(key=lambda e: e["when"] or timezone.now())
    entries = []
    total_debit = ZERO
    total_credit = ZERO
    for index, entry in enumerate(raw, start=1):
        entry["folio"] = index
        entries.append(entry)
        for line in entry["lines"]:
            total_debit += line["debit"]
            total_credit += line["credit"]

    return {
        "book_slug": "journal-proper",
        "book_kind": "journal",
        "book_title": "Journal Proper",
        "book_lead": BOOK_LEADS["journal-proper"],
        "metrics": _metrics(
            ("Entries", str(len(entries))),
            ("Total debit", f"KES {total_debit:,.2f}"),
            ("Total credit", f"KES {total_credit:,.2f}"),
        ),
        "entries": entries[:ENTRY_LIMIT],
        "totals": {"debit": total_debit, "credit": total_credit},
        "entry_count": len(entries),
        "empty_title": "No journal entries yet",
        "empty_copy": (
            "Inter-account transfers, recovered advances, and payroll statutory "
            "posts will appear here."
        ),
    }


def _sales_ledger():
    clients = list(
        Client.objects.filter(status=Client.Status.ACTIVE).order_by(
            "company_name", "first_name", "last_name", "email"
        )
    )
    invoices_by_client = defaultdict(list)
    invoices = (
        Invoice.objects.filter(client_id__in=[c.pk for c in clients])
        .exclude(status=Invoice.Status.CANCELLED)
        .select_related("client")
        .order_by("issue_date", "created_at", "id")
    )
    for invoice in invoices:
        invoices_by_client[invoice.client_id].append(invoice)

    groups = []
    total_due = ZERO
    total_credit = ZERO
    total_invoiced = ZERO
    total_paid = ZERO
    folio = 0

    for client in clients:
        items = invoices_by_client.get(client.pk, [])
        credit = _money(client.credit_balance)
        if not items and credit <= ZERO:
            continue
        folio += 1
        invoiced = sum((_money(inv.total_amount) for inv in items), ZERO)
        paid = sum((_money(inv.amount_paid) for inv in items), ZERO)
        due = sum((_money(inv.balance_due) for inv in items), ZERO)
        total_invoiced += invoiced
        total_paid += paid
        total_due += due
        total_credit += credit

        lines = []
        running = ZERO
        for inv in items[:80]:
            debit = _money(inv.total_amount)
            credit_amt = _money(inv.amount_paid)
            # Show invoice as debit; payment as separate credit row when paid.
            running += debit
            lines.append(
                {
                    "when": inv.issue_date,
                    "ref": inv.invoice_number,
                    "particulars": f"Invoice — {inv.description}",
                    "debit": debit,
                    "credit": ZERO,
                    "balance": running,
                }
            )
            if credit_amt > ZERO:
                running -= credit_amt
                lines.append(
                    {
                        "when": inv.updated_at.date()
                        if getattr(inv, "updated_at", None)
                        else inv.issue_date,
                        "ref": inv.invoice_number,
                        "particulars": "By cash / bank / M-Pesa",
                        "debit": ZERO,
                        "credit": credit_amt,
                        "balance": running,
                    }
                )

        groups.append(
            {
                "folio": folio,
                "label": client.get_full_name(),
                "subtitle": client.get_client_type_display(),
                "metrics": {
                    "invoiced": invoiced,
                    "paid": paid,
                    "due": due,
                    "credit": credit,
                },
                "balance": due,
                "balance_side": "Dr",
                "lines": lines,
                "totals": {"debit": invoiced, "credit": paid},
            }
        )

    return {
        "book_slug": "sales-ledger",
        "book_kind": "sales_ledger",
        "book_title": "Sales Ledger (Debtors)",
        "book_lead": BOOK_LEADS["sales-ledger"],
        "metrics": _metrics(
            ("Accounts", str(len(groups))),
            ("Invoiced (Dr)", f"KES {total_invoiced:,.2f}"),
            ("Received (Cr)", f"KES {total_paid:,.2f}"),
            ("Balance due", f"KES {total_due:,.2f}"),
        ),
        "groups": groups,
        "entry_count": len(groups),
        "empty_title": "No client receivable accounts",
        "empty_copy": "Active clients with invoices will appear in this ledger.",
    }


def _purchases_ledger():
    payments = list(
        CompanyExpensePayment.objects.select_related(
            "account", "employee"
        ).order_by("created_at", "id")[:ENTRY_LIMIT]
    )
    by_type: dict[str, list] = defaultdict(list)
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in payments:
        label = row.get_expense_type_display()
        by_type[label].append(row)
        totals[label] += _money(row.amount)

    groups = []
    folio = 0
    for label in sorted(by_type.keys(), key=str.lower):
        folio += 1
        rows = by_type[label]
        lines = []
        running = ZERO
        for index, row in enumerate(rows[:80], start=1):
            amount = _money(row.amount)
            running += amount
            lines.append(
                {
                    "when": row.created_at,
                    "folio": index,
                    "ref": f"PL/{row.pk}",
                    "particulars": (
                        f"{row.account.name} — {row.description}"
                    ),
                    "debit": amount,
                    "credit": ZERO,
                    "balance": running,
                }
            )
        groups.append(
            {
                "folio": folio,
                "label": label,
                "subtitle": f"{len(rows)} entry(ies)",
                "total": totals[label],
                "balance": totals[label],
                "balance_side": "Dr",
                "lines": lines,
                "totals": {"debit": totals[label], "credit": ZERO},
            }
        )

    payroll_paid = (
        PayrollPayment.objects.aggregate(total=Sum("amount_paid"))["total"]
        or ZERO
    )
    grand = sum(totals.values(), ZERO)

    return {
        "book_slug": "purchases-ledger",
        "book_kind": "purchases_ledger",
        "book_title": "Purchases Ledger (Creditors / Expenses)",
        "book_lead": BOOK_LEADS["purchases-ledger"],
        "metrics": _metrics(
            ("Accounts", str(len(groups))),
            ("Expense total", f"KES {grand:,.2f}"),
            ("Payroll receipts", f"KES {_money(payroll_paid):,.2f}"),
        ),
        "groups": groups,
        "entry_count": len(groups),
        "empty_title": "No purchase / expense ledger activity",
        "empty_copy": (
            "Expense payments from Company Accounts will group here by type."
        ),
    }


def _general_ledger():
    CompanyExpenseAccount.ensure_default_accounts()
    accounts = list(CompanyExpenseAccount.objects.order_by("name"))
    gl_accounts = []

    for index, account in enumerate(accounts, start=1):
        topups = list(
            account.topups.select_related("created_by").order_by(
                "created_at", "id"
            )[:80]
        )
        payments = list(
            account.expense_payments.select_related("created_by").order_by(
                "created_at", "id"
            )[:80]
        )
        lines = []
        for row in topups:
            lines.append(
                {
                    "when": row.created_at,
                    "ref": f"GL/T/{row.pk}",
                    "particulars": row.source_display,
                    "debit": _money(row.amount),
                    "credit": ZERO,
                }
            )
        for row in payments:
            lines.append(
                {
                    "when": row.created_at,
                    "ref": f"GL/P/{row.pk}",
                    "particulars": (
                        f"{row.get_expense_type_display()} — {row.description}"
                    ),
                    "debit": ZERO,
                    "credit": _money(row.amount),
                }
            )
        lines.sort(key=lambda e: (e["when"], e["ref"]))
        running = ZERO
        total_debit = ZERO
        total_credit = ZERO
        for line_no, line in enumerate(lines, start=1):
            running += line["debit"] - line["credit"]
            line["folio"] = line_no
            line["balance"] = running
            total_debit += line["debit"]
            total_credit += line["credit"]

        gl_accounts.append(
            {
                "code": f"GL-{index:03d}",
                "folio": index,
                "name": account.name,
                "meta": account.bank_name,
                "balance": _money(account.balance),
                "side": "Dr" if account.balance >= 0 else "Cr",
                "lines": lines,
                "totals": {"debit": total_debit, "credit": total_credit},
            }
        )

    invoices = Invoice.objects.exclude(status=Invoice.Status.CANCELLED)
    ar_balance = sum((_money(inv.balance_due) for inv in invoices), ZERO)
    client_credit = (
        Client.objects.filter(status=Client.Status.ACTIVE).aggregate(
            total=Sum("credit_balance")
        )["total"]
        or ZERO
    )
    advances = (
        EmployeeAdvance.objects.filter(
            status=EmployeeAdvance.Status.OUTSTANDING
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    unpaid_payroll = ZERO
    for run in PayrollRun.objects.filter(status=PayrollRun.Status.REGISTERED):
        unpaid_payroll += _money(run.amount_payable())

    next_folio = len(gl_accounts)
    control_accounts = [
        {
            "code": "AR-001",
            "folio": next_folio + 1,
            "name": "Accounts receivable (clients)",
            "meta": "Control account",
            "balance": _money(ar_balance),
            "side": "Dr",
            "lines": [],
            "totals": {"debit": _money(ar_balance), "credit": ZERO},
        },
        {
            "code": "CR-001",
            "folio": next_folio + 2,
            "name": "Client credit balances",
            "meta": "Control account",
            "balance": _money(client_credit),
            "side": "Cr",
            "lines": [],
            "totals": {"debit": ZERO, "credit": _money(client_credit)},
        },
        {
            "code": "ADV-001",
            "folio": next_folio + 3,
            "name": "Employee advances",
            "meta": "Control account",
            "balance": _money(advances),
            "side": "Dr",
            "lines": [],
            "totals": {"debit": _money(advances), "credit": ZERO},
        },
        {
            "code": "PAY-001",
            "folio": next_folio + 4,
            "name": "Payroll payable",
            "meta": "Control account",
            "balance": _money(unpaid_payroll),
            "side": "Cr",
            "lines": [],
            "totals": {"debit": ZERO, "credit": _money(unpaid_payroll)},
        },
    ]

    return {
        "book_slug": "general-ledger",
        "book_kind": "general_ledger",
        "book_title": "General Ledger",
        "book_lead": BOOK_LEADS["general-ledger"],
        "metrics": _metrics(
            ("Accounts", str(len(gl_accounts) + len(control_accounts))),
            ("AR balance", f"KES {_money(ar_balance):,.2f}"),
            ("Payroll payable", f"KES {_money(unpaid_payroll):,.2f}"),
            ("Advances", f"KES {_money(advances):,.2f}"),
        ),
        "gl_accounts": gl_accounts + control_accounts,
        "entry_count": len(gl_accounts) + len(control_accounts),
        "empty_title": "No ledger accounts",
        "empty_copy": "Register company accounts to populate the general ledger.",
    }


def _trial_balance():
    book = _general_ledger()
    rows = []
    total_debit = ZERO
    total_credit = ZERO
    for account in book["gl_accounts"]:
        bal = _money(account["balance"])
        if bal == ZERO:
            debit = ZERO
            credit = ZERO
        elif account["side"] in {"debit", "Dr"}:
            debit = bal
            credit = ZERO
        else:
            debit = ZERO
            credit = bal
        total_debit += debit
        total_credit += credit
        rows.append(
            {
                "folio": account["folio"],
                "code": account["code"],
                "name": account["name"],
                "debit": debit,
                "credit": credit,
            }
        )

    difference = abs(total_debit - total_credit)
    return {
        "book_slug": "trial-balance",
        "book_kind": "trial_balance",
        "book_title": "Trial Balance",
        "book_lead": BOOK_LEADS["trial-balance"],
        "metrics": _metrics(
            ("Accounts", str(len(rows))),
            ("Total debit", f"KES {total_debit:,.2f}"),
            ("Total credit", f"KES {total_credit:,.2f}"),
            ("Difference", f"KES {difference:,.2f}"),
        ),
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": difference,
        "is_balanced": difference == ZERO,
        "entry_count": len(rows),
        "empty_title": "No balances to list",
        "empty_copy": "Account balances from finance activity will appear here.",
        "generated_at": timezone.localtime(),
    }


BOOK_BUILDERS = {
    "cash-book": lambda: _cash_or_bank_book(book_slug="cash-book"),
    "bank-book": lambda: _cash_or_bank_book(book_slug="bank-book"),
    "sales-day-book": _sales_day_book,
    "purchases-day-book": _purchases_day_book,
    "journal-proper": _journal_proper,
    "sales-ledger": _sales_ledger,
    "purchases-ledger": _purchases_ledger,
    "general-ledger": _general_ledger,
    "trial-balance": _trial_balance,
}

ACCOUNTING_BOOK_SLUGS = frozenset(BOOK_BUILDERS) | {"petty-cash-book"}


def build_accounting_hub_snapshot() -> list[dict]:
    """Compact live metrics for the Accounting hub page."""
    CompanyExpenseAccount.ensure_default_accounts()
    company_balance = (
        CompanyExpenseAccount.objects.aggregate(total=Sum("balance"))["total"]
        or ZERO
    )
    ar_balance = sum(
        (
            _money(inv.balance_due)
            for inv in Invoice.objects.exclude(status=Invoice.Status.CANCELLED)
        ),
        ZERO,
    )
    advances = (
        EmployeeAdvance.objects.filter(
            status=EmployeeAdvance.Status.OUTSTANDING
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    unpaid_payroll = ZERO
    for run in PayrollRun.objects.filter(status=PayrollRun.Status.REGISTERED):
        unpaid_payroll += _money(run.amount_payable())
    return _metrics(
        ("Company ledger balance", f"KES {_money(company_balance):,.2f}"),
        ("Accounts receivable", f"KES {_money(ar_balance):,.2f}"),
        ("Payroll payable", f"KES {_money(unpaid_payroll):,.2f}"),
        ("Outstanding advances", f"KES {_money(advances):,.2f}"),
    )


def build_accounting_book(book_slug: str) -> dict | None:
    """Return live context for an accounting book page, or None if unknown."""
    builder = BOOK_BUILDERS.get(book_slug)
    if not builder:
        return None
    return builder()
