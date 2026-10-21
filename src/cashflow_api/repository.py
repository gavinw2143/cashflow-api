from dataclasses import dataclass
from datetime import date

from psycopg import Connection

from cashflow_api.amortization import generate_schedule, ScheduledCashflow


@dataclass(frozen=True, slots=True)
class MonthlyCashflow:
    month: date
    principal_cents: int
    interest_cents: int
    total_cents: int


def get_portfolio_cashflows(
    conn: Connection,
    portfolio_id: int,
) -> list[MonthlyCashflow] | None:
    exists = conn.execute(
        "SELECT 1 FROM portfolios WHERE id = %s",
        (portfolio_id,),
    ).fetchone()

    if exists is None:
        return None

    rows = conn.execute(
        """
        SELECT
            date_trunc('month', c.due_date)::date AS month,
            SUM(c.principal_cents) AS principal_cents,
            SUM(c.interest_cents) AS interest_cents,
            SUM(c.principal_cents + c.interest_cents)
                AS total_cents
        FROM scheduled_cashflows AS c
        JOIN loans AS l ON l.id = c.loan_id
        WHERE l.portfolio_id = %s
        GROUP BY 1
        ORDER BY 1
        """,
        (portfolio_id,),
    ).fetchall()

    return [
        MonthlyCashflow(
            month=row[0],
            principal_cents=int(row[1]),
            interest_cents=int(row[2]),
            total_cents=int(row[3]),
        )
        for row in rows
    ]


def create_loan(
    conn: Connection,
    *,
    portfolio_id: int,
    reference: str,
    principal_cents: int,
    annual_rate_bps: int,
    term_months: int,
    first_payment_date: date,
) -> int:
    schedule = generate_schedule(
        principal_cents,
        annual_rate_bps,
        term_months,
        first_payment_date,
    )

    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO loans (
                portfolio_id, reference, principal_cents,
                annual_rate_bps, term_months,
                first_payment_date
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                portfolio_id,
                reference,
                principal_cents,
                annual_rate_bps,
                term_months,
                first_payment_date,
            ),
        ).fetchone()

        assert row is not None
        loan_id = row[0]

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO scheduled_cashflows (
                    loan_id, payment_number, due_date,
                    principal_cents, interest_cents,
                    remaining_balance_cents
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        loan_id,
                        item.payment_number,
                        item.due_date,
                        item.principal_cents,
                        item.interest_cents,
                        item.remaining_balance_cents,
                    )
                    for item in schedule
                ],
            )

    return loan_id


def create_portfolio(
    conn: Connection,
    *,
    code: str,
    name: str,
) -> int:
    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO portfolios (code, name)
            VALUES (%s, %s)
            RETURNING id
            """,
            (code, name),
        ).fetchone()

        assert row is not None
        return row[0]


def get_loan_schedule(
    conn: Connection,
    loan_id: int,
) -> list[ScheduledCashflow] | None:
    exists = conn.execute(
        "SELECT 1 FROM loans WHERE id = %s",
        (loan_id,),
    ).fetchone()

    if exists is None:
        return None

    rows = conn.execute(
        """
        SELECT
            payment_number,
            due_date,
            principal_cents,
            interest_cents,
            remaining_balance_cents
        FROM scheduled_cashflows
        WHERE loan_id = %s
        ORDER BY payment_number
        """,
        (loan_id,),
    ).fetchall()

    return [ScheduledCashflow(*row) for row in rows]

