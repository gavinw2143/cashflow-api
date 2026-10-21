import os
from datetime import date

import psycopg
from flask import Flask, current_app, g, jsonify, request
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from cashflow_api.repository import (
    create_loan,
    create_portfolio,
    get_loan_schedule,
    get_portfolio_cashflows,
)


def get_db() -> psycopg.Connection:
    if "db" not in g:
        dsn = current_app.config["DATABASE_URL"]
        if not dsn:
            raise RuntimeError("DATABASE_URL is not configured")

        g.db = psycopg.connect(dsn, autocommit=True)

    return g.db


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")

    if test_config:
        app.config.update(test_config)

    @app.teardown_appcontext
    def close_db(_exception):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.post("/portfolios")
    def post_portfolio():
        if not request.is_json:
            return jsonify(
                error="Content-Type must be application/json"
            ), 415

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify(error="Expected a JSON object"), 400

        code = payload.get("code")
        name = payload.get("name")

        if not isinstance(code, str) or not isinstance(name, str):
            return jsonify(
                error="code and name must be strings"
            ), 400

        code, name = code.strip(), name.strip()

        if not code or not name:
            return jsonify(
                error="code and name cannot be empty"
            ), 400

        try:
            portfolio_id = create_portfolio(
                get_db(), code=code, name=name
            )
        except UniqueViolation:
            return jsonify(
                error="Portfolio code already exists"
            ), 409

        return jsonify(
            id=portfolio_id,
            code=code,
            name=name,
        ), 201

    @app.post("/portfolios/<int:portfolio_id>/loans")
    def post_loan(portfolio_id: int):
        if not request.is_json:
            return jsonify(
                error="Content-Type must be application/json"
            ), 415

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Expected a JSON object"), 400

        reference = payload.get("reference")
        if not isinstance(reference, str) or not reference.strip():
            return jsonify(error="Invalid loan reference"), 400
        reference = reference.strip()

        principal = payload.get("principal_cents")
        rate = payload.get("annual_rate_bps")
        term = payload.get("term_months")

        if type(principal) is not int or not 0 < principal < 2**63:
            return jsonify(error="Invalid principal_cents"), 400

        if type(rate) is not int or not 0 <= rate <= 100_000:
            return jsonify(error="Invalid annual_rate_bps"), 400

        if type(term) is not int or not 1 <= term <= 600:
            return jsonify(error="Invalid term_months"), 400

        raw_date = payload.get("first_payment_date")
        try:
            first_payment_date = date.fromisoformat(raw_date)
            if first_payment_date.isoformat() != raw_date:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(
                error="first_payment_date must be YYYY-MM-DD"
            ), 400

        try:
            loan_id = create_loan(
                get_db(),
                portfolio_id=portfolio_id,
                reference=reference,
                principal_cents=principal,
                annual_rate_bps=rate,
                term_months=term,
                first_payment_date=first_payment_date,
            )
        except ForeignKeyViolation as exc:
            if exc.diag.constraint_name != "loans_portfolio_fk":
                raise
            return jsonify(error="Portfolio not found"), 404
        except UniqueViolation as exc:
            if exc.diag.constraint_name != "loans_reference_unique":
                raise
            return jsonify(
                error="Loan reference already exists in portfolio"
            ), 409

        return jsonify(
            id=loan_id,
            portfolio_id=portfolio_id,
            reference=reference,
            principal_cents=principal,
            annual_rate_bps=rate,
            term_months=term,
            first_payment_date=first_payment_date.isoformat(),
        ), 201

    @app.get("/loans/<int:loan_id>/schedule")
    def get_schedule(loan_id: int):
        schedule = get_loan_schedule(get_db(), loan_id)

        if schedule is None:
            return jsonify(error="Loan not found"), 404

        return jsonify(
            loan_id=loan_id,
            cashflows=[
                {
                    "payment_number": item.payment_number,
                    "due_date": item.due_date.isoformat(),
                    "principal_cents": item.principal_cents,
                    "interest_cents": item.interest_cents,
                    "remaining_balance_cents": (
                        item.remaining_balance_cents
                    ),
                }
                for item in schedule
            ],
        ), 200

    @app.get("/portfolios/<int:portfolio_id>/cashflows")
    def get_cashflows(portfolio_id: int):
        cashflows = get_portfolio_cashflows(
            get_db(), portfolio_id
        )

        if cashflows is None:
            return jsonify(error="Portfolio not found"), 404

        return jsonify(
            portfolio_id=portfolio_id,
            cashflows=[
                {
                    "month": row.month.isoformat(),
                    "principal_cents": row.principal_cents,
                    "interest_cents": row.interest_cents,
                    "total_cents": row.total_cents,
                }
                for row in cashflows
            ],
        ), 200

    return app

