from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext


@dataclass(frozen=True, slots=True)
class ScheduledCashflow:
    payment_number: int
    due_date: date
    principal_cents: int
    interest_cents: int
    remaining_balance_cents: int


def _month_date(start: date, offset: int) -> date:
    year, zero_month = divmod(start.year * 12 + start.month - 1 + offset, 12)
    month = zero_month + 1
    last_day = monthrange(year, month)[1]

    is_month_end = start.day == monthrange(start.year, start.month)[1]
    day = last_day if is_month_end else min(start.day, last_day)
    return date(year, month, day)


def generate_schedule(
    principal_cents: int,
    annual_rate_bps: int,
    term_months: int,
    first_payment_date: date,
) -> list[ScheduledCashflow]:
    if principal_cents <= 0:
        raise ValueError("principal must be positive")
    if annual_rate_bps < 0:
        raise ValueError("rate cannot be negative")
    if term_months <= 0:
        raise ValueError("term must be positive")

    with localcontext() as ctx:
        ctx.prec = 40

        principal = Decimal(principal_cents)
        monthly_rate = Decimal(annual_rate_bps) / 120_000

        if monthly_rate == 0:
            payment = principal / term_months
        else:
            payment = (
                principal * monthly_rate / (1 - (1 + monthly_rate) ** (-term_months))
            )

        payment_cents = int(payment.quantize(Decimal(1), rounding=ROUND_HALF_UP))

        balance = principal_cents
        schedule = []

        for number in range(1, term_months + 1):
            interest = int(
                (Decimal(balance) * monthly_rate).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            )

            if number == term_months:
                principal_paid = balance
            else:
                principal_paid = min(
                    balance,
                    max(0, payment_cents - interest),
                )

            balance -= principal_paid

            schedule.append(
                ScheduledCashflow(
                    payment_number=number,
                    due_date=_month_date(first_payment_date, number - 1),
                    principal_cents=principal_paid,
                    interest_cents=interest,
                    remaining_balance_cents=balance,
                )
            )

    return schedule
