from datetime import date

from psycopg import Connection

from cashflow_api.amortization import generate_schedule


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
