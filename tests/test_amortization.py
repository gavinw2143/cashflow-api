import itertools
from datetime import date

import pytest

from cashflow_api.amortization import generate_schedule


def test_fixed_rate_amortization():
    rows = generate_schedule(
        principal_cents=120_000,
        annual_rate_bps=525,
        term_months=12,
        first_payment_date=date(2026, 11, 1),
    )

    assert len(rows) == 12
    assert rows[0].principal_cents == 9762
    assert rows[0].interest_cents == 525
    assert rows[0].remaining_balance_cents == 110238

    assert sum(r.principal_cents for r in rows) == 120_000
    assert rows[-1].remaining_balance_cents == 0
    assert [r.payment_number for r in rows] == list(range(1, 13))

    for previous, current in itertools.pairwise(rows):
        assert (
            previous.remaining_balance_cents - current.principal_cents
            == current.remaining_balance_cents
        )


def test_zero_interest_and_rounding():
    rows = generate_schedule(100, 0, 3, date(2027, 1, 31))

    assert [r.principal_cents for r in rows] == [33, 33, 34]
    assert all(r.interest_cents == 0 for r in rows)
    assert rows[-1].remaining_balance_cents == 0


def test_month_end_dates():
    rows = generate_schedule(120_000, 525, 3, date(2027, 1, 31))

    assert [r.due_date for r in rows] == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
    ]


@pytest.mark.parametrize(
    "principal,rate,term",
    [
        (0, 525, 12),
        (120_000, -1, 12),
        (120_000, 525, 0),
    ],
)
def test_invalid_terms(principal, rate, term):
    with pytest.raises(ValueError):
        generate_schedule(principal, rate, term, date(2026, 11, 1))
