import os
from datetime import date
from dataclasses import replace

import psycopg
from psycopg.errors import UniqueViolation
import pytest

import cashflow_api.repository as repository
from cashflow_api.repository import create_loan


def test_create_loan_persists_schedule(db):
    portfolio_id = db.execute(
        """
        INSERT INTO portfolios (code, name)
        VALUES (%s, %s)
        RETURNING id
        """,
        ("test-portfolio", "Test Portfolio"),
    ).fetchone()[0]

    loan_id = create_loan(
        db,
        portfolio_id=portfolio_id,
        reference="loan-001",
        principal_cents=120_000,
        annual_rate_bps=525,
        term_months=12,
        first_payment_date=date(2026, 11, 1),
    )

    rows = db.execute(
        """
        SELECT principal_cents, remaining_balance_cents
        FROM scheduled_cashflows
        WHERE loan_id = %s
        ORDER BY payment_number
        """,
        (loan_id,),
    ).fetchall()

    assert len(rows) == 12
    assert sum(row[0] for row in rows) == 120_000
    assert rows[-1][1] == 0

def test_schedule_failure_rolls_back_loan(db, monkeypatch):
    portfolio_id = db.execute(
        """
        INSERT INTO portfolios (code, name)
        VALUES (%s, %s)
        RETURNING id
        """,
        ("rollback-test", "Rollback Test Portfolio"),
    ).fetchone()[0]

    original_generate = repository.generate_schedule

    def duplicate_payment(*args, **kwargs):
        schedule = original_generate(*args, **kwargs)

        schedule[1] = replace(
            schedule[1],
            payment_number=schedule[0].payment_number,
        )
        return schedule

    monkeypatch.setattr(
        repository, "generate_schedule", duplicate_payment
    )

    with pytest.raises(UniqueViolation):
        repository.create_loan(
            db,
            portfolio_id=portfolio_id,
            reference="rollback-loan",
            principal_cents=120_000,
            annual_rate_bps=525,
            term_months=12,
            first_payment_date=date(2026, 11, 1),
        )

    # The failed schedule insert must undo the loan insert.
    assert db.execute(
        """
        SELECT COUNT(*) FROM loans
        WHERE portfolio_id = %s AND reference = %s
        """,
        (portfolio_id, "rollback-loan"),
    ).fetchone() == (0,)

    # The enclosing test transaction must remain usable.
    assert db.execute(
        "SELECT COUNT(*) FROM portfolios WHERE id = %s",
        (portfolio_id,),
    ).fetchone() == (1,)

