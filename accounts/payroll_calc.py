"""Kenya payroll calculation helpers for register payroll."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")

PAY_FREQUENCIES = (
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
    ("annually", "Annually"),
)
DEFAULT_PAY_FREQUENCY = "monthly"


def pay_period_end_for_frequency(start: date, frequency: str) -> date:
    """Return the inclusive pay period end date from frequency and start."""
    if frequency == "daily":
        return start
    if frequency == "weekly":
        return start + timedelta(days=6)
    if frequency == "monthly":
        last_day = calendar.monthrange(start.year, start.month)[1]
        return date(start.year, start.month, last_day)
    if frequency == "annually":
        try:
            return start.replace(year=start.year + 1) - timedelta(days=1)
        except ValueError:
            return date(start.year + 1, 2, 28)
    return start


def default_pay_period_start(frequency: str = DEFAULT_PAY_FREQUENCY) -> date:
    today = date.today()
    if frequency == "monthly":
        return today.replace(day=1)
    if frequency == "weekly":
        return today - timedelta(days=today.weekday())
    if frequency == "annually":
        return today.replace(month=1, day=1)
    return today


def resolve_pay_period(
    start: date | None, frequency: str | None
) -> tuple[date, date, str]:
    frequency = frequency or DEFAULT_PAY_FREQUENCY
    start = start or default_pay_period_start(frequency)
    end = pay_period_end_for_frequency(start, frequency)
    return start, end, frequency


def q(value) -> Decimal:
    return Decimal(value or 0).quantize(MONEY, rounding=ROUND_HALF_UP)


PAYROLL_RATE_DEFAULTS = {
    "nssf_employee_rate": Decimal("6.00"),
    "nssf_employer_rate": Decimal("1.50"),
    "nssf_tier1_limit": Decimal("7000.00"),
    "nssf_pensionable_cap": Decimal("36000.00"),
    "shif_rate": Decimal("2.75"),
    "housing_levy_employee_rate": Decimal("1.50"),
    "housing_levy_employer_rate": Decimal("1.50"),
    "paye_personal_relief": Decimal("2400.00"),
    "paye_band_1_max": Decimal("24000.00"),
    "paye_band_1_rate": Decimal("10.00"),
    "paye_band_2_max": Decimal("32333.00"),
    "paye_band_2_rate": Decimal("25.00"),
    "paye_band_3_max": Decimal("500000.00"),
    "paye_band_3_rate": Decimal("30.00"),
    "paye_band_4_rate": Decimal("35.00"),
    "nita_levy_amount": Decimal("50.00"),
    "wiba_insurance_amount": Decimal("0.00"),
}


@dataclass
class PayrollEarnings:
    basic_salary: Decimal = Decimal("0")
    house_allowance: Decimal = Decimal("0")
    transport_allowance: Decimal = Decimal("0")
    medical_allowance: Decimal = Decimal("0")
    other_allowances: Decimal = Decimal("0")
    bonuses_overtime_commissions: Decimal = Decimal("0")

    @property
    def gross_salary(self) -> Decimal:
        return q(
            self.basic_salary
            + self.house_allowance
            + self.transport_allowance
            + self.medical_allowance
            + self.other_allowances
            + self.bonuses_overtime_commissions
        )


@dataclass
class PayrollRates:
    nssf_employee_rate: Decimal = PAYROLL_RATE_DEFAULTS["nssf_employee_rate"]
    nssf_employer_rate: Decimal = PAYROLL_RATE_DEFAULTS["nssf_employer_rate"]
    nssf_tier1_limit: Decimal = PAYROLL_RATE_DEFAULTS["nssf_tier1_limit"]
    nssf_pensionable_cap: Decimal = PAYROLL_RATE_DEFAULTS["nssf_pensionable_cap"]
    shif_rate: Decimal = PAYROLL_RATE_DEFAULTS["shif_rate"]
    housing_levy_employee_rate: Decimal = PAYROLL_RATE_DEFAULTS[
        "housing_levy_employee_rate"
    ]
    housing_levy_employer_rate: Decimal = PAYROLL_RATE_DEFAULTS[
        "housing_levy_employer_rate"
    ]
    paye_personal_relief: Decimal = PAYROLL_RATE_DEFAULTS["paye_personal_relief"]
    paye_band_1_max: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_1_max"]
    paye_band_1_rate: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_1_rate"]
    paye_band_2_max: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_2_max"]
    paye_band_2_rate: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_2_rate"]
    paye_band_3_max: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_3_max"]
    paye_band_3_rate: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_3_rate"]
    paye_band_4_rate: Decimal = PAYROLL_RATE_DEFAULTS["paye_band_4_rate"]
    nita_levy_amount: Decimal = PAYROLL_RATE_DEFAULTS["nita_levy_amount"]
    wiba_insurance_amount: Decimal = PAYROLL_RATE_DEFAULTS["wiba_insurance_amount"]


@dataclass
class PayrollBreakdown:
    gross_salary: Decimal
    nssf_employee_amount: Decimal
    shif_amount: Decimal
    housing_levy_employee_amount: Decimal
    paye_amount: Decimal
    total_employee_deductions: Decimal
    net_pay: Decimal
    nssf_employer_amount: Decimal
    housing_levy_employer_amount: Decimal
    nita_levy_amount: Decimal
    wiba_insurance_amount: Decimal
    total_employer_cost: Decimal
    taxable_income: Decimal


def calculate_nssf(
    gross: Decimal,
    *,
    employee_rate: Decimal,
    employer_rate: Decimal,
    tier1_limit: Decimal,
    pensionable_cap: Decimal,
) -> tuple[Decimal, Decimal]:
    gross = q(gross)
    tier1_limit = q(tier1_limit)
    pensionable_cap = q(pensionable_cap)
    pensionable = min(gross, pensionable_cap)

    tier1_base = min(pensionable, tier1_limit)
    tier2_base = max(pensionable - tier1_limit, Decimal("0"))

    employee_amount = q(
        tier1_base * employee_rate / Decimal("100")
        + tier2_base * employee_rate / Decimal("100")
    )
    employer_amount = q(
        tier1_base * employer_rate / Decimal("100")
        + tier2_base * employer_rate / Decimal("100")
    )
    return employee_amount, employer_amount


def calculate_percentage_amount(base: Decimal, rate: Decimal) -> Decimal:
    return q(q(base) * q(rate) / Decimal("100"))


def calculate_paye(
    taxable_income: Decimal,
    *,
    personal_relief: Decimal,
    band_1_max: Decimal,
    band_1_rate: Decimal,
    band_2_max: Decimal,
    band_2_rate: Decimal,
    band_3_max: Decimal,
    band_3_rate: Decimal,
    band_4_rate: Decimal,
) -> Decimal:
    taxable_income = q(taxable_income)
    if taxable_income <= 0:
        return Decimal("0.00")

    bands = [
        (q(band_1_max), q(band_1_rate)),
        (q(band_2_max), q(band_2_rate)),
        (q(band_3_max), q(band_3_rate)),
        (None, q(band_4_rate)),
    ]

    tax = Decimal("0.00")
    lower = Decimal("0.00")
    for upper, rate in bands:
        if taxable_income <= lower:
            break
        if upper is None:
            bracket = taxable_income - lower
        else:
            bracket = min(taxable_income, upper) - lower
        if bracket > 0:
            tax += bracket * rate / Decimal("100")
        if upper is not None:
            lower = upper

    tax = max(tax - q(personal_relief), Decimal("0.00"))
    return q(tax)


def calculate_payroll(
  earnings: PayrollEarnings,
    rates: PayrollRates,
) -> PayrollBreakdown:
    gross = earnings.gross_salary

    nssf_employee_amount, nssf_employer_amount = calculate_nssf(
        gross,
        employee_rate=rates.nssf_employee_rate,
        employer_rate=rates.nssf_employer_rate,
        tier1_limit=rates.nssf_tier1_limit,
        pensionable_cap=rates.nssf_pensionable_cap,
    )
    shif_amount = calculate_percentage_amount(gross, rates.shif_rate)
    housing_levy_employee_amount = calculate_percentage_amount(
        gross, rates.housing_levy_employee_rate
    )
    housing_levy_employer_amount = calculate_percentage_amount(
        gross, rates.housing_levy_employer_rate
    )

    taxable_income = q(gross - nssf_employee_amount)
    paye_amount = calculate_paye(
        taxable_income,
        personal_relief=rates.paye_personal_relief,
        band_1_max=rates.paye_band_1_max,
        band_1_rate=rates.paye_band_1_rate,
        band_2_max=rates.paye_band_2_max,
        band_2_rate=rates.paye_band_2_rate,
        band_3_max=rates.paye_band_3_max,
        band_3_rate=rates.paye_band_3_rate,
        band_4_rate=rates.paye_band_4_rate,
    )

    total_employee_deductions = q(
        nssf_employee_amount
        + shif_amount
        + housing_levy_employee_amount
        + paye_amount
    )
    net_pay = q(gross - total_employee_deductions)

    nita_levy_amount = q(rates.nita_levy_amount)
    wiba_insurance_amount = q(rates.wiba_insurance_amount)
    total_employer_cost = q(
        nssf_employer_amount
        + housing_levy_employer_amount
        + nita_levy_amount
        + wiba_insurance_amount
    )

    return PayrollBreakdown(
        gross_salary=gross,
        nssf_employee_amount=nssf_employee_amount,
        shif_amount=shif_amount,
        housing_levy_employee_amount=housing_levy_employee_amount,
        paye_amount=paye_amount,
        total_employee_deductions=total_employee_deductions,
        net_pay=net_pay,
        nssf_employer_amount=nssf_employer_amount,
        housing_levy_employer_amount=housing_levy_employer_amount,
        nita_levy_amount=nita_levy_amount,
        wiba_insurance_amount=wiba_insurance_amount,
        total_employer_cost=total_employer_cost,
        taxable_income=taxable_income,
    )


def payroll_rate_defaults_json() -> dict[str, str]:
    return {key: str(value) for key, value in PAYROLL_RATE_DEFAULTS.items()}
